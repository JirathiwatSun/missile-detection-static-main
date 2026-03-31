#!/bin/bash

# ====================================================
#   Iron Dome Missile Tracker v3 - AUTOMATIC SETUP (macOS/Linux)
# ====================================================

echo "===================================================="
echo "  Iron Dome Missile Tracker v3 - AUTOMATIC SETUP"
echo "===================================================="
echo

# 1. Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found! Please install Python from python.org or brew install python"
    exit 1
fi

# 2. Create Virtual Environment
echo "[1/2] Creating Virtual Environment (.venv)..."
if [ -d ".venv" ]; then
    echo "[INFO] .venv already exists. Skipping creation."
else
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment!"
        exit 1
    fi
fi

# 3. Install Requirements
echo "[2/2] Installing dependencies (this may take a few minutes)..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install requirements!"
    exit 1
fi

echo
echo "===================================================="
echo "  SETUP COMPLETE!"
echo "===================================================="
echo
echo "Your environment is ready. To track missiles, run:"
echo "  chmod +x run.sh"
echo "  ./run.sh track --video data/videos/Iron_Dome.mp4"
echo
echo "NOTE: If you need to download the training dataset later, run:"
echo "  ./run.sh train"
echo
