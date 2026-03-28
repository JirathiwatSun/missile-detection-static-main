@echo off
REM ============================================================
REM  Iron Dome Missile Tracker v3 — Day/Night Launcher
REM  Day mode  : YOLO shape detection
REM  Night mode: YOLO shape + Flame/Exhaust dot detection
REM ============================================================

set PYTHON=C:\Users\jirat\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\python.exe

echo ====================================================
echo   Iron Dome Missile Tracker v3
echo   Day: YOLO shape detection
echo   Night: YOLO + Flame/Propellant Exhaust detection
echo   Python: %PYTHON%
echo ====================================================
echo.

if "%~1"=="track" goto :track
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
echo   --bright-thresh 180     Lower = more sensitive to dim flames (default: 200)
echo   --min-flame-area 4      Minimum pixel area for flame blob (default: 8)
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

REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\missile.pt --bright-thresh 170
