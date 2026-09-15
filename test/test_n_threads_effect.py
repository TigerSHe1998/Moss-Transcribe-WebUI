"""实测 n_threads 在不同后端下的效果。

CUDA0：247s 音频，n_threads=1 / 0(默认) / 32，对比解码耗时
  —— 若三者一致，说明 CUDA 下 n_threads 无效果。
CPU：7.9s 音频，n_threads=1 / 0(默认) / 16，对比解码耗时
  —— 若差异显著，说明 CPU 下真实生效。
"""
import subprocess
import time
import wave

import numpy as np
import transcribe_cpp as tc

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"


def load_pcm(path, resample=False):
    if resample:  # audio_zh.wav 是 FLAC 封装，需 ffmpeg 转 16k mono
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
             "-f", "f32le", "pipe:1"], capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        return np.frombuffer(proc.stdout, dtype=np.float32)
    with wave.open(path, "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


short = load_pcm(r"test\audio_zh.wav", resample=True)  # 7.9s
long_ = load_pcm(r"test\audio_mono.wav")  # 247s

print("==== CUDA0 × 247s 音频 ====", flush=True)
model = tc.Model(MODEL, backend="cuda")
for nt in [1, 0, 32]:
    # 每档跑两遍取第二遍（排除首跑 JIT/缓存噪声）
    for run_i in (1, 2):
        with model.session(n_threads=nt, kv_type="f16") as s:
            t0 = time.time()
            r = s.run(long_, language="zh", timestamps="segment", diarize="on")
            wall = time.time() - t0
        if run_i == 2:
            print(f"n_threads={nt:3d} (默认值 0 表示不传): wall {wall:5.1f}s "
                  f"enc {r.timings.encode_ms/1000:5.2f}s dec {r.timings.decode_ms/1000:6.2f}s "
                  f"{len(r.segments)}段", flush=True)
model.close()

print("\n==== CPU × 7.9s 音频 ====", flush=True)
model = tc.Model(MODEL, backend="cpu")
for nt in [1, 0, 16]:
    with model.session(n_threads=nt, kv_type="f16") as s:
        t0 = time.time()
        r = s.run(short, language="zh", timestamps="segment", diarize="on")
        wall = time.time() - t0
    print(f"n_threads={nt:3d}: wall {wall:6.2f}s "
          f"enc {r.timings.encode_ms/1000:6.3f}s dec {r.timings.decode_ms/1000:6.2f}s "
          f"{len(r.segments)}段 文本前20字: {r.text[:20]!r}", flush=True)
model.close()

print("\n==== Vulkan0 × 7.9s 音频（每档两遍取第二遍）====", flush=True)
model = tc.Model(MODEL, backend="vulkan")
for nt in [1, 0, 16]:
    for run_i in (1, 2):
        with model.session(n_threads=nt, kv_type="f16") as s:
            t0 = time.time()
            r = s.run(short, language="zh", timestamps="segment", diarize="on")
            wall = time.time() - t0
        if run_i == 2:
            print(f"n_threads={nt:3d}: wall {wall:6.2f}s "
                  f"enc {r.timings.encode_ms/1000:6.3f}s dec {r.timings.decode_ms/1000:6.2f}s", flush=True)
model.close()
