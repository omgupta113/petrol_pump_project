import numpy as np

class Config:
    # Constants and configurations
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 300
    MIN_WINDOW_WIDTH = 1000
    MIN_WINDOW_HEIGHT = 800
    
    # YOLO configurations
    VEHICLE_MODEL = 'models/yolov8m.pt'
    YOLO_CONFIDENCE = 0.6
    YOLO_CLASSES = [2, 3, 5, 7]  # Vehicle classes (car, motorcycle, bus, truck)
    
    # Tracker configurations
    TRACKER_MAX_AGE = 20
    TRACKER_MIN_HITS = 10
    TRACKER_IOU_THRESHOLD = 0.3
    BIKE_CLASS = 3
    
    # Stream processing configurations
    STREAM_BUFFER_SIZE = 30      # Maximum frames to buffer
    STREAM_QUEUE_TIMEOUT = 0.1   # Timeout for queue operations
    MAX_FPS = 30                 # Cap FPS to avoid excessive CPU usage
    
    # RTSP specific settings
    RTSP_RECONNECT_ATTEMPTS = 5  # Number of reconnection attempts for RTSP streams
    RTSP_RECONNECT_DELAY = 3     # Delay between reconnection attempts in seconds
    RTSP_CONNECTION_TIMEOUT = 10 # Timeout for RTSP connection in seconds
    RTSP_MAX_RETRIES = 3         # Maximum number of retries for RTSP read operations
    
    # Sample RTSP URL templates (for testing)
    RTSP_URL_SAMPLES = [
        "rtsp://username:password@ip_address:port/path",
        "rtsp://admin:admin@192.168.1.100:554/stream1",
        "rtsp://10.0.0.10:554/live/main"
    ]
    
    # Generate random colors for tracking visualization
    COLORS = [(int(r), int(g), int(b)) for r, g, b in np.random.randint(0, 255, size=(100, 3))]
    
    # Class names for display
    CLASS_NAMES = {
        2: "Car",
        3: "Motorcycle",
        5: "Bus",
        7: "Truck"
    }
    
    # Processing options
    SHOW_FPS = True           # Show FPS counter on processed frame
    SHOW_CLASS_LABEL = True   # Show vehicle class label
    SHOW_TRACK_ID = True      # Show tracking ID
    
    # Vehicle tracking configurations
    MAX_ROI_TIME = 120        # Maximum time (seconds) a vehicle should be in ROI before forced exit
    CLEANUP_INTERVAL = 600    # Time (seconds) after exit before removing vehicle from tracking
    
    # Error recovery
    MAX_RETRIES = 5           # Maximum number of retries for API operations
    RETRY_DELAY = 5           # Delay between retries in seconds