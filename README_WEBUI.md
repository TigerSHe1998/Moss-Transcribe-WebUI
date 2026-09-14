# Moss 转录 WebUI

基于本地 `transcribe.cpp`（Moss-Transcribe-Diarize 模型）的轻量语音转写 Web 界面，
支持时间戳分段与说话人分离。

## 启动

```bat
run_webui.bat                    :: 仅本机访问 http://127.0.0.1:8390
run_webui.bat --host 0.0.0.0     :: 暴露给局域网（首次需在 Windows 防护墙放行 8390 端口）
```

常用参数：`--port`、`--model`（GGUF 路径）、`--backend cuda|cpu|vulkan`、`--device-index`。

## 功能

- 上传任意音频/视频，自动调用本机 ffmpeg 转码为 16kHz 单声道（视频抽音轨、重采样、下混）
- 说话人分离 + 分段时间戳；结果可查看 / 复制 / 导出 TXT、SRT、JSON
- 推理设备（CUDA / Vulkan / CPU）在页面内切换，切换会重载模型（等待当前任务完成）
- 设置项：语言（zh/en）、时间戳粒度、说话人分离、KV 缓存类型、CPU 线程数、n_ctx、保留特殊标记
- 任务队列串行执行（transcribe.cpp 0.x 限制），支持取消（保留部分结果）
- 音频超过模型单次上限（约 2.9 小时）会直接拒绝，请自行裁剪

## 说明

- 依赖（fastapi / uvicorn / python-multipart / numpy / transcribe-cpp）已装入 `.venv`
- 未安装 ffmpeg 时仅支持 16kHz 单声道 16-bit PCM WAV
- 任务结果保存在内存中，服务重启后清空；上传文件在 `uploads/`，随任务删除自动清理
- 接口详情见 [transcribe_cpp_api.md](transcribe_cpp_api.md)
