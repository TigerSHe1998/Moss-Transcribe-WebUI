@echo off
rem Moss 转录 WebUI 启动脚本
rem   仅本机访问:  run_webui.bat
rem   局域网访问:  run_webui.bat --host 0.0.0.0   （首次需在防火墙放行 8390 端口）
cd /d "%~dp0"
.venv\Scripts\python.exe webui\server.py %*
pause
