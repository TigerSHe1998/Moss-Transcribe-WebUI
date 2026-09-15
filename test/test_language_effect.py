"""交叉测试 language 参数对 Moss 输出的影响。

中文音频与英文音频分别用 zh / en / 不传 跑一遍，对比输出文本与 Result.language。
"""
import subprocess
import wave

import numpy as np
import transcribe_cpp as tc

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"


def load_pcm(path, resample=False):
    if resample:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
             "-f", "f32le", "pipe:1"],
            capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        return np.frombuffer(proc.stdout, dtype=np.float32)
    with wave.open(path, "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


zh_pcm = load_pcm(r"test\audio_zh.wav", resample=True)  # FLAC 44.1k → 16k
en_pcm = load_pcm(r"test\audio_mono.wav")
print(f"zh audio: {len(zh_pcm)/16000:.1f}s | en audio: {len(en_pcm)/16000:.1f}s")

model = tc.Model(MODEL, backend="cuda")

for label, pcm, lang in [
    ("zh音频 × language='zh'", zh_pcm, "zh"),
    ("zh音频 × language='en'", zh_pcm, "en"),
    ("zh音频 × 不传language", zh_pcm, None),
    ("en音频 × language='zh'", en_pcm, "zh"),
    ("en音频 × language='en'", en_pcm, "en"),
]:
    with model.session() as s:
        r = s.run(pcm, language=lang, timestamps="segment", diarize="off")
    print("=" * 78)
    print(f"{label}  → Result.language={r.language!r}")
    print(f"text[:100]: {r.text[:100]!r}")

model.close()
