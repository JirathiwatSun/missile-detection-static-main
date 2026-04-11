import os
from ultralytics import YOLO
import torch

def train_model():
    # Check for GPU
    device = '0' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # Load the YOLO26 model
    # Options: yolo26n.pt, yolo26s.pt, yolo26m.pt, yolo26l.pt, yolo26x.pt
    model = YOLO('yolo26n.pt') 

    # Path to the dataset configuration file (created after download)
    dataset_path = os.path.join(os.getcwd(), 'datasets', 'FINAL-MISSILES-2', 'data.yaml')
    
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        print("Please run download_data.py first.")
        return

    # Train the model
    results = model.train(
        data=dataset_path,
        epochs=100,
        imgsz=640,
        batch=16,
        device=device,
        name='missile_yolo26_custom',
        exist_ok=False,
        # NMS-free training is a key feature of YOLO26
        # but is typically handled internally by the architecture
    )

    print("Training complete. Results saved in 'runs/detect/missile_yolo26_custom'")

if __name__ == "__main__":
    train_model()
