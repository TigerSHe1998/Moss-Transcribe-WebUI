# transcribe.cpp Python Binding 接口文档

> 面向 WebUI 开发的接口参考。基于 `transcribe_cpp` **0.2.3**（native 0.2.3, commit `63a44d9`，
> provider `transcribe-cpp-native-cu12`），通过打印各公开符号的 `help()` 并实机探测 Moss 模型能力整理而成。
>
> 绑定包源码位置：`.venv/Lib/site-packages/transcribe_cpp/`（`__init__.py` 为主要实现）。

---

## 目录

1. [部署环境实测](#1-部署环境实测)
2. [快速开始](#2-快速开始)
3. [模块级函数](#3-模块级函数)
4. [类型别名（字符串枚举）](#4-类型别名字符串枚举)
5. [Model — 已加载模型](#5-model--已加载模型)
6. [Session — 转录会话](#6-session--转录会话)
7. [Stream — 流式转录](#7-stream--流式转录)
8. [结果对象（不可变 dataclass）](#8-结果对象不可变-dataclass)
9. [BackendDevice — 计算设备](#9-backenddevice--计算设备)
10. [FamilyExtension — 模型家族扩展选项](#10-familyextension--模型家族扩展选项)
11. [异常层次](#11-异常层次)
12. [PCM 输入格式要求](#12-pcm-输入格式要求)
13. [线程与并发](#13-线程与并发)
14. [WebUI 集成建议](#14-webui-集成建议)

---

## 1. 部署环境实测

本机（venv 内）实际探测结果，WebUI 可直接依赖这些结论：

**运行时信息**

| 项目 | 值 |
|---|---|
| Python 包版本 / native 版本 | `0.2.3` / `0.2.3`（pre-1.0 要求 base 版本完全一致，否则 import 时报错） |
| native provider | `transcribe-cpp-native-cu12` |
| native 库路径 | `.venv/Lib/site-packages/transcribe_cpp_native_cu12/_native/transcribe.dll` |

**注册的计算设备**（`backends()` 实测）

| index | name | kind | device_type | 显存/内存 |
|---|---|---|---|---|
| 0 | `CUDA0` | `cuda` | `gpu` | 31.8 GiB（RTX 5090, compute 12.0） |
| 1 | `Vulkan0` | `vulkan` | `gpu` | 31.4 GiB |
| 2 | `CPU` | `cpu` | `cpu` | 127.6 GiB |

**MOSS-Transcribe-Diarize-Q8_0.gguf 模型能力**（`Model.capabilities` / `supports()` 实测）

| 能力 | 值 | 说明 |
|---|---|---|
| arch / variant | `moss` / `moss-transcribe-diarize` | |
| 原生采样率 | 16000 Hz | 输入必须重采样到 16k mono float32 |
| 支持语言 | `('en', 'zh')` | |
| 语言自动检测 | ❌ 不支持 | **必须显式传 `language="zh"` 或 `"en"`** |
| 最大时间戳粒度 | `segment` | 词级/`token` 级时间戳不可用 |
| 说话人分离（diarization） | ✅ 支持 | `diarize="on"` |
| 取消（cancellation） | ✅ 支持 | `Session.cancel()` 可中断推理 |
| 翻译（translate） | ❌ | `task` 只能用 `"transcribe"` |
| 流式（streaming） | ❌ | `Session.stream()` 会抛 `NotImplementedByModel` |
| 投机解码 / pnc / itn / initial_prompt / 温度回退 / long_form | ❌ | |
| 接受任何 FamilyExtension | ❌ | `accepts()` 对所有扩展返回 False |
| 默认会话限制 | `effective_n_ctx=131072`，`effective_max_audio_ms=10458400`（≈2.9 小时），`max_kv_bytes≈14 GiB` | 输入超过约 2.9 小时会抛 `InputTooLong` |

> `import transcribe_cpp` 时即加载 native 库并注册后端（CUDA/Vulkan/CPU DLL），会向 stderr 打印 ggml 日志。
> 首次加载模型输出 `moss: using cuda backend: CUDA0`。

---

## 2. 快速开始

一次性转录（模型随调用加载/释放，见 `test/test_moss.py`）：

```python
import wave
import numpy as np
import transcribe_cpp

MODEL = r"C:\AI\models\asr\MOSS-Transcribe-Diarize-Q8_0.gguf"

# 选择设备（也可以直接 backend="cuda" 不指定 device）
device = next(d for d in transcribe_cpp.backends()
              if d.kind == "cuda" and d.name == "CUDA0")

# 读取 16kHz/16-bit/mono WAV → float32
with wave.open(r"audio_mono.wav", "rb") as wf:
    pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

result = transcribe_cpp.transcribe(
    MODEL, pcm,
    backend="cuda", device=device,
    language="zh",            # Moss 不支持自动检测，必须显式指定
    timestamps="segment",     # Moss 最大支持 segment 级
    diarize="on",             # 说话人分离
)
print(result.text)                        # 全文
print(result.segments)                    # 带 [t0_ms, t1_ms, speaker_id] 的分段
print(result.speaker_segments)            # 说话人时间段
```

推荐的生产用法（模型常驻、多次调用，**WebUI 应采用这种**）：

```python
import transcribe_cpp as tc

with tc.Model(MODEL, backend="cuda") as model:
    with model.session() as session:
        result = session.run(pcm, language="zh", timestamps="segment", diarize="on")
        print(result.text)
```

---

## 3. 模块级函数

### `transcribe(model, pcm, *, ...) -> Result`

单次调用完成转录。参数与 `Session.run()` 相同并额外接受会话/加载选项：

```python
transcribe(
    model: Model | str | os.PathLike,   # 模型路径（本次调用内加载并释放）或已加载的 Model（复用）
    pcm: PCMLike,                       # 16kHz mono float32，见 §12
    *,
    backend: Backend = "auto",          # 仅当 model 是路径时生效；传 Model 实例时被忽略
    device: BackendDevice | None = None,# 精确设备选择，来自 backends()；同样仅路径模式生效
    n_threads: int = 0,                 # 0 = 家族默认
    kv_type: KVType = "auto",           # KV cache 类型 "auto" | "f32" | "f16"
    n_ctx: int = 0,                     # 0 = 模型默认；调低会缩小 effective_max_audio_ms
    task: Task = "transcribe",
    language: str | None = None,
    target_language: str | None = None, # 翻译目标语言（Moss 不支持）
    timestamps: Timestamps = "auto",
    pnc: Pnc = "default",
    itn: Itn = "default",
    diarize: Diarize = "default",
    keep_special_tags: bool = False,    # True 时保留特殊标记（时间戳 token 等）
    spec_k_drafts: int = -1,            # 投机解码（Moss 不支持，静默忽略）
    family: FamilyExtension | None = None,
) -> Result
```

> 模型加载不便宜：批量/常驻场景请自己持有 `Model` 并调用 `model.session().run(...)`；
> 本函数适合一次性调用。

### `backends() -> list[BackendDevice]`

列出 native 运行时注册的全部计算设备（后端模块加载、优雅降级之后进程真正可用的设备）。
每个设备的 `memory_free` 是调用时刻的快照，轮询显存时重复调用即可。详见 §9。

### `backend_available(backend: Backend) -> bool`

探测 `Model(..., backend=...)` 在本机是否可满足——在加载模型之前就把
"没有 Vulkan 却请求 vulkan"变成明确答案。

### `set_log_callback(handler) -> None`

将 native 日志路由到 `handler(level: int, message: str)`；传 `None` 静默。

- **必须在启动时、加载模型/创建线程之前安装一次**（0.x 契约）。
- handler 可能从 ggml 工作线程被调用，**必须线程安全**——转发到 `logging` 模块或队列，不要做重活。
- level 取值：1=info, 2=warn, 3=error, 4=debug。

### 元信息函数

| 函数 | 返回 | 说明 |
|---|---|---|
| `native_version() -> str` | `"0.2.3"` | 已加载 native 库版本 |
| `native_commit() -> str` | `"63a44d9"` 或 `"unknown"` | 构建所用 git commit |
| `library_path() -> str` | DLL 路径 | 已加载 native 库的文件路径 |
| `native_provider() -> str \| None` | `"transcribe-cpp-native-cu12"` | native 库来自哪个 provider 包；dev-tree / `TRANSCRIBE_LIBRARY` 加载时为 None |
| `__version__` | `"0.2.3"` | Python 包版本 |

### 相关环境变量

- `TRANSCRIBE_BACKEND`：覆盖 `backend="auto"` 的默认选择（显式传 `backend=` 参数永远优先）。
  用于规避某机器上"最优"设备实际有问题（如驱动坏）的场景。

---

## 4. 类型别名（字符串枚举）

所有枚举均为 `typing.Literal` 字符串，直接传字符串即可：

| 别名 | 取值 | 说明 |
|---|---|---|
| `Backend` | `"auto"`, `"cpu"`, `"metal"`, `"vulkan"`, `"cpu_accel"`, `"cuda"`, `"rocm"` | 计算后端 |
| `KVType` | `"auto"`, `"f32"`, `"f16"` | KV cache 精度 |
| `Task` | `"transcribe"`, `"translate"` | Moss 只支持 transcribe |
| `Timestamps` | `"none"`, `"auto"`, `"segment"`, `"word"`, `"token"` | 时间戳粒度，模型能力上限由 `Capabilities.max_timestamp_kind` 决定（Moss 上限 `segment`） |
| `Pnc` | `"default"`, `"off"`, `"on"` | 标点/大小写（Moss 不支持） |
| `Itn` | `"default"`, `"off"`, `"on"` | 逆文本正则化（Moss 不支持） |
| `Diarize` | `"default"`, `"off"`, `"on"` | 说话人分离（Moss 支持，WebUI 传 `"on"`） |
| `SortformerPreset` | `"default"`, `"very_high_latency"`, `"high_latency"`, `"low_latency"` | Sortformer 专用 |
| `CommitPolicy` | `"auto"`, `"on_finalize"`, `"stable_prefix"` | 流式提交策略 |
| `Feature` | `"initial_prompt"`, `"temperature_fallback"`, `"long_form"`, `"cancellation"`, `"pnc"`, `"itn"`, `"diarization"` | 供 `Model.supports()` 查询的行为特性 |

非法取值抛 `InvalidArgument`（错误信息会列出全部合法值）。

---

## 5. Model — 已加载模型

```python
Model(path: str | os.PathLike, *, backend: Backend = "auto",
      device: BackendDevice | None = None)
```

跨线程共享同一个 Model 做查询/建会话是安全的；**Model 必须活得比它的所有 Session 长**。
已知 0.x 限制：一个 Model 的所有 Session **同时只能有一个 run/stream 在跑**（详见 §13）。

### 属性

| 属性 | 类型 | 说明 |
|---|---|---|
| `arch` | `str` | 模型架构，如 `"moss"` |
| `variant` | `str` | 变体，如 `"moss-transcribe-diarize"` |
| `backend` | `str` | 实际使用的后端，如 `"CUDA0"` |
| `device` | `BackendDevice` | 模型运行的设备；`memory_free` 是实时快照，可反复读取以轮询模型加载后剩余显存。无设备时抛 `BackendError` |
| `capabilities` | `Capabilities` | 能力集合，见 §8 |

### 方法

| 方法 | 说明 |
|---|---|
| `supports(feature: Feature) -> bool` | 是否暴露某行为特性（initial_prompt / temperature_fallback / long_form / cancellation / pnc / itn / diarization） |
| `accepts(options: FamilyExtension) -> bool` | 是否接受某家族扩展（Moss 对所有扩展返回 False） |
| `tokenize(text: str) -> list[int]` | 将 UTF-8 文本编码为模型词表 id（无 BOS/EOS/特殊 tag）。无 encode 路径的家族抛 `NotImplementedByModel` |
| `session(*, n_threads=0, kv_type="auto", n_ctx=0) -> Session` | 创建转录会话，见 §6 |
| `close() -> None` | 释放模型；仍开着的 Session 会先被关闭（任何顺序下显式 close 都安全） |

支持 `with` 上下文管理器；`__del__` 兜底调用 `close()`。

---

## 6. Session — 转录会话

```python
Session(model: Model, *, n_threads: int = 0, kv_type: KVType = "auto", n_ctx: int = 0)
```

绑定到一个 Model 的转录上下文，**非线程安全**。0.x 中同一 Model 的多个 Session 也不能并发 run（共享计算后端）——要么串行交替，要么每个 worker 一个 Model。

### `run(pcm, *, ...) -> Result`

```python
run(
    pcm: PCMLike,                        # 16kHz mono float32，见 §12
    *,
    task: Task = "transcribe",
    language: str | None = None,         # Moss 必须显式给 "zh"/"en"
    target_language: str | None = None,
    timestamps: Timestamps = "auto",
    pnc: Pnc = "default",
    itn: Itn = "default",
    diarize: Diarize = "default",        # WebUI 场景传 "on"
    keep_special_tags: bool = False,
    spec_k_drafts: int = -1,             # -1 家族默认 / 0 禁用 / >0 draft 长度；不支持的模型静默忽略
    family: FamilyExtension | None = None,
) -> Result
```

转录并返回完整物化的 `Result`。当因 `cancel()` 抛 `Aborted`、或生成预算用尽抛
`OutputTruncated` 时，**部分转录结果保留在异常的 `partial_result` 属性上**。

### `run_batch(pcms, *, ..., return_exceptions=False) -> list[Result | TranscribeError]`

一次调度转录多条语音，每条各得一个 `Result`。参数与 `run()` 相同（无 `pcm`，改为
`pcms: Sequence[PCMLike]`，另加 `return_exceptions`）。

- 有批量计算路径的家族会在单次设备 dispatch 中处理全部语音（GPU 闲时约 2 倍吞吐）；
  其余家族逐条跑，**任何模型都接受此调用**（Moss 走逐条回退）。
- 失败按**每条语音**报告：默认抛出第一条失败的异常（带 `utterance_index`、尽可能附
  `partial_result`、`batch_results` 携带完整的逐条视图）；`return_exceptions=True`
  时直接返回 `Result`/`TranscribeError` 混合列表（`asyncio.gather` 惯例），已完成的工作不丢失。
- `cancel()` 在 batch 层面暴露，但已完成的语音片段仍保留在结果视图中。

### `stream(*, ...) -> Stream`

开始流式转录，返回 `Stream`。要求 `capabilities.supports_streaming`，否则抛
`NotImplementedByModel`。**Moss 不支持流式，WebUI 不用考虑此接口**（文档保留供换模型时参考，见 §7）。

### 其他成员

| 成员 | 说明 |
|---|---|
| `cancel() -> None` | 从另一线程请求取消进行中的 run/stream；活动调用在下一个 chunk/decode 边界中止并抛 `Aborted`（附 `partial_result`）。标志在下一次 run/stream 开始时自动清除 |
| `was_aborted -> bool` | 最近一次调用是否被 `cancel()` 结束 |
| `limits -> SessionLimits` | 本会话生效的限制（模型上界被 `n_ctx` 收窄后的值）。事先查 `effective_max_audio_ms` 以确定输入长度上限，而不是事后撞 `InputTooLong` |
| `close() -> None` | 关闭会话；支持 `with` 与 `__del__` 兜底 |

---

## 7. Stream — 流式转录

> Moss 不支持流式（`supports_streaming=False`），此节仅供更换模型时参考。
> 通过 `Session.stream(...)` 获得，本身作为上下文管理器使用：

```python
with session.stream(language="zh", timestamps="none",
                    commit_policy="auto", stable_prefix_agreement_n=0) as stream:
    for chunk in audio_chunks:              # 16kHz mono float32 分块
        update = stream.feed(chunk)         # -> StreamUpdate（变更元数据）
        txt = stream.text()                 # -> StreamText（committed/tentative 视图）
    update = stream.finalize()              # 音频结束，冲刷最终假设
    result = stream.snapshot()              # -> Result（当前假设的完整结构化快照）
```

`Session.stream()` 完整签名：

```python
stream(*, task="transcribe", language=None, target_language=None,
        timestamps="none", pnc="default", itn="default", diarize="default",
        keep_special_tags=False, commit_policy="auto",
        stable_prefix_agreement_n=0, family=None) -> Stream
```

### Stream 成员

| 成员 | 说明 |
|---|---|
| `feed(pcm: PCMLike) -> StreamUpdate` | 喂入一块 16kHz mono float32 PCM，返回本次调用的变更元数据 |
| `finalize() -> StreamUpdate` | 通知音频结束，冲刷最终假设 |
| `text() -> StreamText` | 当前 committed / tentative / full 三个文本视图（自有拷贝） |
| `snapshot() -> Result` | 当前假设的完整结构化快照（自有拷贝） |
| `state -> str` | `"idle"` / `"active"` / `"finished"` / `"failed"` |
| `revision -> int` | 修订号 |
| `last_status -> TranscribeError \| None` | 流的终态失败原因；`state == "failed"` 时查看 |
| `reset() -> None` | 将会话归还 idle、丢弃流状态；幂等。上下文管理器退出时自动调用 |

---

## 8. 结果对象（不可变 dataclass）

全部为 `@dataclass(frozen=True)`，不持有任何 native 指针——所有字符串和行数据在返回前
已从会话拷出，**在后续 run 之后仍然有效**，可安全缓存/跨线程传递。

### `Result` — 一次完整转录

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 后处理后的最终全文 |
| `raw_text` | `str` | 家族后处理（说话人标记、时间戳/特殊 token、tag 过滤、空白修剪）之前的解码输出；输出干净文本的家族里与 `text` 仅空白差异 |
| `language` | `str` | 检测/使用的语言 |
| `timestamp_kind` | `str` | 实际返回的时间戳粒度 |
| `segments` | `tuple[Segment, ...]` | 分段列表 |
| `speaker_segments` | `tuple[SpeakerSegment, ...]` | 说话人时间段（diarization 开启时） |
| `words` | `tuple[Word, ...]` | 词级结果（取决于 timestamps 粒度与模型能力） |
| `tokens` | `tuple[Token, ...]` | token 级结果（同上） |
| `timings` | `Timings` | 耗时统计 |

### `Segment` — 一个转录分段

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 分段文本 |
| `t0_ms` / `t1_ms` | `int` | 起止时间（毫秒） |
| `first_word` / `n_words` | `int` | 在 `Result.words` 中的起始下标与数量 |
| `first_token` / `n_tokens` | `int` | 在 `Result.tokens` 中的起始下标与数量 |
| `speaker_id` | `int` | 该段归属的说话人编号 |

### `SpeakerSegment` — 一次说话人轮次

| 字段 | 类型 | 说明 |
|---|---|---|
| `t0_ms` / `t1_ms` | `int` | 起止毫秒；模型只归属文本不提供说话人时间时为 0 |
| `speaker_id` | `int` | 说话人编号 |
| `p` | `float` | 置信度；不可用时为 NaN |

### `Word` — 词级结果

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 词文本 |
| `t0_ms` / `t1_ms` | `int` | 起止毫秒 |
| `seg_index` | `int` | 所属分段下标 |
| `first_token` / `n_tokens` | `int` | 在 `Result.tokens` 中的范围 |

### `Token` — token 级结果

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` / `id` | `str` / `int` | 文本与词表 id |
| `p` | `float` | 概率 |
| `t0_ms` / `t1_ms` | `int` | 起止毫秒 |
| `seg_index` / `word_index` | `int` | 所属分段/词下标 |

### `Timings` — 耗时（毫秒，float）

`load_ms` / `mel_ms` / `encode_ms` / `decode_ms`

### `Capabilities` — 模型能力

| 字段 | 说明 |
|---|---|
| `native_sample_rate: int` | 原生采样率（16 kHz） |
| `languages: tuple[str, ...]` | 支持的语言列表 |
| `max_timestamp_kind: str` | 支持的最大时间戳粒度 |
| `supports_language_detect / supports_translate / supports_streaming / supports_spec_decode: bool` | 各项能力开关 |
| `max_audio_ms: int` | 单次输入时长上限；0 表示无界（Moss 报 0，实际会话限制见 `SessionLimits`） |
| `translate_target_languages: tuple[str, ...]` | 翻译目标语言列表 |

### `SessionLimits` — 会话生效限制

| 字段 | 说明 |
|---|---|
| `effective_n_ctx: int` | 生效上下文长度 |
| `effective_max_audio_ms: int` | **本会话**强制执行的输入时长上限（反映被 `n_ctx` 收窄后的值）；0 表示无界 |
| `max_kv_bytes: int` | KV cache 字节上限 |

### `StreamUpdate` — 流式每次调用的变更元数据

`result_changed: bool`、`is_final: bool`、`revision: int`、`input_received_ms: int`、
`audio_committed_ms: int`、`buffered_ms: int`、`committed_changed: bool`、`tentative_changed: bool`

### `StreamText` — 流式文本视图

| 字段/属性 | 说明 |
|---|---|
| `committed: str` | 只追加、稳定 |
| `tentative: str` | 易变的后缀 |
| `display: str`（property） | `committed + tentative`，UI 应显示的内容 |
| `full: str` | 原始模型假设（修订后可能不等于 `committed + tentative`） |

---

## 9. BackendDevice — 计算设备

`@dataclass(frozen=True, eq=False)`，代表一个已注册的计算设备。相等性比较的是 native 身份
（内部句柄），`index` 与内存快照不影响"是否同一设备"。

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `str` | 设备名，如 `"CUDA0"`、`"CPU"` |
| `description` | `str` | 人读描述 |
| `kind` | `str` | `"cpu"` / `"accel"` / `"metal"` / `"vulkan"` / `"cuda"` / `"rocm"` / `"sycl"` / `"gpu"` / `"unknown"` |
| `device_type` | `str` | 厂商无关分类：`"cpu"` / `"gpu"` / `"igpu"` / `"accel"` / `"unknown"` |
| `device_id` | `str \| None` | 稳定硬件 id（PCI bus id）；如 Metal 无则为 None。**应用持久化应存这个，不要存 `_handle` 或 `index`** |
| `memory_total` | `int` | 字节；未报告为 0 |
| `memory_free` | `int` | 查询时刻快照；轮询需重查（`backends()` 或 `Model.device`）。不同 kind 之间不可比 |
| `index` | `int \| None` | 注册表序号（仅显示用），进程内有效、驱动更新后不稳定 |

---

## 10. FamilyExtension — 模型家族扩展选项

按模型家族携带的专属参数，经 `Session.run(family=...)` / `Session.stream(family=...)`
传入。传入时先探测模型是否接受（`Model.accepts()`），不接受则抛 `UnsupportedRequest`。
**Moss 不接受任何扩展**——以下供换模型时参考。

| 类 | slot | 参数 | 说明 |
|---|---|---|---|
| `WhisperRunOptions` | run | `initial_prompt`, `condition_on_prev_tokens`, `temperature`, `temperature_inc`, `compression_ratio_thold`, `logprob_thold`, `no_speech_thold`, `max_prev_context_tokens`, `seed`, `max_initial_timestamp` | Whisper 的初始提示/温度回退/解码阈值；只覆盖显式设置的字段 |
| `MoonshineStreamingOptions` | stream | `min_decode_interval_ms` | Moonshine 流式 |
| `ParakeetStreamOptions` | stream | `att_context_right` | Parakeet cache-aware 流式 |
| `ParakeetBufferedStreamOptions` | stream | `left_ms`, `chunk_ms`, `right_ms` | Parakeet 分块注意力缓冲流式；None 保留家族默认（C 哨兵 -1） |
| `VoxtralRealtimeStreamOptions` | stream | `num_delay_tokens`, `min_decode_interval_ms` | Voxtral 实时流式 |
| `SortformerStreamOptions` | run | `preset: SortformerPreset` | Sortformer 是纯 diarizer（run 只产 speaker segments 无文本）；preset 选延迟/精度档位：`"very_high_latency"`（~30s lookahead，离线档）/ `"high_latency"` / `"low_latency"`（~1s，实时档，算力开销显著增大）/ `"default"` |

slot 不匹配（run 扩展传给 stream 或反之）抛 `InvalidArgument`。

---

## 11. 异常层次

所有异常继承自 `TranscribeError(RuntimeError)`：

```
TranscribeError                     # 基类；.status: int（native 状态码，纯 Python 侧错误为 0）
                                    #        .utterance_index: int|None（仅 run_batch 逐条失败时设置）
├── InvalidArgument                 # 非法参数（含 PCM 格式错误、采样率不符、枚举值非法）
├── NotImplementedByModel           # 模型无此能力（如 Moss 调 stream()、tokenize 无 encode 路径）
├── ModelFileNotFound               # 模型文件不存在
├── ModelLoadError                  # GGUF 解析失败 / 不支持的 arch / variant
├── OutOfMemory                     # OOM
├── BackendError                    # 后端错误（如模型无解析出的计算设备、无可用后端）
├── UnsupportedRequest              # 模型不支持的 task / language / 时间戳粒度 / pnc / itn
├── AbiError                        # 调用方结构体布局与库不匹配（struct_size）
├── InputTooLong                    # 输入超过会话上限（先用 Session.limits 检查）
├── Aborted                         # 被 Session.cancel() 中止
│                                   #   .partial_result: Result|None —— 中止前已完成部分的转录
└── OutputTruncated                 # 生成预算耗尽，转录按契约不完整
                                    #   .partial_result: Result|None —— 始终保留的部分结果
```

`run_batch` 抛出的异常额外携带 `batch_results`（逐条 `Result | TranscribeError` 列表），
已完成的工作不会丢失。

---

## 12. PCM 输入格式要求

**所有音频输入必须是 16 kHz、单声道、float32**（缩放到 ±1.0）。多声道请先下混：
`(frames, channels)` 的 numpy 数组用 `audio.mean(axis=1).astype("float32")`——
传 2-D 数组会被 `InvalidArgument` 明确拒绝（而不是转录出静音垃圾）。

`PCMLike` 接受的形态（按优先顺序）：

| 形态 | 处理方式 |
|---|---|
| `ctypes` float 数组 | 直接使用 |
| `bytes` / `bytearray` / `memoryview` | 需为 C 连续、1-D；`format == "f"` 直接拷贝；**itemsize 为 1 的原始字节按小端 float32 解释**（长度必须是 4 的倍数）；其他格式（如 float64）拒绝 |
| `Sequence[float]`（含 float32 1-D numpy 数组） | 逐元素转 float32 |

空缓冲抛 `InvalidArgument`。常见转换：

```python
# 16-bit PCM WAV
pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
# 其他采样率/声道，先重采样（外部完成）
# ffmpeg -i in.wav -ar 16000 -ac 1 -f f32le out.f32
```

---

## 13. 线程与并发

- **GIL**：耗时 native 调用（模型加载、run）期间释放 GIL（ctypes 对外部调用一律如此），
  推理时其他 Python 线程可继续推进。
- **Model**：跨线程共享做查询/建会话安全；必须活得比其 Session 长。
- **0.x 串行限制**：一个 Model 的所有 Session **同时只能有一个 run/stream 在飞**——
  Session 共享模型的计算后端，重叠执行会竞争。WebUI 多请求并发时：用一把锁把 run 串行化
  （排队），或每个 worker 各加载一个 Model 实现真并行。
- **Session**：非线程安全；同一 Session 同时至多一个流。
- `Session.cancel()` 是专为跨线程设计的：从请求处理线程调用，推理线程里的 run 会在
  下一个 chunk/decode 边界抛出 `Aborted` 并带上 `partial_result`。

---

## 14. WebUI 集成建议

结合 Moss 部署的实测能力，给前/后端设计的落地建议：

1. **模型常驻**：服务启动时加载一次 `Model`（首次加载有可观耗时，`Timings.load_ms` 可观测），
   每个请求 `model.session()` 新建会话。绝不要每请求 `transcribe(path, ...)`。
2. **请求排队**：一把全局锁串行化所有 `session.run(...)`（§13 的 0.x 限制）；
   后端维护任务队列，前端轮询或 SSE 推送进度/结果。
3. **音频预处理**：上传任意格式 → 后端统一转 16 kHz mono float32（numpy 重采样，或调
   ffmpeg）。文件超长约 2.9 小时（`SessionLimits.effective_max_audio_ms=10458400`）
   会抛 `InputTooLong`，应在上传时用 `session.limits` 预检并提示。
4. **参数固定项**：`timestamps="segment"`（上限）、`diarize="on"`、`task="transcribe"`；
   `language` 由用户在 `zh`/`en` 中**必选**（无自动检测）。
5. **取消功能**：Moss 支持 cancellation——长音频转录时可提供"停止"按钮，
   另一线程调 `session.cancel()`，捕获 `Aborted` 后把 `exc.partial_result` 作为部分结果返回。
6. **说话人展示**：用 `Result.segments`（每段带 `speaker_id` + `t0_ms/t1_ms`）渲染
   分说话人的时间轴/字幕；`speaker_segments` 可画说话人时间条（注意 `p` 可能为 NaN）。
7. **设备选择**：设置页列出 `backends()` 供用户选 CUDA/Vulkan/CPU，保存 `device_id`
   （稳定标识）而非 `index`；`model.device.memory_free` 可做显存余量展示。
8. **日志**：启动时 `set_log_callback()` 接到 `logging`（一次性、在任何模型加载前安装，
   handler 必须线程安全）。
9. **错误映射**：`ModelFileNotFound`/`ModelLoadError` → 配置错误提示；
   `UnsupportedRequest`/`InvalidArgument` → 请求参数校验提示；`Aborted` → 用户取消；
   `InputTooLong` → 时长超限提示；其余 `TranscribeError` → 通用失败（可带 `.status`）。
