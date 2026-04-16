@echo off
setlocal DisableDelayedExpansion

REM ── Python resolver ────────────────────────────────────────────────────────
set PYTHON=python
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [ENV] Using virtual environment: .venv
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
    echo [ENV] Using virtual environment: venv
) else (
    echo [ENV] No local virtual environment found. Using system 'python'.
    echo [ENV] TIP: Run 'python -m venv .venv' and pip install -r requirements.txt
)

REM ── Load config.cfg ────────────────────────────────────────────────────────
REM Reads every KEY=VALUE line from config.cfg, skipping blank lines and
REM lines whose first character is # (comments).
set "CFG=config.cfg"
if not exist "%CFG%" (
    echo [ERROR] Configuration file not found: %CFG%
    echo [ERROR] Please restore config.cfg from the repository.
    pause
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%K in ("%CFG%") do (
    if not "%%K"=="" (
        set "%%K=%%L"
    )
)
echo [CFG] Loaded configuration from %CFG%

REM ── Banner ─────────────────────────────────────────────────────────────────
echo ====================================================
echo   Iron Dome Missile Tracker v3
echo   Day : YOLO shape detection
echo   Night: YOLO + IR Flame / Dim-dot detection
echo   Config: %CFG%
echo   Python: %PYTHON%
echo ====================================================
echo.

if "%~1"=="track" goto :track
if "%~1"=="train" goto :train
if "%~1"=="download-data" goto :download_data
goto :usage

:track
echo [ACTION] Starting Iron Dome Missile Tracker v3...
REM Check if --download-data was passed as a flag within 'track'
for %%x in (%*) do (
    if "%%x"=="--download-data" goto :download_data
)

for /f "tokens=1,* delims= " %%a in ("%*") do set REMAINING=%%b

REM Strip leading/trailing quotes from arguments (support both quoted and unquoted paths)
if defined REMAINING (
    set "REMAINING=%REMAINING:'=%"
    set "REMAINING=%REMAINING:"=%"
)

%PYTHON% src\missile_tracker.py ^
    --weights             "%WEIGHTS%" ^
    --conf                "%CONF%" ^
    --bright-thresh       "%BRIGHT_THRESH%" ^
    --min-flame-area      "%MIN_FLAME%" ^
    --max-flame-area      "%MAX_FLAME%" ^
    --edge-margin         "%EDGE_MARGIN%" ^
    --max-aspect-ratio    "%MAX_ASPECT%" ^
    --ground-fraction     "%GROUND_FRAC%" ^
    --cluster-radius      "%CLUSTER_RADIUS%" ^
    --cluster-max-size    "%CLUSTER_MAX%" ^
    --mog-history         "%MOG_HISTORY%" ^
    --mog-var-thresh      "%MOG_VAR%" ^
    --flame-min-conf      "%FLAME_MIN_CONF%" ^
    --static-grid         "%STATIC_GRID%" ^
    --static-world-thresh "%WORLD_THRESH%" ^
    --static-cam-thresh   "%CAM_THRESH%" ^
    --static-decay        "%STATIC_DECAY%" ^
    --trail-length        "%TRAIL_LEN%" ^
    --track-max-dist      "%TRACK_DIST%" ^
    --track-confirm       "%TRACK_CONFIRM%" ^
    --track-missed        "%TRACK_MISSED%" ^
    --track-coast         "%TRACK_COAST%" ^
    --track-vel-gate      "%VEL_GATE%" ^
    --track-dir-penalty   "%DIR_PENALTY%" ^
    --track-vel-alpha     "%VEL_ALPHA%" ^
    --track-coast-drift   "%COAST_DRIFT%" ^
    --track-box-smooth    "%BOX_SMOOTH%" ^
    --trail-jump-mult     "%TRAIL_JUMP%" ^
    --flash-thresh        "%FLASH_THRESH%" ^
    --flash-cooldown      "%FLASH_COOLDOWN%" ^
    --max-horizon-rise    "%HORIZON_RISE%" ^
    --auto-ground-alpha   "%AUTO_ALPHA%" ^
    --night-sensitivity   "%NIGHT_SENS%" ^
    --default-filter      "%DEF_FILTER%" ^
    --night-conf-offset   "%NIGHT_CONF_OFFSET%" ^
    --cam-motion-thresh   "%CAM_MOTION%" ^
    --below-ground-conf   "%BELOW_GROUND_CONF%" ^
    --yolo-below-ground-conf "%YOLO_GROUND_CONF%" ^
    --device              "%DEVICE%" ^
    %REMAINING%
goto :EOF

:train
echo [ACTION] Starting YOLO26 Training on Custom Dataset...
%PYTHON% scripts\train_yolo26.py
goto :EOF

:usage
echo.
echo  Usage:
echo    .\run.bat track --video data\videos\video.mp4          (auto day/night)
echo    .\run.bat track --video data\videos\video.mp4 --night  (force night mode)
echo    .\run.bat track --video data\videos\video.mp4 --day    (force day mode)
echo    .\run.bat track --video data\videos\video.mp4 --save   (save output_tracked.mp4)
echo    .\run.bat track --cam 0 --night                        (webcam, night mode)
echo.
echo  All default values are configured in: config.cfg
echo  Any flag listed below overrides config.cfg for a single run.
echo.
echo  Key per-run override flags:
echo    --weights PATH           YOLO model weights
echo    --conf 0.27              YOLO confidence threshold
echo    --device 0               GPU device (0 = primary GPU, cpu = CPU-only)
echo    --bright-thresh 120      IR global brightness threshold
echo    --ground-fraction 0.70   Initial horizon fraction
echo    --auto-ground-alpha 0.10 Auto-horizon EMA speed
echo    --night-sensitivity 60   Brightness level for auto night/day switch
echo    --track-confirm 3        Frames before target lock is displayed
echo    --track-missed 12        Frames to hold a track when occluded
echo    --night                  Force night mode
echo    --day                    Force day mode
echo    --save                   Save output to output_tracked.mp4
echo    --no-window              Run headless (no display window)
echo.
echo  Examples:
echo    .\run.bat track --video data\videos\Iron_Dome.mp4
echo    .\run.bat track --video data\videos\Iron_Dome.mp4 --night --weights models\missile.pt
echo    .\run.bat track --video data\videos\Iron_Dome.mp4 --conf 0.20
echo    .\run.bat track --cam 0 --night --save
echo.
echo  Training:
echo    .\run.bat train
echo.
echo  Data Management:
echo    .\run.bat download-data                 (download Roboflow dataset)
echo    .\run.bat track --download-data         (alternative download command)
echo.
echo  Live window controls:
echo    Q  Quit              P  Pause/Resume        N  Toggle Night/Day
echo    F  Cycle Filter      G  Toggle Auto-Horizon  W/S  Raise/Lower Horizon
echo    C  Screenshot
echo.
echo  Legend:
echo    YOLO = missile detected by shape model
echo    IR   = missile detected by IR exhaust / dim-dot tracking

REM Quick-launch (remove leading REM to activate):
REM NOTE: Do NOT use single quotes around video paths. Use format: .\run.bat track --video data\videos\video.mp4
REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\missile.pt
REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\yolo26n_custom.pt
REM .\run.bat track --video data\videos\NIGHT@.mp4
REM .\run.bat track --video data\videos\IRAN!1.mp4

:download_data
echo [ACTION] Downloading tactical missile dataset...
%PYTHON% scripts\download_data.py
goto :EOF