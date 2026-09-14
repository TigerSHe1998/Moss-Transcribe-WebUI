@echo off
rem Moss transcription WebUI launcher.
rem NOTE: keep this file ASCII-only with CRLF line endings -
rem       cmd.exe parses .bat in the ANSI codepage and needs CRLF.
rem   Local only : run_webui.bat
rem   LAN access : run_webui.bat --host 0.0.0.0    (allow TCP 8390 in Windows Firewall first)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found under %~dp0
    echo          create it first, see README_WEBUI.md
    pause
    exit /b 1
)
".venv\Scripts\python.exe" webui\server.py %*
pause
