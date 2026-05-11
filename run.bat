@echo off
REM English Coach Agent - Windows Launcher
REM Double-click this file to start the agent

cd /d "%~dp0"

REM Check if venv exists, if not run setup
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running setup...
    python setup.py
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Setup failed. Please check the errors above.
        pause
        exit /b 1
    )
)

REM Activate venv and run
echo.
echo Starting English Coach Agent...
venv\Scripts\python.exe run.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Agent exited with error code %ERRORLEVEL%
    pause
)
