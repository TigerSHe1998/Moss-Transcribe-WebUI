@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo  Moss Transcribe WebUI - environment setup
echo ================================================
echo.

rem ---- 1. locate python ----
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3.10+ from https://www.python.org/
    echo         and make sure it is added to PATH, then rerun.
    goto :fail
)
echo [1/4] Using Python: %PY%

rem ---- 2. create venv (skip if it already exists) ----
if exist ".venv\Scripts\python.exe" (
    echo [2/4] .venv already exists, reusing it.
) else (
    echo [2/4] Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto :fail
    )
)
set "VENV_PY=.venv\Scripts\python.exe"

rem ---- 3. install PyPI packages ----
echo [3/4] Installing packages from PyPI (fastapi uvicorn python-multipart numpy transcribe-cpp) ...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] pip self-upgrade failed. Check your network / proxy.
    goto :fail
)
"%VENV_PY%" -m pip install fastapi uvicorn python-multipart numpy transcribe-cpp
if errorlevel 1 (
    echo [ERROR] Failed to install PyPI packages. Check your network / proxy.
    goto :fail
)

rem ---- 4. install local native wheel ----
set "WHEEL="
for %%f in ("resources\whl\transcribe_cpp_native_cu12-*.whl") do set "WHEEL=%%f"
if not defined WHEEL (
    echo [ERROR] No transcribe_cpp_native_cu12-*.whl found in resources\whl\
    echo         Put the wheel there first.
    goto :fail
)
echo [4/4] Installing local wheel: %WHEEL%
"%VENV_PY%" -m pip install --force-reinstall "%WHEEL%"
if errorlevel 1 (
    echo [ERROR] Failed to install the native wheel.
    goto :fail
)

rem ---- verify imports quickly ----
"%VENV_PY%" -c "import transcribe_cpp, fastapi, uvicorn, numpy; print('import check OK:', transcribe_cpp.__version__)"
if errorlevel 1 (
    echo [ERROR] Import check failed. See the message above.
    goto :fail
)

echo.
echo ================================================
echo  Setup complete!
echo  Start the server with: run_webui.bat
echo ================================================
goto :end

:fail
echo.
echo Setup FAILED - see the errors above.

:end
pause
endlocal
