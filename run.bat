setlocal
set PYTHON=python

REM 1. Check for virtual environment in the current directory
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [ENV] Using virtual environment: .venv
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
    echo [ENV] Using virtual environment: venv
) else (
    echo [ENV] No local virtual environment found. Using system 'python'.
    echo [ENV] TIP: Run 'python -m venv .venv' and Pip install requirements for best results.
)

echo ====================================================
echo   Iron Dome Missile Tracker v3
echo   Day: YOLO shape detection
echo   Night: YOLO + Flame/Propellant Exhaust detection
echo   Current Python: %PYTHON%
echo ====================================================
echo.

if "%~1"=="track" goto :track
if "%~1"=="train" goto :train
goto :usage

:track
echo [ACTION] Starting Iron Dome Missile Tracker v3...
for /f "tokens=1,* delims= " %%a in ("%*") do set REMAINING=%%b
%PYTHON% src\missile_tracker.py %REMAINING%
goto :EOF

:train
echo [ACTION] Starting YOLO26 Training on Custom Dataset...
%PYTHON% scripts\train_yolo26.py
goto :EOF

:usage
echo Usage:
echo   run.bat track --video data\videos\video.mp4                   -- Auto day/night
echo   run.bat track --video data\videos\video.mp4 --night           -- Force night mode
echo   run.bat track --video data\videos\video.mp4 --day             -- Force day mode
echo   run.bat track --video data\videos\video.mp4 --save            -- Save output_tracked.mp4
echo   run.bat track --cam 0 --night                     -- Night mode on webcam
echo.
echo Night Flame Detector tuning:
echo   --bright-thresh 160     Lower = more sensitive to dim flames (default: 170)
echo   --min-flame-area 4      Minimum pixel area for flame blob (default: 5)
echo   --night-sensitivity 80  Brightness threshold for auto night switch (default: 60)
echo.
echo Examples:
echo   run.bat track --video data\videos\Iron_Dome.mp4 --weights models\missile.pt
echo   run.bat track --video data\videos\Iron_Dome.mp4 --night --weights models\missile.pt
echo   run.bat track --video data\videos\Iron_Dome.mp4 --night --bright-thresh 170 --weights models\missile.pt
echo   run.bat track --video data\videos\Iron_Dome.mp4 --save --weights models\missile.pt
echo.
echo Training:
echo   run.bat train           -- Starts YOLO26 training on the new dataset
echo.
echo Controls in window:
echo   Q = Quit   P = Pause/Resume   N = Toggle Night/Day   S = Screenshot
echo.
echo Legend:
echo   YOLO:N  = missile shape detections (works in daylight)
echo   FLAME:N = propellant flame / exhaust dot detections (works at night)

REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\missile.pt
REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\yolo26n_custom.pt

