@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ============================================================
echo   Gravity Harness Fix - Live Telemetry ^& Full Transcript Audit
echo ============================================================
echo.

call "%SCRIPT_DIR%\scripts\_find_python.bat"
if not defined PYTHON_CMD (
    echo [ERROR] Python 3 not found on PATH.
    if "%NO_PAUSE%"=="" pause
    exit /b 1
)

"%PYTHON_CMD%" -X utf8 "%SCRIPT_DIR%\plugin\skills\gravity-session-doctor\scripts\inspect_logs.py" --logs-dir "%SCRIPT_DIR%\logs" --tail 25
echo.
echo Running forensic scan across all .gemini conversation logs...
echo.
"%PYTHON_CMD%" -X utf8 "%SCRIPT_DIR%\scripts\audit_transcripts.py" --json-out "%SCRIPT_DIR%\docs\raw_audit.json"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%NO_PAUSE%"=="" pause
exit /b %EXIT_CODE%
