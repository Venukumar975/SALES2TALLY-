@echo off
echo ==============================================================
echo  Excel Header Mapper ^& Register Generator Startup Script
echo ==============================================================
echo.

cd /d "%~dp0"

if not exist .venv (
    echo [INFO] Creating Python Virtual Environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Is Python installed and in PATH?
        pause
        exit /b 1
    )
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate

echo [INFO] Ensuring dependencies are installed...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [INFO] Starting Web App...
echo [INFO] Please open your browser and navigate to http://localhost:5005
echo.

python app.py

pause
