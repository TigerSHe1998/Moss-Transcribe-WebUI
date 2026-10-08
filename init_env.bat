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

rem ---- 3. install PyPI packages (versions pinned; keep in sync with the whl) ----
echo [3/4] Installing packages from PyPI (pinned versions) ...
"%VENV_PY%" -m pip install --upgrade "pip==25.2"
if errorlevel 1 (
    echo [ERROR] pip self-upgrade failed. Check your network / proxy.
    goto :fail
)
"%VENV_PY%" -m pip install "fastapi==0.141.1" "uvicorn==0.53.0" "python-multipart==0.0.32" "numpy==2.5.3" "transcribe-cpp==0.3.1"
if errorlevel 1 (
    echo [ERROR] Failed to install PyPI packages. Check your network / proxy.
    goto :fail
)

rem ---- 4. install local native wheel (version must match the binding) ----
set "WHEEL_COUNT=0"
set "WHEEL="
set "WHEEL_NAME="
for %%f in ("resources\whl\transcribe_cpp_native_cu12-*.whl") do (
    set /a WHEEL_COUNT+=1
    set "WHEEL=%%f"
    set "WHEEL_NAME=%%~nf"
)
if %WHEEL_COUNT%==0 (
    echo [ERROR] No transcribe_cpp_native_cu12-*.whl found in resources\whl\
    echo         Put the wheel there first.
    goto :fail
)
if %WHEEL_COUNT% GTR 1 (
    echo [ERROR] Multiple wheels found in resources\whl\ - keep exactly one.
    echo         Remove the old version after upgrading.
    goto :fail
)
echo [4/4] Installing local wheel: %WHEEL%
"%VENV_PY%" -m pip install --force-reinstall "%WHEEL%"
if errorlevel 1 (
    echo [ERROR] Failed to install the native wheel.
    goto :fail
)

rem ---- check binding/wheel version match (mismatch breaks the ABI) ----
set "WHEEL_VER=%WHEEL_NAME:transcribe_cpp_native_cu12-=%"
set "WHEEL_VER=%WHEEL_VER:-py3-none-win_amd64=%"
"%VENV_PY%" -c "import sys, transcribe_cpp; sys.exit(0 if transcribe_cpp.__version__ == '%WHEEL_VER%' else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Version mismatch: transcribe-cpp binding is not %WHEEL_VER%.
    echo         The PyPI binding version (step 3) and the whl in resources\whl\
    echo         must match. Update both together.
    goto :fail
)

rem ---- dependency consistency + import smoke ----
"%VENV_PY%" -m pip check
if errorlevel 1 (
    echo [ERROR] Dependency check failed. See the conflicts above.
    goto :fail
)
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
