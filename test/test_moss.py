import wave
import numpy as np
import transcribe_cpp

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"
AUDIO = r"C:\AI\transcribe_cpp_native_cu12-0.2.3-py3-none-win_amd64\test\audio_mono.wav"

# 选择 RTX 5090
device = next(
    d for d in transcribe_cpp.backends()
    if d.kind == "cuda" and d.name == "CUDA0"
)

print("Using device:", device)

# 读取 WAV
with wave.open(AUDIO, "rb") as wf:
    channels = wf.getnchannels()
    sample_rate = wf.getframerate()
    sample_width = wf.getsampwidth()
    frames = wf.readframes(wf.getnframes())

if channels != 1:
    raise ValueError(f"需要 mono WAV，当前 channels={channels}")

if sample_rate != 16000:
    raise ValueError(f"需要 16000 Hz，当前 sample_rate={sample_rate}")

if sample_width != 2:
    raise ValueError(
        f"当前脚本要求 16-bit PCM WAV，当前 sample_width={sample_width}"
    )

# int16 -> float32
pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

print(f"Audio: {len(pcm) / sample_rate:.2f} sec")

result = transcribe_cpp.transcribe(
    MODEL,
    pcm,
    backend="cuda",
    device=device,
    language="zh",
    timestamps="segment",
    diarize="on",
)

print("\n===== RESULT =====")
print(result)