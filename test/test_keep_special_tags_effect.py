"""交叉测试 keep_special_tags 对 Moss 输出的影响。

文档语义：True 时保留输出文本中的特殊标记（时间戳 token 等）。
实测矩阵：中/英文 × timestamps none/segment × diarize on/off × keep False/True，
对比分段哈希、文本标记扫描，以及 speaker_segments 哈希。
"""
import hashlib
import re
import subprocess
import wave

import numpy as np
import transcribe_cpp as tc

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"


def load_pcm(path, resample=False):
    if resample:  # audio_zh.wav 是 FLAC 封装，需 ffmpeg 转码
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ar", "16000", "-ac", "1",
             "-f", "f32le", "pipe:1"], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace"))
        return np.frombuffer(p.stdout, dtype=np.float32)
    with wave.open(path, "rb") as wf:
        return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


pcm_zh = load_pcm(r"test\audio_zh.wav", resample=True)
pcm_en = load_pcm(r"test\audio_mono.wav")

model = tc.Model(MODEL, backend="cuda")


def seg_hash(r):
    return hashlib.md5(repr([(s.t0_ms, s.t1_ms, s.text) for s in r.segments]).encode()).hexdigest()[:10]


def spk_hash(r):
    return hashlib.md5(repr([(x.t0_ms, x.t1_ms, x.speaker_id)
                             for x in r.speaker_segments]).encode()).hexdigest()[:10]


print(f"{'audio':4s} {'ts':8s} {'dia':4s} {'keep':5s} {'seg_hash':10s} 文本内标记")
diffs = 0
for label, pcm in [("zh", pcm_zh), ("en", pcm_en)]:
    for ts in ("none", "segment"):
        for dia in ("on", "off"):
            baseline = None
            for keep in (False, True):
                with model.session(kv_type="f16") as s:
                    r = s.run(pcm, language="zh", timestamps=ts, diarize=dia,
                              keep_special_tags=keep)
                h = seg_hash(r)
                tags = re.findall(r"<\|[^|]*\|>|<[^>]{1,20}>|\[[A-Z_]{2,10}\]", r.text)
                if keep is False:
                    baseline = (h, spk_hash(r))
                else:
                    if (h, spk_hash(r)) != baseline:
                        diffs += 1
                print(f"{label:4s} {ts:8s} {dia:4s} {str(keep):5s} {h} "
                      f"{tags[:6] if tags else '无'}")

model.close()
print(f"\nkeep=True 与 False 输出不一致的组合数: {diffs} (0 = 全组合无差异)")
