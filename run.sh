#!/bin/bash

# ====================================================
#   Iron Dome Missile Tracker v3 - RUNNER (macOS/Linux)
# ====================================================

# ── Python resolver ────────────────────────────────────────────────────────
PYTHON="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "[ENV] Using virtual environment: .venv"
elif [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
    echo "[ENV] Using virtual environment: venv"
else
    echo "[ENV] No local virtual environment found. Using system 'python3'."
    echo "[ENV] TIP: Run './setup.sh' to create a virtual environment."
fi

# ── Load config.cfg ────────────────────────────────────────────────────────
CFG="config.cfg"
if [ ! -f "$CFG" ]; then
    echo "[ERROR] Configuration file not found: $CFG"
    echo "[ERROR] Please restore config.cfg from the repository."
    exit 1
fi

# Parse config.cfg and export variables
# This handles Windows line endings (\r) automatically by using tr
while IFS='=' read -r key value; do
    # Strip carriage returns and skip comments/empty lines
    key=$(echo "$key" | tr -d '\r' | xargs)
    value=$(echo "$value" | tr -d '\r')
    
    if [[ -n "$key" && ! "$key" =~ ^# ]]; then
        # Convert backslashes to forward slashes for path-like variables
        if [[ "$key" == "WEIGHTS" ]]; then
            value=$(echo "$value" | sed 's/\\/\//g')
        fi
        export "$key=$value"
    fi
done < "$CFG"

echo "[CFG] Loaded configuration from $CFG"

# ── Banner ─────────────────────────────────────────────────────────────────
echo "===================================================="
echo "  Iron Dome Missile Tracker v3"
echo "  Day : YOLO shape detection"
echo "  Night: YOLO + IR Flame / Dim-dot detection"
echo "  Config: $CFG"
echo "  Python: $PYTHON"
echo "===================================================="
echo

case "$1" in
    track)
        echo "[ACTION] Starting Iron Dome Missile Tracker v3..."
        
        # Check if --download-data is present in arguments
        for arg in "$@"; do
            if [ "$arg" == "--download-data" ]; then
                echo "[ACTION] Redirecting to data download..."
                $PYTHON scripts/download_data.py
                exit 0
            fi
        done

        shift # Remove 'track' from arguments
        
        # Strip leading/trailing quotes from arguments (support both quoted and unquoted paths)
        declare -a CLEAN_ARGS
        for arg in "$@"; do
            # Remove single and double quotes from beginning and end
            arg="${arg%\'}"  # Remove trailing single quote
            arg="${arg#\'}"  # Remove leading single quote
            arg="${arg%\"}"  # Remove trailing double quote
            arg="${arg#\"}"  # Remove leading double quote
            CLEAN_ARGS+=("$arg")
        done
        
        # Run python script with all configured flags
        $PYTHON src/missile_tracker.py \
            --weights             "$WEIGHTS" \
            --conf                "$CONF" \
            --bright-thresh       "$BRIGHT_THRESH" \
            --min-flame-area      "$MIN_FLAME" \
            --max-flame-area      "$MAX_FLAME" \
            --edge-margin         "$EDGE_MARGIN" \
            --max-aspect-ratio    "$MAX_ASPECT" \
            --ground-fraction     "$GROUND_FRAC" \
            --cluster-radius      "$CLUSTER_RADIUS" \
            --cluster-max-size    "$CLUSTER_MAX" \
            --mog-history         "$MOG_HISTORY" \
            --mog-var-thresh      "$MOG_VAR" \
            --flame-min-conf      "$FLAME_MIN_CONF" \
            --static-grid         "$STATIC_GRID" \
            --static-world-thresh "$WORLD_THRESH" \
            --static-cam-thresh   "$CAM_THRESH" \
            --static-decay        "$STATIC_DECAY" \
            --trail-length        "$TRAIL_LEN" \
            --track-max-dist      "$TRACK_DIST" \
            --track-confirm       "$TRACK_CONFIRM" \
            --track-missed        "$TRACK_MISSED" \
            --track-coast         "$TRACK_COAST" \
            --track-vel-gate      "$VEL_GATE" \
            --track-dir-penalty   "$DIR_PENALTY" \
            --track-vel-alpha     "$VEL_ALPHA" \
            --track-coast-drift   "$COAST_DRIFT" \
            --track-box-smooth    "$BOX_SMOOTH" \
            --trail-jump-mult     "$TRAIL_JUMP" \
            --flash-thresh        "$FLASH_THRESH" \
            --flash-cooldown      "$FLASH_COOLDOWN" \
            --max-horizon-rise    "$HORIZON_RISE" \
            --auto-ground-alpha   "$AUTO_ALPHA" \
            --night-sensitivity   "$NIGHT_SENS" \
            --default-filter      "$DEF_FILTER" \
            --night-conf-offset   "$NIGHT_CONF_OFFSET" \
            --cam-motion-thresh   "$CAM_MOTION" \
            --below-ground-conf   "$BELOW_GROUND_CONF" \
            --yolo-below-ground-conf "$YOLO_GROUND_CONF" \
            --device              "$DEVICE" \
            "${CLEAN_ARGS[@]}" # Forward remaining arguments (quotes stripped)
        ;;
    train)
        echo "[ACTION] Starting YOLO26 Training on Custom Dataset..."
        $PYTHON scripts/train_yolo26.py
        ;;
    download-data)
        echo "[ACTION] Downloading tactical missile dataset..."
        $PYTHON scripts/download_data.py
        ;;
    *)
        echo
        echo " Usage:"
        echo "   ./run.sh track --video data/videos/video.mp4          (auto day/night)"
        echo "   ./run.sh track --video data/videos/video.mp4 --night  (force night mode)"
        echo "   ./run.sh track --video data/videos/video.mp4 --day    (force day mode)"
        echo "   ./run.sh track --video data/videos/video.mp4 --save   (save output_tracked.mp4)"
        echo "   ./run.sh track --cam 0 --night                        (webcam, night mode)"
        echo
        echo " All default values are configured in: config.cfg"
        echo " Any flag listed below overrides config.cfg for a single run."
        echo
        echo " Key per-run override flags:"
        echo "   --weights PATH           YOLO model weights"
        echo "   --conf 0.27              YOLO confidence threshold"
        echo "   --device 0               GPU device (0 = primary GPU, cpu = CPU-only)"
        echo "   --bright-thresh 120      IR global brightness threshold"
        echo "   --ground-fraction 0.70   Initial horizon fraction"
        echo "   --auto-ground-alpha 0.10 Auto-horizon EMA speed"
        echo "   --night-sensitivity 60   Brightness level for auto night/day switch"
        echo "   --track-confirm 3        Frames before target lock is displayed"
        echo "   --track-missed 12        Frames to hold a track when occluded"
        echo "   --night                  Force night mode"
        echo "   --day                    Force day mode"
        echo "   --save                   Save output to output_tracked.mp4"
        echo "   --no-window              Run headless (no display window)"
        echo
        echo " Examples:"
        echo "   ./run.sh track --video data/videos/Iron_Dome.mp4"
        echo "   ./run.sh track --video data/videos/Iron_Dome.mp4 --night --weights models/missile.pt"
        echo "   ./run.sh track --video data/videos/Iron_Dome.mp4 --conf 0.20"
        echo "   ./run.sh track --cam 0 --night --save"
        echo
        echo " Training:"
        echo "   ./run.sh train"
        echo
        echo " Data Management:"
        echo "   ./run.sh download-data                 (download Roboflow dataset)"
        echo "   ./run.sh track --download-data         (alternative download command)"
        echo
        echo " Live window controls:"
        echo "   Q  Quit              P  Pause/Resume        N  Toggle Night/Day"
        echo "   F  Cycle Filter      G  Toggle Auto-Horizon  W/S  Raise/Lower Horizon"
        echo "   C  Screenshot"
        echo
        echo " Legend:"
        echo "   YOLO = missile detected by shape model"
        echo "   IR   = missile detected by IR exhaust / dim-dot tracking"
        ;;
esac

# Quick-launch (remove leading # to activate):
# ./run.sh track --video 'data/videos/Iron_Dome.mp4' --weights models/missile.pt
# ./run.sh track --video 'data/videos/Iron_Dome.mp4' --weights models/yolo26n_custom.pt
# ./run.sh track --video 'data/videos/NIGHT@.mp4'
# ./run.sh track --video 'data/videos/IRAN!1.mp4'
