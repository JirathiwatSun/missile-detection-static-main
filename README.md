# 🚀 Iron Dome Missile Tracker v3 (Day/Night Edition)

Welcome to the **Iron Dome Missile Tracker v3**! This project is a professional-grade real-time tactical tracking system designed for high-speed projectile detection. It uses a **Dual-Engine** architecture combining the power of **YOLO26n** (Next-Gen AI) with a custom **NightFlame** computer vision engine.

---

## 🛠️ Quick Installation (First-Time Users)

If you have just downloaded the project from GitHub, follow these 3 simple steps to get started:

### 1. Automatic Environment Setup
Double-click the **`setup.bat`** file.
> [!IMPORTANT]
> This will automatically create your virtual environment (`.venv`) and install all necessary AI libraries (OpenCV, Torch, Ultralytics, etc.). You don't need to run any manual `pip` commands!

### 2. Download the Dataset (Optional)
If you want to train your own model or explore the 9,206-image dataset:
```powershell
.\run.bat track --download-data
```
*(Or simply run `python scripts\download_data.py` from your terminal)*

### 3. Run the Tracker
To see the system in action immediately using the included high-accuracy weights:
```powershell
.\run.bat track --video data\videos\Iron_Dome.mp4
```

---

## 🎯 How to Use the Tracker

The system is designed to handle both clear daylight and pitch-black night conditions automatically.

### Running with different Video Feeds:
*   **Auto Mode (Recommended):** Tracks using the best available data.
    ```bash
    .\run.bat track --video data\videos\Iron_Dome.mp4
    ```
*   **Tactical Night Mode:** Forces the high-sensitivity "NightFlame" engine.
    ```bash
    .\run.bat track --video data\videos\Iron_Dome.mp4 --night --bright-thresh 150
    ```
*   **Webcam Tracking:** Use your own camera as a radar sensor.
    ```bash
    .\run.bat track --cam 0
    ```

### 🎮 In-Window Controls
While the tracker is running, you can use these keys to interact with the system:
| Key | Label | Description |
| :--- | :--- | :--- |
| **Q** | **ABORT** | Safely shut down the tracking system. |
| **P** | **HALT** | Pause the video feed to analyze a specific frame. |
| **N** | **OPTICS** | Cycle through tactical states: **AUTO** -> **FORCE NIGHT** -> **FORCE DAY**. |
| **F** | **FILTER** | Cycle through **Thermal (FLIR)** and **NVG** visual filters. |
| **G** | **AUTO-G** | Toggle automatic horizon detection on/off. |
| **W** | **HORIZON ↑** | Raise the ground exclusion horizon line (ignore more city lights). |
| **S** | **HORIZON ↓** | Lower the ground exclusion horizon line. |
| **C** | **CAPTURE** | Capture a high-resolution screenshot with HUD telemetry. |

---

## 🧠 Training Your Own Model

If you want to customize the AI to detect specific types of projectiles, follows these steps:

1.  **Prepare your data:** Ensure you have run the download script mentioned in Step 2 of the Installation section.
2.  **Start Training:**
    ```bash
    .\run.bat train
    ```
3.  **Monitor Results:** The training logic will run for **100 epochs**. You can follow the progress in the newly created `runs/detect/missile_yolo26_custom/` folder.
4.  **Deploy:** Once finished, your best model will be saved as `best.pt`. You can move this to the `models/` folder to use it.

---

## 📁 Project Structure Explained

*   **`src/`**: The "Heart" of the system. Contains the main logic engine.
*   **`models/`**: Stores your trained AI "Brains" (`.pt` files).
*   **`data/videos/`**: Contains sample tactical footage for testing.
*   **`runs/`**: This folder appears after you train. It contains your AI's "Report Card" (accuracy graphs and stats).
*   **`docs/`**: Contains the **Presentation Report** for a deep dive into the OS optimization logic.

---

## 💡 Troubleshooting
> [!TIP]
> **Error: "failed to locate pyvenv.cfg":** Your virtual environment is corrupted. Simply delete the `.venv` folder and run `setup.bat` again.
>
> **Low FPS:** Ensure your laptop is plugged in. The YOLO engine performs best on a dedicated GPU (RTX 4060 or better).

---

## 🤝 Collaboration & Git Basics

If you are working on this project with a team, follow these simple commands to keep your code up to date and share your changes.

### 1. Get the Latest Code (Before you start)
Always run this to make sure you have the newest version from your friends:
```bash
git pull origin main
```

### 2. Save Your Changes (Local)
When you have finished making changes, "save" them to your local history:
```bash
# Stage all your changed files
git add .

# Create a save point with a message
git commit -m "Added new features or fixed bugs"
```

### 3. Share Your Work (To GitHub)
Send your saved changes so your friends can see them:
```bash
git push origin main
```

> [!TIP]
> **Not sure what changed?** Run `git status` anytime to see which files you have modified!

---

*This project is built for tactical research and educational purposes. Always ensure you are following local regulations regarding the use of such software.*

