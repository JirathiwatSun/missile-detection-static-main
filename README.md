# Iron Dome Missile Tracker v3 (Day/Night Edition)

A professional-grade real-time missile detection and tracking system optimized for modern GPUs (RTX 4060+) using **YOLO26** (next-generation, NMS-free architecture).

## 🚀 Key Features
- **Day Mode**: Shape-based detection (missile silhouettes).
- **Night Mode**: Dual-engine detection (High-intensity flame/exhaust dots + Optical Flow).
- **YOLO26 Precision**: Trained on a custom dataset for high-accuracy tactical missile identification.
- **HUD Telemetry**: Real-time GPS, RNG (Range), ALT (Altitude), and SPD (Speed) estimation.

## 📁 Project Structure
- `src/`: Core tracking engine (`missile_tracker.py`).
- `scripts/`: Training and dataset utility scripts.
- `datasets/`: (Local only) Training data from Roboflow.
- `models/`: Weights files (`missile.pt`, `yolo26n.pt`).
- `data/`: Sample images and tactical footage.

## 🛠️ Setup Instructions
1. **Clone the repository**:
   ```bash
   git clone <your-repo-link>
   cd missile-detection-project
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Get the Dataset**:
   Update your Roboflow API key in `scripts/download_data.py` and run:
   ```bash
   python scripts/download_data.py
   ```

## 🎯 How to Use
Use the **`run.bat`** launcher for easy access:

### Track Video
```bash
.\run.bat track --video data\videos\Iron_Dome.mp4
```

### Force Night Mode
```bash
.\run.bat track --video data\videos\Iron_Dome.mp4 --night
```

### Train your own model
```bash
.\run.bat train
```

## 🎮 In-Window Controls
| Key | Action |
| --- | --- |
| **Q** | Quit Tracking |
| **P** | Pause / Resume |
| **N** | Toggle Night/Day Mode |
| **F** | Cycle Visual Filters (Thermal / NVG) |
| **S** | Capture Screenshot |

---
*Developed for tactical research and educational purposes.*
