#!/usr/bin/env python3
"""One-shot transcription CLI for Moss Transcribe WebUI.

Attaches to a running WebUI service (local or remote). If no service is
running locally, starts one automatically and stops it when finished.
Pure standard library — the cli/ folder works standalone against any
reachable WebUI service.

Usage: transcribe <file> [options]        single file
       transcribe -b <folder> [options]   all media files in a folder
       transcribe --list-backend          list inference backends
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit

PROG = "transcribe"

MEDIA_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
              ".wma", ".mp4", ".mkv", ".webm", ".mov", ".avi"}
MAX_UPLOAD_BYTES = 2 * 1024 ** 3   # server-side hard limit

PROBE_TIMEOUT = 2      # service detection
HTTP_TIMEOUT = 60      # per socket operation
HTTP_WAIT_S = 90       # self-started service: time to begin listening
MODEL_WAIT_S = 300     # model load / backend switch
POLL_S = 1.0

EXIT_OK = 0
EXIT_USAGE = 1         # bad arguments / bad input files
EXIT_SERVICE = 2       # service unreachable or failed
EXIT_JOBS = 3          # one or more transcription jobs failed

STATUS_TEXT = {"queued": "queued", "converting": "converting",
               "running": "transcribing", "done": "done",
               "error": "failed", "cancelled": "cancelled"}

EXAMPLES = """examples:
  transcribe meeting.wav
  transcribe meeting.wav --output srt --diarize off
  transcribe recording.wav --autosplit 15
  transcribe -b ./recordings --output all
  transcribe --list-backend
  transcribe voice.mp3 --host 192.168.50.2 --port 8390
"""


class ServiceError(Exception):
    def __init__(self, msg: str, http_code: int | None = None):
        super().__init__(msg)
        self.http_code = http_code


def die(code: int, msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---- HTTP ----

def base_url(host: str, port: int) -> str:
    h = f"[{host}]" if ":" in host else host
    return f"http://{h}:{port}"


def probe_host(host: str) -> str:
    """0.0.0.0 是绑定地址而非连接地址；本机回环始终可达。"""
    return "127.0.0.1" if host in ("0.0.0.0", "") else host


def is_local_host(host: str) -> bool:
    h = host.strip("[]").lower()
    if h in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return True
    try:
        locals_ = {info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)}
        return socket.gethostbyname(host) in locals_
    except OSError:
        return False


def http_json(method: str, url: str, payload=None, timeout: float = HTTP_TIMEOUT):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail", "")
        except Exception:
            detail = ""
        raise ServiceError(f"HTTP {e.code}: {detail}" if detail else f"HTTP {e.code}",
                           http_code=e.code) from None
    except urllib.error.URLError as e:
        raise ServiceError(f"cannot reach service: {e.reason}") from None
    except (TimeoutError, socket.timeout, ValueError) as e:
        raise ServiceError(f"service communication failed: {e}") from None


class Client:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.base = base_url(host, port)

    def get(self, path: str):
        return http_json("GET", self.base + path)

    def post_json(self, path: str, payload):
        return http_json("POST", self.base + path, payload)

    def probe(self) -> bool:
        try:
            st = http_json("GET", self.base + "/api/status", timeout=PROBE_TIMEOUT)
            return isinstance(st, dict) and "model" in st
        except (ServiceError, ValueError):
            return False

    def upload(self, fields: dict, file_path: Path) -> dict:
        """multipart/form-data 流式上传（http.client 允许原生 utf-8 文件名，
        urllib 的 header 只能 latin-1）。"""
        u = urlsplit(self.base)
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=HTTP_TIMEOUT)
        boundary = "----MossCLI" + uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"\r\n\r\n{v}\r\n')
        head = "".join(parts).encode("utf-8")
        head += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                 f"filename=\"{file_path.name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
        size = len(head) + file_path.stat().st_size + len(tail)
        try:
            try:
                conn.putrequest("POST", "/api/jobs")
                conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
                conn.putheader("Content-Length", str(size))
                conn.endheaders()
                conn.send(head)
                with open(file_path, "rb") as f:
                    while True:
                        block = f.read(1 << 20)
                        if not block:
                            break
                        conn.send(block)
                conn.send(tail)
            except OSError:
                pass  # 服务器可能提前拒绝并断开（如超限），仍尝试读响应
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
            if resp.status != 200:
                try:
                    detail = json.loads(body).get("detail", "")
                except ValueError:
                    detail = ""
                raise ServiceError(f"upload rejected (HTTP {resp.status}): {detail}",
                                   http_code=resp.status)
            return json.loads(body)
        except OSError as e:
            raise ServiceError(f"upload failed: {e}") from None
        finally:
            conn.close()


# ---- 服务生命周期 ----

SERVICE = {"proc": None, "logf": None, "self_started": False}


def log_tail(logf) -> str:
    try:
        logf.flush()
        with open(logf.name, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return text[-800:].strip()
    except OSError:
        return "(log unavailable)"


def start_local_service(host: str, port: int, model: str | None):
    repo = Path(__file__).resolve().parent.parent
    venv_py = repo / ".venv" / "Scripts" / "python.exe"
    server = repo / "webui" / "server.py"
    if not venv_py.is_file() or not server.is_file():
        die(EXIT_SERVICE, "cannot start a local service: this cli folder is not inside "
                          "a full WebUI deployment (no .venv / webui/server.py)")
    cmd = [str(venv_py), str(server), "--host", host, "--port", str(port)]
    if model:
        cmd += ["-m", str(Path(model).resolve())]
    logf = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False,
                                       encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(repo), stdout=logf, stderr=subprocess.STDOUT)
    SERVICE.update(proc=proc, logf=logf, self_started=True)


def wait_http(client: Client) -> None:
    deadline = time.time() + HTTP_WAIT_S
    while time.time() < deadline:
        if SERVICE["proc"].poll() is not None:
            die(EXIT_SERVICE, "service exited during startup:\n" + log_tail(SERVICE["logf"]))
        if client.probe():
            return
        time.sleep(0.5)
    die(EXIT_SERVICE, "service did not start in time:\n" + log_tail(SERVICE["logf"]))


def stop_service() -> None:
    proc, logf = SERVICE["proc"], SERVICE["logf"]
    if proc is not None and proc.poll() is None:
        print("service: stopping...")
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
    if logf is not None:
        try:
            logf.close()
        except OSError:
            pass
        try:
            os.unlink(logf.name)
        except OSError:
            pass
    SERVICE.update(proc=None, logf=None, self_started=False)


def connect_or_start(args, client: Client) -> None:
    if client.probe():
        if args.model:
            print("warning: -m ignored (using the running service)", file=sys.stderr)
        print(f"service: attached to {client.base}")
        return
    if not is_local_host(args.host):
        die(EXIT_SERVICE, f"no service at {client.base} and cannot start one on a remote host")
    print(f"service: none at {client.base}, starting locally...")
    start_local_service(args.host, args.port, args.model)
    wait_http(client)
    print(f"service: started (pid {SERVICE['proc'].pid})")


def wait_model_ready(client: Client, allow_error: bool = False) -> dict:
    deadline = time.time() + MODEL_WAIT_S
    while True:
        st = client.get("/api/status")
        m = st["model"]
        if m.get("state") == "ready" and not m.get("loading"):
            return st
        if m.get("state") == "error" and allow_error:
            return st
        if m.get("state") == "error":
            die(EXIT_SERVICE, f"model unavailable: {m.get('error')} "
                              f"(pass --backend to switch devices)")
        if time.time() > deadline:
            die(EXIT_SERVICE, "timed out waiting for the model to become ready")
        time.sleep(POLL_S)


def find_device(st: dict, name: str):
    devices = st.get("devices") or []
    for d in devices:
        if d["name"] == name:
            return d
    for d in devices:
        if d["name"].lower() == name.lower():
            return d
    return None


def ensure_backend(client: Client, args) -> None:
    name = args.backend
    if not name or name.lower() == "auto":
        return
    st = client.get("/api/status")
    dev = find_device(st, name)
    if dev is None:
        names = ", ".join(d["name"] for d in st.get("devices") or []) or "none"
        die(EXIT_USAGE, f"unknown backend {name!r}; available: {names}")
    current = st["model"].get("backend")
    if current == dev["name"] and st["model"].get("state") == "ready":
        return
    print(f"service: switching backend to {dev['name']} (model reload)...")
    client.post_json("/api/model", {"backend": dev["kind"], "device_index": dev["index"]})
    # 阶段一：确认重载线程已接管（loading 置位），避免把旧状态误判为完成
    deadline = time.time() + 10
    while time.time() < deadline:
        m = client.get("/api/status")["model"]
        if m.get("loading"):
            break
        if m.get("state") == "ready" and m.get("backend") == dev["name"]:
            return
        time.sleep(0.2)
    # 阶段二：等待重载结束
    deadline = time.time() + MODEL_WAIT_S
    while time.time() < deadline:
        m = client.get("/api/status")["model"]
        if not m.get("loading"):
            if m.get("error"):
                die(EXIT_SERVICE, f"backend switch failed: {m['error']}")
            if m.get("state") == "ready" and m.get("backend") == dev["name"]:
                return
            die(EXIT_SERVICE, f"backend switch failed: now on {m.get('backend')!r}, "
                              f"wanted {dev['name']!r}")
        time.sleep(POLL_S)
    die(EXIT_SERVICE, "timed out waiting for backend switch")


# ---- 结果导出（格式对齐 WebUI 前端导出）----

def speaker_map(result: dict) -> dict:
    """后端 raw speaker_id（1 起、可能不连续）→ 连续 1..N。"""
    ids = set()
    for s in result.get("segments") or []:
        if s.get("speaker_id", -1) >= 0:
            ids.add(s["speaker_id"])
    for s in result.get("speaker_segments") or []:
        if s.get("speaker_id", -1) >= 0:
            ids.add(s["speaker_id"])
    return {sid: i for i, sid in enumerate(sorted(ids), 1)}


def fmt_clock(ms: int) -> str:
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def srt_time(ms: int) -> str:
    h, rem = divmod(int(ms), 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def txt_content(job: dict) -> str:
    r = job.get("result") or {}
    segs = r.get("segments") or []
    params = job.get("params") or {}
    with_diarize = params.get("diarize") == "on"
    no_ts = params.get("timestamps") == "none"
    smap = speaker_map(r)
    if not segs:
        return (r.get("text") or "") + "\n"
    lines = []
    for s in segs:
        time = "" if no_ts else f"[{fmt_clock(s['t0_ms'])} → {fmt_clock(s['t1_ms'])}] "
        sp = f"Speaker {smap[s['speaker_id']]}: " if with_diarize else ""
        lines.append(time + sp + (s.get("text") or ""))
    return "\n".join(lines) + "\n"


def srt_content(job: dict) -> str:
    r = job.get("result") or {}
    segs = r.get("segments") or []
    with_diarize = (job.get("params") or {}).get("diarize") == "on"
    smap = speaker_map(r)
    blocks = []
    for i, s in enumerate(segs, 1):
        sp = f"Speaker {smap[s['speaker_id']]}: " if with_diarize else ""
        blocks.append(f"{i}\n{srt_time(s['t0_ms'])} --> {srt_time(s['t1_ms'])}\n"
                      f"{sp}{s.get('text') or ''}\n")
    return "\n".join(blocks)


def write_outputs(job: dict, out_dir: Path, stem: str, kinds: list, count: int, idx: int) -> list:
    suffix = "" if count == 1 else f".{idx}of{count}"
    written = []
    for kind in kinds:
        target = out_dir / f"{stem}{suffix}.{kind}"
        if kind == "txt":
            target.write_text(txt_content(job), encoding="utf-8")
        elif kind == "srt":
            target.write_text(srt_content(job), encoding="utf-8")
        else:
            target.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        written.append(target)
    return written


# ---- 任务执行 ----

ACTIVE_JOBS: list[str] = []   # Ctrl+C 时对它们发 cancel


def make_fields(args) -> dict:
    return {
        "timestamps": "none" if args.timestamp == "none" else "segment",
        "diarize": args.diarize,
        "kv_type": args.kv_cache_type,
        "n_threads": str(args.threads),
        "n_ctx": str(args.n_ctx),
        "chunk_min": str(args.autosplit),
    }


def wait_jobs(client: Client, job_ids: list, label: str) -> list:
    idx_of = {jid: i for i, jid in enumerate(job_ids, 1)}
    n = len(job_ids)
    results: dict[str, dict] = {}
    last_status: dict[str, str] = {}
    remaining = list(job_ids)
    ACTIVE_JOBS.extend(job_ids)
    try:
        while remaining:
            jobs = {j["id"]: j for j in client.get("/api/jobs")["jobs"]}
            for jid in list(remaining):
                j = jobs.get(jid)
                if j is None:
                    results[jid] = {"id": jid, "status": "error",
                                    "error": "job disappeared (deleted on the server)"}
                    remaining.remove(jid)
                    continue
                s = j["status"]
                if s != last_status.get(jid):
                    part = f"part {idx_of[jid]}/{n}: " if n > 1 else ""
                    print(f"  {label}: {part}{STATUS_TEXT.get(s, s)}")
                    last_status[jid] = s
                if s in ("done", "error", "cancelled"):
                    results[jid] = j
                    remaining.remove(jid)
            if remaining:
                time.sleep(POLL_S)
    finally:
        for jid in job_ids:
            if jid in ACTIVE_JOBS:
                ACTIVE_JOBS.remove(jid)
    return [results[jid] for jid in job_ids]


def transcribe_file(client: Client, path: Path, args, kinds: list, label: str) -> bool:
    t0 = time.time()
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        print(f"{label}: failed: file exceeds the 2 GB upload limit", file=sys.stderr)
        return False
    print(f"{label}: uploading...")
    try:
        resp = client.upload(make_fields(args), path)
    except ServiceError as e:
        if e.http_code in (400, 413, 422):   # 该文件自身的问题，不中断批次
            print(f"{label}: failed: {e}", file=sys.stderr)
            return False
        die(EXIT_SERVICE, str(e))
    ids = resp.get("job_ids") or [resp["job_id"]]
    count = resp.get("count", len(ids))
    if count > 1:
        print(f"  {label}: split into {count} parts")
    jobs = wait_jobs(client, ids, label)
    if not all(j["status"] == "done" for j in jobs):
        for j in jobs:
            if j["status"] != "done":
                print(f"  {label}: failed: {j.get('error') or j['status']}", file=sys.stderr)
        return False
    written = []
    for i, j in enumerate(jobs, 1):
        written += write_outputs(j, path.parent, path.stem, kinds, count, i)
    for w in written:
        print(f"  {label}: wrote {w}")
    note = f" ({jobs[0].get('detail')})" if jobs[0].get("detail") else ""
    print(f"{label}: done in {time.time() - t0:.0f}s{note}")
    return True


def cmd_list_backend(client: Client) -> None:
    st = client.get("/api/status")
    print("available backends:")
    for d in st.get("devices") or []:
        free = (d.get("memory_free") or 0) / 1024 ** 3
        print(f"  {d['name']:<12} {d['kind']:<8} {free:6.1f} GB free")
    m = st.get("model") or {}
    if m.get("state") == "ready":
        print(f"current: {m.get('backend')}")


# ---- 参数 ----

class _Parser(argparse.ArgumentParser):
    def error(self, message):   # argparse 默认退出码 2 与服务的 2 冲突，统一为 1
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def parse_args(argv):
    p = _Parser(prog=PROG,
                description="One-shot transcription via Moss Transcribe WebUI. "
                            "Attaches to a running WebUI service; starts a local "
                            "one if needed (and stops it after).",
                epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", nargs="?", help="audio/video file to transcribe")
    p.add_argument("-b", "--batch", metavar="FOLDER",
                   help="transcribe all media files in FOLDER (top level only)")
    p.add_argument("--timestamp", choices=["segments", "segment", "none"],
                   default="segments", help="timestamp mode (default: segments)")
    p.add_argument("--diarize", choices=["on", "off"], default="on",
                   help="speaker diarization (default: on)")
    p.add_argument("--autosplit", type=int, default=0, metavar="MIN",
                   help="auto-split long audio into MIN-minute chunks, 0 = off (default: 0)")
    p.add_argument("--kv-cache-type", choices=["auto", "f32", "f16"], default="auto",
                   help="KV cache type (default: auto)")
    p.add_argument("--n-ctx", type=int, default=131072, metavar="N",
                   help="context size, 0-131072, 0 = engine default (default: 131072)")
    p.add_argument("--threads", type=int, default=0, metavar="N",
                   help="CPU threads, 0 = automatic (default: automatic)")
    p.add_argument("--backend", metavar="NAME",
                   help="inference backend device name (see --list-backend)")
    p.add_argument("--list-backend", action="store_true",
                   help="list available backends and exit")
    p.add_argument("--output", choices=["txt", "srt", "json", "all"], default="txt",
                   help="output format (default: txt)")
    p.add_argument("--host", default="127.0.0.1",
                   help="WebUI service host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8390,
                   help="WebUI service port (default: 8390)")
    p.add_argument("-m", "--model", metavar="GGUF",
                   help="model path, only used when the CLI starts the service")
    return p.parse_args(argv)


def validate(args) -> list | None:
    """返回待转录文件列表；--list-backend 返回 None（不做文件检查）。"""
    if not 1 <= args.port <= 65535:
        die(EXIT_USAGE, "--port must be 1-65535")
    if not 0 <= args.autosplit <= 180:
        die(EXIT_USAGE, "--autosplit must be 0-180")
    if not 0 <= args.n_ctx <= 131072:
        die(EXIT_USAGE, "--n-ctx must be 0-131072")
    if args.threads < 0:
        die(EXIT_USAGE, "--threads must be >= 0")
    kinds = {"txt": ["txt"], "srt": ["srt"], "json": ["json"],
             "all": ["txt", "srt", "json"]}[args.output]
    if "srt" in kinds and args.timestamp == "none":
        die(EXIT_USAGE, "--output srt requires timestamps; 'none' has no timing data")
    if args.list_backend:
        return None
    if args.batch is not None and args.path is not None:
        die(EXIT_USAGE, "--batch cannot be combined with a file path")
    if args.batch is None and args.path is None:
        die(EXIT_USAGE, "nothing to transcribe: pass a file path or --batch FOLDER")
    if args.batch is not None:
        folder = Path(args.batch)
        if not folder.is_dir():
            die(EXIT_USAGE, f"not a folder: {folder}")
        files = sorted(p for p in folder.iterdir()
                       if p.is_file() and p.suffix.lower() in MEDIA_EXTS)
        if not files:
            die(EXIT_USAGE, f"no media files in {folder}")
        return files
    p = Path(args.path)
    if not p.is_file():
        die(EXIT_USAGE, f"not a file: {p}")
    return [p]


# ---- 主流程 ----

def run(args, files) -> int:
    client = Client(probe_host(args.host), args.port)
    code = EXIT_OK
    try:
        connect_or_start(args, client)
        if args.list_backend:
            cmd_list_backend(client)
            return EXIT_OK
        wait_model_ready(client, allow_error=bool(args.backend))
        ensure_backend(client, args)
        kinds = {"txt": ["txt"], "srt": ["srt"], "json": ["json"],
                 "all": ["txt", "srt", "json"]}[args.output]
        ok = 0
        for i, f in enumerate(files, 1):
            label = f"[{i}/{len(files)}] {f.name}" if len(files) > 1 else f.name
            if transcribe_file(client, f, args, kinds, label):
                ok += 1
        print(f"\n{ok}/{len(files)} file(s) transcribed.")
        code = EXIT_OK if ok == len(files) else EXIT_JOBS
    except KeyboardInterrupt:
        print("\ninterrupted: cancelling active jobs...")
        for jid in list(ACTIVE_JOBS):
            try:
                client.post_json(f"/api/jobs/{jid}/cancel", {})
            except Exception:
                pass
        code = 130
    finally:
        if SERVICE["self_started"]:
            stop_service()
    return code


def main(argv=None) -> None:
    # 行缓冲必须显式开：stdout 接管道/文件时 Python 默认全缓冲，
    # Agent 捕获 CLI 输出会到进程退出才看到内容
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace", line_buffering=True)
        sys.stderr.reconfigure(errors="replace", line_buffering=True)
    args = parse_args(argv)
    files = validate(args)
    sys.exit(run(args, files))


if __name__ == "__main__":
    main()
