@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found under %~dp0
    echo          create it first, see README.md or run init_env.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" webui\server.py %*
pause
