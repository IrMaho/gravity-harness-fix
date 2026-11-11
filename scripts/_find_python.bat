@echo off
set "PYTHON_CMD="
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo "%%P" | findstr /I "WindowsApps" >nul
    if errorlevel 1 (
        set "PYTHON_CMD=%%P"
        goto :eof
    )
)
for %%P in (
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do (
    if exist %%P (
        set "PYTHON_CMD=%%~P"
        goto :eof
    )
)
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON_CMD=%%P"
)
goto :eof

