@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

call "%SCRIPT_DIR%\scripts\_find_python.bat"
if not defined PYTHON_CMD (
    echo [ERROR] Python 3 not found on PATH.
    exit /b 1
)

if "%~1"=="" (
    echo Usage:
    echo   agile-worktree.bat create ^<repo_path^> ^<slice1^> [slice2 ...]
    echo   agile-worktree.bat list ^<repo_path^>
    echo   agile-worktree.bat cleanup ^<repo_path^> [--delete-branches] [--force]
    exit /b 0
)

"%PYTHON_CMD%" -X utf8 "%SCRIPT_DIR%\plugin\skills\agile-swarm\scripts\worktree_team.py" %*
exit /b %ERRORLEVEL%

