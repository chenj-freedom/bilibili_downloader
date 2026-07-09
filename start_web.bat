@echo off
setlocal
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

where python >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=py -3"
    ) else (
        echo Python was not found. Please install Python 3 and try again.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% scripts\bilibili_web.py
if not %errorlevel%==0 (
    echo.
    echo Web UI stopped with an error.
)
pause
