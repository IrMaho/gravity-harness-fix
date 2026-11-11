@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ============================================================
echo   Gravity Harness Fix - Uninstaller
echo ============================================================
echo.

call "%SCRIPT_DIR%\scripts\_find_python.bat"
if not defined PYTHON_CMD (
    echo [ERROR] Python 3 not found on PATH.
    if "%NO_PAUSE%"=="" pause
    exit /b 1
)

"%PYTHON_CMD%" -X utf8 "%SCRIPT_DIR%\scripts\install_harness.py" --uninstall %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%NO_PAUSE%"=="" pause
exit /b %EXIT_CODE%
