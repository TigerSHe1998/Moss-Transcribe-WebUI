"""测 Session.cancel() 在 CPU 后端的实际生效延迟。

CPU 上跑 247s 音频（够慢），run 起飞后 5s 时在主线程外调 cancel()，
测量 cancel 调用 → run 抛 Aborted 的间隔。对照 CUDA 同样测一次。
"""
import subprocess
import threading
import time
import wave

import numpy as np
import transcribe_cpp as tc

MODEL = r"model\MOSS-Transcribe-Diarize-Q8_0.gguf"


def load_pcm(path, resample=False):
    if resample:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
             "-f", "f32le", "pipe:1"], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace"))
        return np.frombuffer(p.stdout, dtype=np.float32)
    with wave.open(path, "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def test_cancel(backend, pcm, cancel_after_s):
    model = tc.Model(MODEL, backend=backend)
    with model.session(kv_type="f16") as s:
        result = {}

        def runner():
            t0 = time.time()
            try:
                s.run(pcm, language="zh", timestamps="segment", diarize="on")
                result["outcome"] = "completed"
            except tc.Aborted:
                result["outcome"] = "aborted"
            result["run_s"] = time.time() - t0

        th = threading.Thread(target=runner)
        th.start()
        time.sleep(cancel_after_s)
        t_cancel = time.time()
        s.cancel()
        result["cancel_to_abort_s"] = None  # runner 结束时回填
        th.join(timeout=300)
        result["cancel_wait_s"] = time.time() - t_cancel
    model.close()
    return result


pcm = load_pcm(r"test\audio_mono.wav")  # 247s
print("==== CPU backend: cancel 5s into run ====", flush=True)
r = test_cancel("cpu", pcm, cancel_after_s=5)
print(f"outcome={r['outcome']} | cancel→线程退出 {r['cancel_wait_s']:.1f}s | run 总时长 {r['run_s']:.1f}s", flush=True)

print("\n==== CUDA backend: cancel 5s into run (对照) ====", flush=True)
r2 = test_cancel("cuda", pcm, cancel_after_s=5)
print(f"outcome={r2['outcome']} | cancel→线程退出 {r2['cancel_wait_s']:.2f}s | run 总时长 {r2['run_s']:.1f}s", flush=True)
