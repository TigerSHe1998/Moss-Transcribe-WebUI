"""Moss 转录 WebUI 服务端。

用法:
    python webui/server.py                     # 仅本机访问 (127.0.0.1:8390)
    python webui/server.py --host 0.0.0.0      # 暴露给局域网（需放行防火墙端口）
    python webui/server.py --port 8390 --model <path> --backend cuda
"""

from __future__ import annotations

import argparse
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import transcribe_cpp as tc
from engine import Engine, fmt_ms, probe_duration_ms

logger = logging.getLogger("webui")

# 默认模型：工程目录 model/ 下（gitignore，不入库）；可用 --model 指定其他路径
DEFAULT_MODEL = str(Path(__file__).resolve().parent.parent / "model" / "MOSS-Transcribe-Diarize-Q8_0.gguf")
MAX_UPLOAD_BYTES = 2 * 1024**3
STATIC_DIR = Path(__file__).parent / "static"

_NATIVE_LEVELS = {1: logging.INFO, 2: logging.WARNING, 3: logging.ERROR, 4: logging.DEBUG}


def _native_log(level: int, message: str) -> None:
    logging.getLogger("native").log(_NATIVE_LEVELS.get(level, logging.INFO), message.rstrip())


class ModelRequest(BaseModel):
    backend: str = "auto"
    device_index: int | None = None


def create_app(model_path: str, backend: str = "auto",
               device_index: int | None = None) -> FastAPI:
    engine = Engine(model_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine.start(backend, device_index)
        yield

    app = FastAPI(title="Moss 转录 WebUI", lifespan=lifespan)
    app.state.engine = engine

    # 页面与静态资源必须每次回源验证（未变化时仍是廉价的 304）。
    # 不加此头时浏览器会启发式缓存，可能直接用旧 CSS 而不询问服务器，
    # 导致"已修复的 bug 用户仍然看得到"。
    @app.middleware("http")
    async def revalidate_assets(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # ---- 页面与状态 ----

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        return engine.status()

    @app.post("/api/model")
    def reload_model(req: ModelRequest) -> dict:
        ok, msg = engine.request_reload(req.backend, req.device_index)
        if not ok:
            raise HTTPException(409, msg)
        return {"ok": True}

    # ---- 任务 ----

    @app.post("/api/jobs")
    async def create_job(
        file: UploadFile = File(...),
        timestamps: str = Form("segment"),
        diarize: str = Form("on"),
        kv_type: str = Form("auto"),
        n_threads: int = Form(0),
        n_ctx: int = Form(0),
    ):
        if timestamps not in ("none", "auto", "segment"):
            raise HTTPException(400, f"不支持的时间戳选项 {timestamps!r}，可选: none/auto/segment")
        if diarize not in ("default", "off", "on"):
            raise HTTPException(400, f"不支持的说话人分离选项 {diarize!r}")
        if kv_type not in ("auto", "f32", "f16"):
            raise HTTPException(400, f"不支持的 KV 类型 {kv_type!r}")
        if n_threads < 0 or n_ctx < 0:
            raise HTTPException(400, "n_threads / n_ctx 不能为负数")

        if engine.state == "error":
            raise HTTPException(409, f"模型当前不可用: {engine.error}，请先切换设备重新加载")

        suffix = Path(file.filename or "upload").suffix[:12] or ".bin"
        dest = engine.upload_dir / f"{uuid.uuid4().hex}{suffix}"
        size = 0
        try:
            with dest.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "文件过大（上限 2 GB）")
                    out.write(chunk)
            if size == 0:
                raise HTTPException(400, "空文件")

            # ffprobe 时长预检，超长直接拒绝，不进入队列
            est_ms = await run_in_threadpool(probe_duration_ms, dest)
            limit = engine.max_audio_ms
            if est_ms and limit and est_ms > limit:
                raise HTTPException(
                    422,
                    f"音频约 {fmt_ms(est_ms)}，超过模型单次处理上限 {fmt_ms(limit)}，"
                    f"请裁剪后再上传",
                )

            params = {
                "timestamps": timestamps,
                "diarize": diarize,
                "kv_type": kv_type,
                "n_threads": n_threads,
                "n_ctx": n_ctx,
            }
            job = engine.submit(dest, file.filename or dest.name, params)
            return {"job_id": job.id}
        except HTTPException:
            dest.unlink(missing_ok=True)
            raise
        except Exception as e:
            dest.unlink(missing_ok=True)
            logger.exception("上传处理失败")
            raise HTTPException(500, f"上传处理失败: {e}") from e

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        return {"jobs": engine.list_jobs()}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = engine.get_job(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在")
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict:
        if not engine.cancel(job_id):
            raise HTTPException(404, "任务不存在或无法取消")
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/delete")
    def delete_job(job_id: str) -> dict:
        ok, msg = engine.delete(job_id)
        if not ok:
            raise HTTPException(400, msg)
        return {"ok": True}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Moss 转录 WebUI")
    parser.add_argument("--host", default="127.0.0.1",
                        help="监听地址；局域网访问用 0.0.0.0（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8390)
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help="GGUF 模型路径")
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "cpu", "metal", "vulkan", "cpu_accel", "cuda", "rocm"])
    parser.add_argument("--device-index", type=int, default=None,
                        help="backends() 返回的设备索引（按 status 中的顺序）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # native 日志改道 logging：必须在任何模型加载之前安装（0.x 契约），且 handler 线程安全
    tc.set_log_callback(_native_log)

    if not Path(args.model).is_file():
        raise SystemExit(f"模型文件不存在: {args.model}")

    app = create_app(args.model, args.backend, args.device_index)
    logger.info("WebUI: http://%s:%d  (局域网请使用 --host 0.0.0.0)", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
