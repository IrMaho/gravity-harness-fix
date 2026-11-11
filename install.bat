@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ============================================================
echo   Gravity Harness Fix - Installer / Updater
echo ============================================================
echo.

call "%SCRIPT_DIR%\scripts\_find_python.bat"
if not defined PYTHON_CMD (
    echo [ERROR] Python 3 not found on PATH. Please install Python 3.10+ and retry.
    if "%NO_PAUSE%"=="" pause
    exit /b 1
)

echo Using Python: %PYTHON_CMD%
"%PYTHON_CMD%" -X utf8 "%SCRIPT_DIR%\scripts\install_harness.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [SUCCESS] Harness fixes, hooks, always-on rules, and telemetry active.
) else (
    echo [FAILED] Installer exited with code %EXIT_CODE%.
)

if "%NO_PAUSE%"=="" pause
exit /b %EXIT_CODE%
