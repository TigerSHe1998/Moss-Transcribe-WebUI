# Moss 转录 WebUI

基于本地 `transcribe.cpp`（Moss-Transcribe-Diarize 模型）的轻量语音转写 Web 界面，
支持时间戳分段与说话人分离。

## 启动

```bat
run_webui.bat          :: 本机访问 http://127.0.0.1:8390
```

常用参数：`--port`、`-m/--model`（GGUF 路径，默认 `model/` 下随仓库的模型）。
默认仅绑定 127.0.0.1；如需局域网访问请自行评估安全风险后再绑定与放行。

## 功能

- 上传任意音频/视频，自动调用本机 ffmpeg 转码为 16kHz 单声道（视频抽音轨、重采样、下混）
- 说话人分离 + 分段时间戳；结果可查看 / 复制 / 导出 TXT、SRT、JSON
- 结果卡片内置回听播放器：播放/暂停、进度条拖拽、按进度高亮对应文本、分段条目一键跳播
- 推理设备（CUDA / Vulkan / CPU）在页面内切换：无任务进行时立即重载，有任务时需等任务结束
- 设置项：时间戳粒度、说话人分离、KV 缓存类型、CPU 线程数、n_ctx
- 任务队列串行执行（transcribe.cpp 0.x 限制），支持取消（保留部分结果）
- 音频超过模型单次上限（约 2.9 小时）会直接拒绝，请自行裁剪
- 模型权重放 `model/`（gitignore），换模型用 `-m` 指定路径

## 说明

- 依赖（fastapi / uvicorn / python-multipart / numpy / transcribe-cpp）已装入 `.venv`
- 未安装 ffmpeg 时仅支持 16kHz 单声道 16-bit PCM WAV
- 任务结果保存在内存中，服务重启后清空；上传文件在 `uploads/`，随任务删除自动清理
- 接口详情见 [transcribe_cpp_api.md](transcribe_cpp_api.md)
