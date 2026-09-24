@echo off
setlocal
set "SCRIPT=%~dp0transcribe.py"
set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" goto novenv
"%PY%" "%SCRIPT%" %*
endlocal & exit /b %ERRORLEVEL%
:novenv
where python >nul 2>nul
if errorlevel 1 goto nopy
python "%SCRIPT%" %*
endlocal & exit /b %ERRORLEVEL%
:nopy
py "%SCRIPT%" %*
endlocal & exit /b %ERRORLEVEL%
