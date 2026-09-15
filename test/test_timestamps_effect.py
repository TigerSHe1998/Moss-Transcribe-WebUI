"""交叉测试 timestamps 参数对 Moss 输出的影响。

同一音频分别用 none / auto / segment 跑（diarize=off 隔离变量），
对比：分段数量、t0_ms/t1_ms 是否有值、文本是否一致。
另跑 diarize=on 的 none/segment 对比，看说话人时间段是否受影响。
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


pcm = load_pcm(r"test\audio_zh.wav", resample=True)
print(f"audio: {len(pcm)/16000:.1f}s")

model = tc.Model(MODEL, backend="cuda")

runs = {}


def seg_sig(r):
    """分段签名：每段的 (t0_ms, t1_ms, text)，用于逐字节对比。"""
    return [(s.t0_ms, s.t1_ms, s.text) for s in r.segments]


def spk_sig(r):
    return [(s.t0_ms, s.t1_ms, s.speaker_id) for s in (r.speaker_segments or [])]


for label, ts, dia in [
    ("timestamps='none'    diarize=off", "none", "off"),
    ("timestamps='auto'    diarize=off", "auto", "off"),
    ("timestamps='segment' diarize=off", "segment", "off"),
    ("timestamps='none'    diarize=on ", "none", "on"),
    ("timestamps='segment' diarize=on ", "segment", "on"),
]:
    with model.session() as s:
        r = s.run(pcm, language="zh", timestamps=ts, diarize=dia,
                  keep_special_tags=False)
    runs[label] = {"text": r.text, "segs": seg_sig(r), "spk": spk_sig(r)}
    print("=" * 78)
    print(label)
    print(f"  segments: {len(r.segments)} 段")
    for s_ in r.segments[:3]:
        print(f"    [{s_.t0_ms:>7} → {s_.t1_ms:>7}] {s_.text[:40]!r}")
    if len(r.segments) > 3:
        print(f"    ... 其余 {len(r.segments)-3} 段省略")
    print(f"  text[:60]: {r.text[:60]!r}")
    if r.speaker_segments:
        print(f"  speaker_segments: {len(r.speaker_segments)} 条, "
              f"首条 [{r.speaker_segments[0].t0_ms} → {r.speaker_segments[0].t1_ms}] "
              f"spk={r.speaker_segments[0].speaker_id}")
    else:
        print("  speaker_segments: 无")

model.close()

print("\n" + "#" * 78)
print("# 对比结论")
keys = list(runs)
base = runs[keys[2]]  # segment / diarize=off
for k in keys[:3]:
    r = runs[k]
    same_text = r["text"] == base["text"]
    same_times = all(t0 == bt0 and t1 == bt1
                     for (t0, t1, _), (bt0, bt1, _) in zip(r["segs"], base["segs"]))
    print(f"{k}: 文本与segment一致={same_text}, 时间戳与segment一致={same_times}, "
          f"段数={len(r['segs'])}")
none_on = runs[keys[3]]
seg_on = runs[keys[4]]
print(f"diarize=on 时 none vs segment: 说话人段数 {len(none_on['spk'])} vs {len(seg_on['spk'])}, "
      f"说话人时间段一致={none_on['spk'] == seg_on['spk']}")
