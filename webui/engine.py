"""WebUI 核心引擎：模型加载/重载、任务队列、ffmpeg 转码、取消。

并发模型（对应 transcribe.cpp 0.x 的限制，见 transcribe_cpp_api.md §13）：
- 一个 Model 同时只能有一个 run 在飞，因此所有推理由单个 worker 线程串行执行；
- 模型重载与推理共用 _run_lock 互斥，重载会等当前 run 结束，期间新任务排队；
- 取消：排队中的任务直接标记取消；转码/推理中的任务设置 cancel_requested，
  推理阶段通过 Session.cancel() 在下一个解码边界中止并保留 partial_result。
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import transcribe_cpp as tc

log = logging.getLogger("webui.engine")

SAMPLE_RATE = 16000
HISTORY_LIMIT = 30  # 内存中保留的已完成任务数

VALID_BACKENDS = {"auto", "cpu", "metal", "vulkan", "cpu_accel", "cuda", "rocm"}
TIMESTAMP_CHOICES = ("none", "auto", "segment")
DIARIZE_CHOICES = ("default", "off", "on")
KV_CHOICES = ("auto", "f32", "f16")


# --- 音频工具 ---------------------------------------------------------------


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def probe_duration_ms(path: Path) -> Optional[int]:
    """ffprobe 读取媒体时长（毫秒）；无 ffprobe 或失败返回 None。"""
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        dur = float(json.loads(proc.stdout)["format"]["duration"])
        return int(dur * 1000) if dur > 0 else None
    except Exception:
        return None


def load_pcm(path: Path) -> np.ndarray:
    """任意媒体 → 16kHz 单声道 float32。有 ffmpeg 走转码（含视频抽音轨、
    重采样、下混）；无 ffmpeg 时仅支持 16kHz/16-bit/mono PCM WAV。"""
    if ffmpeg_available():
        cmd = [
            "ffmpeg", "-v", "error", "-y", "-i", str(path),
            "-vn", "-sn", "-dn", "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-f", "f32le", "pipe:1",
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()[:500]
            raise RuntimeError(f"ffmpeg 转码失败: {detail}")
        pcm = np.frombuffer(proc.stdout, dtype=np.float32)
        if pcm.size == 0:
            raise RuntimeError("转码后没有音频数据（文件可能没有音轨）")
        return pcm
    with wave.open(str(path), "rb") as wf:
        if (wf.getnchannels(), wf.getframerate(), wf.getsampwidth()) != (1, SAMPLE_RATE, 2):
            raise RuntimeError("本机未安装 ffmpeg，仅支持 16kHz 单声道 16-bit PCM WAV")
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def _jsonable(obj: Any) -> Any:
    """NaN/Inf → None；Python json 默认输出 NaN 字面量，浏览器 JSON.parse 会失败。"""
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) else None
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def serialize_result(result: tc.Result) -> dict:
    return _jsonable(asdict(result))


def fmt_ms(ms: int) -> str:
    s = ms / 1000
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}小时{m}分{sec}秒" if h else f"{m}分{sec}秒"


# --- 任务 -------------------------------------------------------------------


@dataclass
class Job:
    id: str
    filename: str
    stored_path: str
    params: dict
    status: str = "queued"  # queued|converting|running|done|error|cancelled
    detail: str = ""
    error: Optional[str] = None
    audio_ms: Optional[int] = None
    cancel_requested: bool = False
    created: float = field(default_factory=time.time)
    started: Optional[float] = None
    finished: Optional[float] = None
    result: Optional[dict] = None

    def to_dict(self, queue_position: Optional[int] = None) -> dict:
        d = {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "detail": self.detail,
            "error": self.error,
            "audio_ms": self.audio_ms,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "params": self.params,
            "queue_position": queue_position,
        }
        if self.result is not None:
            d["result"] = self.result
        return d


# --- 引擎 -------------------------------------------------------------------


class Engine:
    def __init__(self, model_path: str | Path, upload_dir: str | Path = "uploads"):
        self.model_path = Path(model_path)
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # 任务状态只存内存：重启后历史任务已不存在，清掉残留的上传文件
        for leftover in self.upload_dir.iterdir():
            if leftover.is_file():
                try:
                    leftover.unlink()
                except OSError as e:
                    log.warning("清理残留上传文件失败 %s: %s", leftover, e)

        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []  # 提交顺序（旧→新）
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._jobs_lock = threading.Lock()
        # 推理与模型重载互斥（0.x：同一模型同时只能有一个 run；重载需等当前 run 结束）
        self._run_lock = threading.RLock()

        self._model: Optional[tc.Model] = None
        self._state = "loading"  # loading|ready|error
        self._error: Optional[str] = None
        self._caps: Optional[tc.Capabilities] = None
        self._supports_diarize = False  # 不在 Capabilities 字段里，经 Model.supports() 查询
        self._limits: Optional[dict] = None
        self._model_info: dict = {}
        self._loading = False
        self._load_lock = threading.Lock()
        self._active_session: Optional[tc.Session] = None

    # ---- 生命周期与状态 ----

    @property
    def state(self) -> str:
        return self._state

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def capabilities(self) -> Optional[tc.Capabilities]:
        return self._caps

    @property
    def supports_diarization(self) -> bool:
        return self._supports_diarize

    @property
    def max_audio_ms(self) -> Optional[int]:
        if self._limits and self._limits["effective_max_audio_ms"] > 0:
            return self._limits["effective_max_audio_ms"]
        return None

    def start(self, backend: str = "auto", device_index: Optional[int] = None) -> None:
        threading.Thread(target=self._worker, daemon=True, name="job-worker").start()
        self.request_reload(backend, device_index)

    def request_reload(self, backend: str = "auto",
                       device_index: Optional[int] = None) -> tuple[bool, str]:
        """请求后台重载模型（等当前推理结束后切换）。已在加载中则拒绝。"""
        if backend not in VALID_BACKENDS:
            return False, f"未知的后端 {backend!r}，可选: {sorted(VALID_BACKENDS)}"
        if device_index is not None:
            n = len(tc.backends())
            if not 0 <= device_index < n:
                return False, f"设备索引 {device_index} 超出范围（当前共 {n} 个设备）"
        with self._load_lock:
            if self._loading:
                return False, "模型正在加载中，请稍候"
            self._loading = True

        def run():
            try:
                self._load(backend, device_index)
            finally:
                with self._load_lock:
                    self._loading = False

        threading.Thread(target=run, daemon=True, name="model-load").start()
        return True, ""

    def _load(self, backend: str, device_index: Optional[int]) -> None:
        with self._run_lock:
            self._state = "loading"
            self._error = None
            try:
                device = None
                if device_index is not None:
                    device = tc.backends()[device_index]
                model = tc.Model(self.model_path, backend=backend, device=device)
                old, self._model = self._model, model
                self._caps = model.capabilities
                self._supports_diarize = model.supports("diarization")
                with model.session() as s:
                    lm = s.limits
                    self._limits = {
                        "effective_n_ctx": lm.effective_n_ctx,
                        "effective_max_audio_ms": lm.effective_max_audio_ms,
                        "max_kv_bytes": lm.max_kv_bytes,
                    }
                self._model_info = {
                    "arch": model.arch, "variant": model.variant, "backend": model.backend,
                }
                self._state = "ready"
                if old is not None:
                    old.close()
                log.info("模型已就绪: %s (%s)", model.variant, model.backend)
            except Exception as e:
                log.exception("模型加载失败")
                if self._model is not None:
                    # 旧模型仍可用，仅记录本次重载失败
                    self._state = "ready"
                    self._error = f"上次重载失败: {e}"
                else:
                    self._state = "error"
                    self._error = str(e)

    def status(self) -> dict:
        devices = []
        try:
            for d in tc.backends():
                devices.append({
                    "index": d.index, "name": d.name, "kind": d.kind,
                    "description": d.description, "device_type": d.device_type,
                    "memory_total": d.memory_total, "memory_free": d.memory_free,
                })
        except Exception as e:
            log.warning("backends() 枚举失败: %s", e)

        model = {"state": self._state, "error": self._error, "loading": self._loading}
        model.update(self._model_info)
        if self._model is not None:
            try:
                d = self._model.device
                model["device"] = {
                    "name": d.name, "kind": d.kind,
                    "memory_total": d.memory_total, "memory_free": d.memory_free,
                }
            except Exception:
                pass

        caps: Optional[dict] = None
        if self._caps is not None:
            caps = _jsonable(asdict(self._caps))
            caps["supports_diarization"] = self._supports_diarize

        with self._jobs_lock:
            active = sum(1 for j in self._jobs.values()
                         if j.status in ("queued", "converting", "running"))

        return {
            "model": model,
            "capabilities": caps,
            "limits": self._limits,
            "devices": devices,
            "ffmpeg": ffmpeg_available(),
            "active_jobs": active,
            "version": tc.__version__,
            "native_version": tc.native_version(),
        }

    # ---- 任务管理 ----

    def submit(self, stored_path: Path, filename: str, params: dict) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            stored_path=str(stored_path),
            params=params,
        )
        with self._jobs_lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._prune_locked()
        self._queue.put(job.id)
        return job

    def _prune_locked(self) -> None:
        finished = [jid for jid in self._order
                    if self._jobs[jid].status in ("done", "error", "cancelled")]
        overflow = len(finished) - HISTORY_LIMIT
        for jid in finished[:max(overflow, 0)]:
            self._drop_locked(jid)

    def _drop_locked(self, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None:
            Path(job.stored_path).unlink(missing_ok=True)
        if job_id in self._order:
            self._order.remove(job_id)

    def list_jobs(self) -> list[dict]:
        with self._jobs_lock:
            pos = 0
            positions: dict[str, int] = {}
            for jid in self._order:
                if self._jobs[jid].status == "queued":
                    pos += 1
                    positions[jid] = pos
            return [self._jobs[jid].to_dict(positions.get(jid))
                    for jid in reversed(self._order)]

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            pos = None
            if job.status == "queued":
                pos = sum(1 for jid in self._order[:self._order.index(job_id)]
                          if self._jobs[jid].status == "queued") + 1
            return job.to_dict(pos)

    def cancel(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status == "queued":
                job.status = "cancelled"
                job.finished = time.time()
                return True
            if job.status in ("converting", "running"):
                job.cancel_requested = True
                session = self._active_session
                if session is not None and job.status == "running":
                    session.cancel()
                return True
            return False

    def delete(self, job_id: str) -> tuple[bool, str]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False, "任务不存在"
            if job.status in ("queued", "converting", "running"):
                return False, "任务进行中，请先取消"
            self._drop_locked(job_id)
        return True, ""

    # ---- worker ----

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._jobs_lock:
                job = self._jobs.get(job_id)
            if job is None or job.status == "cancelled":
                continue
            try:
                self._process(job)
            except Exception as e:
                log.exception("任务 %s 处理失败", job_id)
                job.status = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.finished = time.time()

    def _session_for(self, job: Job) -> "tc.Session":
        model = self._model
        assert model is not None
        return model.session(
            n_threads=int(job.params.get("n_threads") or 0),
            kv_type=job.params.get("kv_type", "auto"),
            n_ctx=int(job.params.get("n_ctx") or 0),
        )

    def _process(self, job: Job) -> None:
        with self._run_lock:
            if job.cancel_requested or job.status == "cancelled":
                job.status = "cancelled"
                job.finished = time.time()
                return
            if self._state != "ready" or self._model is None:
                job.status = "error"
                job.error = f"模型不可用（{self._state}）: {self._error or '尚未加载完成'}"
                job.finished = time.time()
                return

            # 先建会话（开销极小）：拿到本任务参数（n_ctx 等）下的真实时长上限
            session = self._session_for(job)
            try:
                lm = session.limits
                job_limit = lm.effective_max_audio_ms if lm.effective_max_audio_ms > 0 else None

                # 时长预检（ffprobe 估算；转码后再按采样点数精确校验）
                est = probe_duration_ms(Path(job.stored_path))
                if est:
                    job.audio_ms = est
                    if self._over_limit(job, est, job_limit):
                        return
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.finished = time.time()
                    return

                job.status = "converting"
                job.detail = "ffmpeg 转码中" if ffmpeg_available() else "读取 WAV"
                pcm = load_pcm(Path(job.stored_path))
                audio_ms = int(len(pcm) * 1000 // SAMPLE_RATE)
                job.audio_ms = audio_ms
                if self._over_limit(job, audio_ms, job_limit):
                    return
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.finished = time.time()
                    return

                job.status = "running"
                job.detail = ""
                job.started = time.time()
                self._active_session = session
                if job.cancel_requested:
                    # 关闭竞态窗口：置 running 与赋值 _active_session 之间收到的取消
                    session.cancel()
                # Moss 的 language 参数实测无效果（模型内部自行判定语言），
                # 传固定值仅为满足绑定接口
                result = session.run(
                    pcm,
                    task="transcribe",
                    language="zh",
                    timestamps=job.params.get("timestamps", "segment"),
                    diarize=job.params.get("diarize", "on"),
                    keep_special_tags=bool(job.params.get("keep_special_tags")),
                )
                job.result = serialize_result(result)
                job.status = "done"
            except tc.Aborted as e:
                job.status = "cancelled"
                partial = getattr(e, "partial_result", None)
                # Moss 的分段在解码完成时才物化，中途取消的 partial 常为空；
                # 仅在确有内容时展示
                if partial is not None and (partial.text or partial.segments):
                    job.result = serialize_result(partial)
                    job.detail = "含部分结果"
            except tc.OutputTruncated as e:
                partial = getattr(e, "partial_result", None)
                if partial is None:
                    raise
                job.result = serialize_result(partial)
                job.status = "done"
                job.detail = "输出被截断，仅部分结果"
            finally:
                self._active_session = None
                session.close()
                job.finished = time.time()

    def _over_limit(self, job: Job, audio_ms: int, limit: Optional[int]) -> bool:
        if limit and audio_ms > limit:
            job.status = "error"
            job.error = (
                f"音频时长 {fmt_ms(audio_ms)}，超过本次设置下的处理上限 {fmt_ms(limit)}"
                f"（n_ctx={job.params.get('n_ctx', 0)}），请调大 n_ctx 或裁剪音频后再试"
            )
            job.finished = time.time()
            return True
        return False
