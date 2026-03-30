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
    echo [ENV] TIP: Run 'python -m venv .venv' and pip install -r requirements.txt
)

REM ===========================================================================
REM |                   IRON DOME TRACKER CONTROL PANEL                       |
REM ===========================================================================
REM | Adjust these values to tune the system without touching Python code.    |
REM | Any flag can also be overridden per-run on the command line.            |
REM ===========================================================================

REM --- Model ---
REM WEIGHTS: Path to the YOLO model weights file.
SET WEIGHTS=models\yolo26n_custom.pt
REM CONF: (0.10-0.60) YOLO detection confidence threshold. Lower = more detections.
SET CONF=0.27

REM --- Hardware Acceleration ---
REM DEVICE: 0 for primary GPU, cpu for CPU. Leave empty to auto-detect.
SET DEVICE=0

REM --- Night Flame / IR Detector ---
REM BRIGHT_THRESH: (100-220) Global pixel threshold for the bright-exhaust detection path.
REM   Lower = catches dimmer exhausts. Raise if city lights cause too many false positives.
SET BRIGHT_THRESH=120
REM MIN_FLAME: (2-20) Minimum blob area in pixels. 
REM   4 = Rejects 1x1 sub-pixel camera noise, ensuring target precision.
SET MIN_FLAME=4
REM MAX_FLAME: (10000-200000) Maximum blob area. Prevents large explosions being tracked.
SET MAX_FLAME=150000
REM EDGE_MARGIN: (0.02-0.10) Fraction of frame edge to ignore (removes TV logos/borders).
SET EDGE_MARGIN=0.06
REM MAX_ASPECT: (2.0-10.0) Rejects elongated blobs. Missiles are compact/roughly round.
SET MAX_ASPECT=5.0
REM GROUND_FRAC: (0.40-0.95) Initial horizon fraction. Auto mode tunes from this baseline.
SET GROUND_FRAC=0.70

REM --- IR Cluster Filter (city-light rejection) ---
REM CLUSTER_RADIUS: (20-120) Pixels. Blobs closer than this count as neighbors.
SET CLUSTER_RADIUS=60
REM CLUSTER_MAX: (2-10) Max neighbor count before a blob is rejected as a city-light cluster.
REM   5 = Allows for missile swarms or multi-stage interceptions before rejecting.
SET CLUSTER_MAX=10

REM --- Background Subtractor (MOG2) ---
REM MOG_HISTORY: (50-500) Frames used to model the static background.
REM   250 = Takes 10 seconds for a static object to fade. Prevents head-on missiles from vanishing.
SET MOG_HISTORY=150
REM MOG_VAR: (10-60) Variance threshold. Lower = flags more motion (catches slower missiles).
SET MOG_VAR=25

REM --- IR Detection Confidence ---
REM FLAME_MIN_CONF: (0.10-0.50) IR detection confidence gate.
REM   0.40 = Requires a rigid optical structure to lock on, maximizing accuracy.
SET FLAME_MIN_CONF=0.25

REM --- Static Light Filter ---
REM STATIC_GRID: (10-60) Grid cell size in pixels. 
REM   30 = Larger buckets so slow/hovering missiles don't trigger static rejection immediately.
SET STATIC_GRID=30
REM WORLD_THRESH: (3-20) Frames before a world-coord static light is suppressed.
REM   18 frames = Missiles can stall or fly head-on for ~0.7s before being assumed as city lights.
SET WORLD_THRESH=18
REM CAM_THRESH: (10-40) Frames before a screen-coord static light is suppressed (TV logos).
REM   25 frames = Takes ~1s for a dirty lens flare/TV logo to disappear.
SET CAM_THRESH=25
REM STATIC_DECAY: (5-30) Frames before a suppressed cell is forgotten and re-enabled.
SET STATIC_DECAY=15

REM --- Tracking Logic ---
REM TRAIL_LEN: (10-100) Frames of position history drawn as the exhaust trail.
SET TRAIL_LEN=30
REM TRACK_DIST: (40-200) Max pixels a missile can move between frames and still be tracked.
REM   190 = Allows tracking of extremely fast / close-range hypersonic missiles.
SET TRACK_DIST=190
REM TRACK_CONFIRM: (1-6) Frames required before a track box is shown on screen.
REM   3 = Stable lock-on (filters out random 1-2 frame camera flashes).
SET TRACK_CONFIRM=3
REM TRACK_MISSED: (5-40) Frames a track is held when the missile disappears.
REM   12 frames = Fast shedding of false-positive tracks, preventing ghost tails.
SET TRACK_MISSED=12
REM TRACK_COAST: (0-15) Frames to dead-reckon (coast) a missed IR track before hiding its box.
REM   6 = Box stays visible for 6 frames during brief MOG2 gaps, eliminating blinking.
SET TRACK_COAST=6

REM --- Multi-target IR Tracker Stability ---
REM VEL_GATE: (1.0-4.0) Speed multiplier for the Hungarian assignment search radius.
REM   1.5 = Track search area grows modestly with speed; lower = tighter ID locking.
SET VEL_GATE=1.5
REM DIR_PENALTY: (0.0-2.0) Penalty for direction-reversals in assignments.
REM   0.4 = Soft tie-breaker only; 0.0 = disable; higher = stricter direction lock.
SET DIR_PENALTY=0.4
REM VEL_ALPHA: (0.1-1.0) EMA weight for velocity update (new frame vs. smoothed history).
REM   0.5 = Balanced; lower = velocity adapts slowly; higher = reacts instantly to jitter.
SET VEL_ALPHA=0.5
REM COAST_DRIFT: (0.0-1.0) Fraction of velocity applied per coasting frame.
REM   0.3 = Box barely moves during coast; 0.0 = box stands still; 1.0 = full drift.
SET COAST_DRIFT=0.3
REM BOX_SMOOTH: (0.1-1.0) EMA alpha for the displayed bounding box position.
REM   0.4 = Smooth, stable box; lower = more lag; higher = jittery raw detection.
SET BOX_SMOOTH=0.4
REM TRAIL_JUMP: (1.0-5.0) Max allowed gap between trail points as multiple of TRACK_DIST.
REM   2.5 = Segments longer than 2.5x the track distance are skipped (no wire lines).
REM   Lower = stricter wipe; useful when sources are tightly packed.
SET TRAIL_JUMP=1.5

REM --- Explosion / Flash Immunity ---
REM FLASH_THRESH: (1.2-3.0) Brightness ratio that triggers explosion flash detection.
REM   1.6 = A frame 60% brighter than the rolling average is treated as a flash.
REM   Lower = more sensitive (catches small glints); Higher = only massive explosions.
SET FLASH_THRESH=1.6
REM FLASH_COOLDOWN: (10-90) Frames to suppress IR detection after the flash ends.
REM   30 = ~1 second cooldown at 30fps. Prevents ground lights being detected as
REM        missiles when the scene suddenly darkens after an explosion.
SET FLASH_COOLDOWN=30
REM HORIZON_RISE: (0.005-0.05) Max fraction the horizon can rise per frame (upward limit).
REM   0.015 = Line only shifts upward 1.5% per frame, preventing flash spike.
REM   Lower = more stable horizon; Higher = allows faster real horizon adjustment.
SET HORIZON_RISE=0.015

REM --- Below-Ground IR Detection ---
REM BELOW_GROUND_CONF: (0.50-1.00) Minimum IR confidence for detections BELOW the horizon.
REM   0.75 = Only very bright/large IR signatures pass through below the ground line.
REM   1.00 = Effectively disabled (no detections below ground).
REM   0.50 = More permissive; useful for low-flying or near-ground missile tracking.
SET BELOW_GROUND_CONF=0.27
REM YOLO_GROUND_CONF: (0.50-1.00) Minimum YOLO AI confidence for detections BELOW the horizon.
REM   0.70 = Only high-confidence missile shapes below the ground line are tracked.
REM   1.00 = Effectively disabled (YOLO never reports below ground).
REM   0.50 = More permissive; keeps low-confidence AI hits near the ground.
SET YOLO_GROUND_CONF=0.80

REM --- Auto Ground Exclusion ---
REM AUTO_ALPHA: (0.05-0.50) EMA speed. Lower = smoother/more stable horizon.
SET AUTO_ALPHA=0.10

REM --- Sensitivity & Display ---
REM NIGHT_SENS: (30-100) Mean frame brightness below which night mode activates.
SET NIGHT_SENS=60
REM DEF_FILTER: Default display filter. Options: thermal  |  nvg  |  original
SET DEF_FILTER=thermal
REM NIGHT_CONF_OFFSET: (0.00-0.25) YOLO confidence reduction in night mode.
SET NIGHT_CONF_OFFSET=0.10
REM CAM_MOTION: (0.01-0.15) Phase-correlation threshold for camera-shake compensation.
SET CAM_MOTION=0.03

REM ===========================================================================

echo ====================================================
echo   Iron Dome Missile Tracker v3
echo   Day : YOLO shape detection
echo   Night: YOLO + IR Flame / Dim-dot detection
echo   Python: %PYTHON%
echo ====================================================
echo.

if "%~1"=="track" goto :track
if "%~1"=="train" goto :train
goto :usage

:track
echo [ACTION] Starting Iron Dome Missile Tracker v3...
for /f "tokens=1,* delims= " %%a in ("%*") do set REMAINING=%%b
%PYTHON% src\missile_tracker.py ^
    --weights             %WEIGHTS% ^
    --conf                %CONF% ^
    --bright-thresh       %BRIGHT_THRESH% ^
    --min-flame-area      %MIN_FLAME% ^
    --max-flame-area      %MAX_FLAME% ^
    --edge-margin         %EDGE_MARGIN% ^
    --max-aspect-ratio    %MAX_ASPECT% ^
    --ground-fraction     %GROUND_FRAC% ^
    --cluster-radius      %CLUSTER_RADIUS% ^
    --cluster-max-size    %CLUSTER_MAX% ^
    --mog-history         %MOG_HISTORY% ^
    --mog-var-thresh      %MOG_VAR% ^
    --flame-min-conf      %FLAME_MIN_CONF% ^
    --static-grid         %STATIC_GRID% ^
    --static-world-thresh %WORLD_THRESH% ^
    --static-cam-thresh   %CAM_THRESH% ^
    --static-decay        %STATIC_DECAY% ^
    --trail-length        %TRAIL_LEN% ^
    --track-max-dist      %TRACK_DIST% ^
    --track-confirm       %TRACK_CONFIRM% ^
    --track-missed        %TRACK_MISSED% ^
    --track-coast         %TRACK_COAST% ^
    --track-vel-gate      %VEL_GATE% ^
    --track-dir-penalty   %DIR_PENALTY% ^
    --track-vel-alpha     %VEL_ALPHA% ^
    --track-coast-drift   %COAST_DRIFT% ^
    --track-box-smooth    %BOX_SMOOTH% ^
    --trail-jump-mult     %TRAIL_JUMP% ^
    --flash-thresh        %FLASH_THRESH% ^
    --flash-cooldown      %FLASH_COOLDOWN% ^
    --max-horizon-rise    %HORIZON_RISE% ^
    --auto-ground-alpha   %AUTO_ALPHA% ^
    --night-sensitivity   %NIGHT_SENS% ^
    --default-filter      %DEF_FILTER% ^
    --night-conf-offset   %NIGHT_CONF_OFFSET% ^
    --cam-motion-thresh   %CAM_MOTION% ^
    --below-ground-conf   %BELOW_GROUND_CONF% ^
    --yolo-below-ground-conf %YOLO_GROUND_CONF% ^
    --device              %DEVICE% ^
    %REMAINING%
goto :EOF

:train
echo [ACTION] Starting YOLO26 Training on Custom Dataset...
%PYTHON% scripts\train_yolo26.py
goto :EOF

:usage
echo.
echo  Usage:
echo    run.bat track --video data\videos\video.mp4          (auto day/night)
echo    run.bat track --video data\videos\video.mp4 --night  (force night mode)
echo    run.bat track --video data\videos\video.mp4 --day    (force day mode)
echo    run.bat track --video data\videos\video.mp4 --save   (save output_tracked.mp4)
echo    run.bat track --cam 0 --night                        (webcam, night mode)
echo.
echo  All default values are configured in the CONTROL PANEL at the top of this file.
echo  Any flag listed below overrides the control panel value for a single run.
echo.
echo  Key per-run override flags:
echo    --weights PATH           YOLO model weights  (default: models\yolo26n_custom.pt)
echo    --conf 0.25              YOLO confidence threshold
echo    --device 0               GPU device (0 for primary GPU, cpu for CPU)
echo    --bright-thresh 120      IR global brightness threshold
echo    --ground-fraction 0.70   Initial horizon fraction
echo    --auto-ground-alpha 0.25 Auto-horizon EMA speed
echo    --night-sensitivity 60   Brightness level for auto night/day switch
echo    --track-confirm 3        Frames before target lock is displayed
echo    --track-missed 12        Frames to hold a track when occluded
echo    --night                  Force night mode
echo    --day                    Force day mode
echo    --save                   Save output to output_tracked.mp4
echo    --no-window              Run headless (no display window)
echo.
echo  Examples:
echo    run.bat track --video data\videos\Iron_Dome.mp4
echo    run.bat track --video data\videos\Iron_Dome.mp4 --night --weights models\missile.pt
echo    run.bat track --video data\videos\Iron_Dome.mp4 --bright-thresh 120
echo    run.bat track --cam 0 --night --save
echo.
echo  Training:
echo    run.bat train
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
REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\missile.pt
REM .\run.bat track --video data\videos\Iron_Dome.mp4 --weights models\yolo26n_custom.pt
REM .\run.bat track --video data\videos\NIGHT@.mp4
REM .\run.bat track --video data\videos\IRAN!1.mp4