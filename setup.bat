@echo off
setlocal
set PYTHON=python

echo ====================================================
echo   Iron Dome Missile Tracker v3 - AUTOMATIC SETUP
echo ====================================================
echo.

REM 1. Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python from python.org
    pause
    exit /b 1
)

REM 2. Create Virtual Environment
echo [1/2] Creating Virtual Environment (.venv)...
if exist ".venv" (
    echo [INFO] .venv already exists. Skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

REM 3. Install Requirements
echo [2/2] Installing dependencies (this may take a few minutes)...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements!
    pause
    exit /b 1
)

echo.
echo ====================================================
echo   SETUP COMPLETE!
echo ====================================================
echo.
echo Your environment is ready. To track missiles, run:
echo   .\run.bat track --video data\videos\Iron_Dome.mp4
echo.
echo NOTE: If you need to download the training dataset later, run:
echo   .\run.bat train (or python scripts\download_data.py)
echo.
pause
