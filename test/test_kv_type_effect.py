"""对比 kv_type（auto/f32/f16）在 CUDA0 下的显存占用与转录速度。

每种类型：全新加载模型 → 建会话（记录显存）→ 后台线程采样显存跑
247s 音频 → 记录 encode/decode 耗时、文本哈希、effective_n_ctx。
每种跑两遍（第二遍为热身后的对照）。
"""
import hashlib
import threading
import time
import wave

import numpy as np
import transcribe_cpp as tc

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"


def load_pcm(path):
    with wave.open(path, "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def cuda_free_mb():
    for d in tc.backends():
        if d.kind == "cuda":
            return d.memory_free / 1024 ** 2
    raise RuntimeError("no cuda backend")


def wait_vram_stable(timeout=30.0):
    """等上一轮模型的显存释放完（相邻两次读数变化 < 20MB 视为稳定）。"""
    prev = cuda_free_mb()
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        cur = cuda_free_mb()
        if abs(cur - prev) < 20:
            return cur
        prev = cur
    return cur


class Sampler:
    """run 期间每 150ms 采样一次 CUDA0 空闲显存。"""

    def __init__(self):
        self.stop = False
        self.samples = []
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self.stop:
            try:
                self.samples.append(cuda_free_mb())
            except Exception:
                pass
            time.sleep(0.15)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.stop = True
        self.thread.join()


pcm = load_pcm(r"test\audio_mono.wav")
print(f"audio: {len(pcm)/16000:.1f}s (English, 58 段)", flush=True)

results = {}
for kv in ["auto", "f32", "f16"]:
    for run_i in (1, 2):
        wait_vram_stable()
        model = tc.Model(MODEL, backend="cuda")
        idle = cuda_free_mb()
        with model.session(kv_type=kv) as s:
            eff_ctx = s.limits.effective_n_ctx
            after_sess = cuda_free_mb()
            with Sampler() as sam:
                t0 = time.time()
                r = s.run(pcm, language="zh", timestamps="segment", diarize="on")
                wall = time.time() - t0
            after_run = cuda_free_mb()
        model.close()

        peak_free = min(sam.samples) if sam.samples else after_run
        results[(kv, run_i)] = dict(
            idle=idle, after_sess=after_sess, after_run=after_run,
            sess_alloc=idle - after_sess,
            peak_extra=idle - peak_free,
            wall_s=wall,
            encode_ms=r.timings.encode_ms, decode_ms=r.timings.decode_ms,
            text_hash=hashlib.md5(r.text.encode()).hexdigest()[:10],
            nseg=len(r.segments), eff_ctx=eff_ctx,
        )
        d = results[(kv, run_i)]
        print(f"kv={kv:4s} run{run_i} | 显存: 模型后剩 {idle:7.1f}M, 建会话用 "
              f"{d['sess_alloc']:6.1f}M, 峰值再增 {d['peak_extra']:6.1f}M | "
              f"耗时: wall {wall:5.1f}s enc {d['encode_ms']/1000:5.2f}s "
              f"dec {d['decode_ms']/1000:6.2f}s | {d['nseg']}段 hash={d['text_hash']} "
              f"n_ctx={eff_ctx}", flush=True)

print("\n==== 汇总（run2 为热身后数据）====")
print(f"{'kv_type':8s} {'会话KV分配(MB)':>14s} {'运行峰值增(MB)':>14s} "
      f"{'encode(s)':>10s} {'decode(s)':>10s} {'wall(s)':>8s} {'文本hash':>12s}")
for kv in ["auto", "f32", "f16"]:
    d = results[(kv, 2)]
    print(f"{kv:8s} {d['sess_alloc']:14.1f} {d['peak_extra']:14.1f} "
          f"{d['encode_ms']/1000:10.2f} {d['decode_ms']/1000:10.2f} "
          f"{d['wall_s']:8.1f} {d['text_hash']:>12s}")
hashes = {kv: results[(kv, 2)]["text_hash"] for kv in ["auto", "f32", "f16"]}
print("三配置文本一致:", len(set(hashes.values())) == 1, hashes)
