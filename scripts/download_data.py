from roboflow import Roboflow
import os

def download_dataset(api_key):
    # Initialize Roboflow
    rf = Roboflow(api_key=api_key)
    
    # Access the project
    # Project: final-missiles
    # Universe path: qedwdqw/final-missiles
    project = rf.workspace("qedwdqw").project("final-missiles")
    
    # Download the dataset in YOLOv8 format (compatible with YOLO26)
    # Note: Using version 1 by default; check Roboflow if another version is needed.
    dataset = project.version(2).download("yolov8")
    
    print(f"Dataset downloaded to: {dataset.location}")
    return dataset.location

if __name__ == "__main__":
    # You can set your API key here or as an environment variable
    # Get your key at https://app.roboflow.com/settings/api
    API_KEY = "i3LX0DPRWRT4TlBqgHB6"
    
    if API_KEY == "YOUR_ROBOFLOW_API_KEY_HERE":
        print("Please update the API_KEY in this script with your Roboflow API Key.")
    else:
        download_dataset(API_KEY)
