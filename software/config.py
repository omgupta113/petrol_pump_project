import numpy as np

class Config:
    # Constants and configurations
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 300
    MIN_WINDOW_WIDTH = 1000
    MIN_WINDOW_HEIGHT = 800
    
    # YOLO configurations
    VEHICLE_MODEL = 'models/yolov8s.pt'
    HELMET_MODEL = 'models/best (2).pt'
    SMOKE_FIRE_MODEL = 'models/best (10).pt'
    YOLO_CONFIDENCE = 0.6
    YOLO_CLASSES = [2, 3, 5, 7]  # Vehicle classes
    
    # Tracker configurations
    TRACKER_MAX_AGE = 20
    TRACKER_MIN_HITS = 3
    TRACKER_IOU_THRESHOLD = 0.3
    BIKE_CLASS=3
    
    # Generate random colors for tracking visualization
    COLORS = [(int(r), int(g), int(b)) for r, g, b in np.random.randint(0, 255, size=(100, 3))]
    BIKE_CLASS_ID = 3  # YOLO class ID for motorcycles
    CLASS_NAMES = {
        2: "Car",
        3: "Motorcycle",
        5: "Bus",
        7: "Truck"
    }