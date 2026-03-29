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

REM ===========================================================================
REM |                   IRON DOME TRACKER CONTROL PANEL                       |
REM ===========================================================================
REM | Adjust these values to tune the system without touching Python code     |
REM ===========================================================================

REM --- Night Flame Detector ---
REM BRIGHT_THRESH: (150-200) Lower = more sensitive (captures dim exhaust), Higher = cleaner.
SET BRIGHT_THRESH=160
REM MIN_FLAME: (3-15) Min pixel area. Lower for tiny/distant missiles, Higher to ignore noise.
SET MIN_FLAME=3
REM MAX_FLAME: (50000-200000) Prevents tracking massive explosions or screen-flares.
SET MAX_FLAME=150000
REM EDGE_MARGIN: (0.02-0.10) Screen % to ignore at edges. Removes TV logos/text.
SET EDGE_MARGIN=0.06
REM MAX_ASPECT: (2.0-8.0) Rejects long flat bars. Missile flames are usually sharp dots.
SET MAX_ASPECT=6.0
REM GROUND_FRAC: (0.50-0.90) 0.70 means ignore the bottom 30% of frame (city lights).
SET GROUND_FRAC=0.75

REM --- Static Light Filter ---
REM STATIC_GRID: (20-60) Precision of the filter. Smaller = more precise grid.
SET STATIC_GRID=20
REM WORLD_THRESH: (5-15) Frames a light must stay fixed to be hidden as a city-light.
SET WORLD_THRESH=9
REM CAM_THRESH: (15-35) Frames a light must stay in screen-coords to be hidden (TV Logos).
SET CAM_THRESH=25
REM STATIC_DECAY: (5-20) Frames it takes the system to 'forget' a static light.
SET STATIC_DECAY=12

REM --- Tracking Logic ---
REM TRAIL_LEN: (10-100) Number of frames to draw for the visual "exhaust trail".
SET TRAIL_LEN=30
REM TRACK_DIST: (50-150) Pixels. Increase if missiles are very fast/close to camera.
SET TRACK_DIST=80
REM TRACK_CONFIRM: (2-5) Frames needed before showing the "LOCK" box.
SET TRACK_CONFIRM=3
REM TRACK_MISSED: (5-30) Frames to 'wait' for a missile if it goes behind clouds.
SET TRACK_MISSED=12

REM --- Sensitivity & Display ---
REM NIGHT_SENS: (40-80) Brightness level to automatically switch to Night Mode.
SET NIGHT_SENS=60
REM DEF_FILTER: The default filter used at night. Options: thermal, nvg, original.
SET DEF_FILTER=thermal

REM ===========================================================================

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
%PYTHON% src\missile_tracker.py ^
    --bright-thresh %BRIGHT_THRESH% ^
    --min-flame-area %MIN_FLAME% ^
    --max-flame-area %MAX_FLAME% ^
    --edge-margin %EDGE_MARGIN% ^
    --max-aspect-ratio %MAX_ASPECT% ^
    --ground-fraction %GROUND_FRAC% ^
    --static-grid %STATIC_GRID% ^
    --static-world-thresh %WORLD_THRESH% ^
    --static-cam-thresh %CAM_THRESH% ^
    --static-decay %STATIC_DECAY% ^
    --trail-length %TRAIL_LEN% ^
    --track-max-dist %TRACK_DIST% ^
    --track-confirm %TRACK_CONFIRM% ^
    --track-missed %TRACK_MISSED% ^
    --night-sensitivity %NIGHT_SENS% ^
    --default-filter %DEF_FILTER% ^
    %REMAINING%
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
echo   --bright-thresh 160     Lower = more sensitive to dim flames
echo   --min-flame-area 4      Minimum pixel area for flame blob
echo   --night-sensitivity 80  Brightness threshold for auto night switch
echo.
echo NOTE: All parameters can also be tuned directly in the 'run.bat' Control Panel.
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
