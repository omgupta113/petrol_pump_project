import cv2
import numpy as np
from ultralytics import YOLO
from sort import Sort
from config import Config
from datetime import datetime
from api_client import post_vehicle_entry, update_vehicle_exit

class VideoProcessor:
    def __init__(self):
        # Load models
        self.vehicle_model = YOLO(Config.VEHICLE_MODEL).to('cuda:0')
        self.helmet_model = YOLO(Config.HELMET_MODEL).to('cuda:0')
        self.smoke_fire_model = YOLO(Config.SMOKE_FIRE_MODEL).to('cuda:0')
        
        # Initialize SORT tracker
        self.tracker = Sort(
            max_age=Config.TRACKER_MAX_AGE,
            min_hits=Config.TRACKER_MIN_HITS,
            iou_threshold=Config.TRACKER_IOU_THRESHOLD
        )
        
        # Define status colors
        self.HELMET_COLOR = (0, 255, 0)      # Green for helmet
        self.NO_HELMET_COLOR = (0, 0, 255)   # Red for no helmet
        self.ID_COLOR = (255, 255, 255)      # White for ID text
        self.SMOKE_COLOR = (128, 128, 128)   # Gray for smoke
        self.FIRE_COLOR = (0, 0, 255)        # Red for fire
        
        # Initialize smoke detection history
        self.smoke_history = []
        self.history_length = 5
        self.tracked_vehicles = {}

    def enhance_frame_for_smoke_detection(self, frame):
        """Enhance frame for better smoke detection."""
        # Convert to HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Enhance contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        hsv[:,:,2] = clahe.apply(hsv[:,:,2])
        
        # Convert back to BGR
        enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        
        return enhanced

    def detect_smoke_fire(self, frame):
        """Dedicated smoke and fire detection with preprocessing."""
        # Enhance frame
        enhanced_frame = self.enhance_frame_for_smoke_detection(frame)
        
        # Run detection with lower confidence for smoke
        results = self.smoke_fire_model.predict(
            source=enhanced_frame,
            conf=0.3,  # Lower confidence threshold
            iou=0.4,
            device='0'
        )
        
        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf)
                cls = int(box.cls)
                
                # Determine if it's smoke or fire based on class
                is_fire = cls == 0  # Assuming class 0 is fire
                
                # Calculate detection area
                area = (x2 - x1) * (y2 - y1)
                
                detections.append({
                    'box': (x1, y1, x2, y2),
                    'conf': conf,
                    'is_fire': is_fire,
                    'area': area
                })
        
        # Update history
        self.smoke_history.append(detections)
        if len(self.smoke_history) > self.history_length:
            self.smoke_history.pop(0)
        
        return self.filter_smoke_fire_detections(detections)

    def filter_smoke_fire_detections(self, current_detections):
        """Filter smoke/fire detections using temporal information."""
        if len(self.smoke_history) < 2:
            return current_detections
        
        filtered = []
        for detection in current_detections:
            current_box = detection['box']
            appearances = 1
            
            # Check previous frames
            for past_frame in self.smoke_history[:-1]:
                for past_detection in past_frame:
                    if self.boxes_overlap(current_box, past_detection['box']):
                        appearances += 1
                        break
            
            # Keep detection if it appears in multiple frames
            if appearances >= 2 or (detection['is_fire'] and detection['conf'] > 0.4):
                filtered.append(detection)
        
        return filtered

    def boxes_overlap(self, box1, box2, threshold=0.3):
        """Check if two boxes overlap significantly."""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right < x_left or y_bottom < y_top:
            return False
        
        intersection = (x_right - x_left) * (y_bottom - y_top)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        iou = intersection / float(area1 + area2 - intersection)
        return iou > threshold

    def point_in_polygon(self, point, polygon):
        """Check if a point is inside a polygon using the ray-casting algorithm."""
        x, y = point
        polygon = polygon.reshape(-1, 2)
        n = len(polygon)
        inside = False
        
        j = n - 1
        for i in range(n):
            if ((polygon[i][1] > y) != (polygon[j][1] > y)) and \
               (x < (polygon[j][0] - polygon[i][0]) * (y - polygon[i][1]) / (polygon[j][1] - polygon[i][1]) + polygon[i][0]):
                inside = not inside
            j = i
            
        return inside

    def draw_label(self, frame, text, position, background_color):
        """Draw text with enhanced visibility."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness = 2
        padding = 5

        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        x, y = position
        
        cv2.rectangle(
            frame,
            (x - padding, y - text_height - padding - baseline),
            (x + text_width + padding, y + padding),
            background_color,
            -1
        )
        
        cv2.rectangle(
            frame,
            (x - padding, y - text_height - padding - baseline),
            (x + text_width + padding, y + padding),
            (255, 255, 255),
            1
        )
        
        cv2.putText(
            frame,
            text,
            (x, y),
            font,
            font_scale,
            (255, 255, 255),
            thickness
        )


    def process_frame(self, frame, roi_points):
        """Process a single frame for vehicle detection, helmet detection, and smoke/fire detection."""
        processed_frame = frame.copy()

        # Enhanced smoke and fire detection
        smoke_fire_detections = self.detect_smoke_fire(frame)
        
        # Draw smoke/fire detections
        for detection in smoke_fire_detections:
            x1, y1, x2, y2 = detection['box']
            conf = detection['conf']
            is_fire = detection['is_fire']
            
            color = self.FIRE_COLOR if is_fire else self.SMOKE_COLOR
            label = f"{'FIRE' if is_fire else 'SMOKE'} {conf:.2f}"
            
            cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 3)
            self.draw_label(processed_frame, label, (x1, y1 - 10), color)

        # Vehicle detection
        vehicle_results = self.vehicle_model.predict(
            source=frame,
            conf=Config.YOLO_CONFIDENCE,
            classes=Config.YOLO_CLASSES,
            device='0'
        )

        # Helmet detection
        helmet_results = self.helmet_model.predict(
            source=frame,
            conf=Config.YOLO_CONFIDENCE,
            device='0'
        )

        detections = []
        for result in vehicle_results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                
                if self.point_in_polygon((center_x, center_y), roi_points):
                    detections.append([x1, y1, x2, y2])

        # Track detected vehicles
        tracked_objects = []
        if len(detections) > 0:
            detections = np.array(detections)
            tracked_objects = self.tracker.update(detections)

            current_time = datetime.now().strftime("%H:%M:%S")
            current_date = datetime.now().strftime("%Y-%m-%d")

            for track in tracked_objects:
                x1, y1, x2, y2, track_id = track.astype(int)
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                color = Config.COLORS[int(track_id) % len(Config.COLORS)]

                # Check if the vehicle is in the ROI
                in_roi = self.point_in_polygon((center_x, center_y), roi_points)

                # Track vehicle entry and exit
                if track_id not in self.tracked_vehicles:
                    # Vehicle is newly detected
                    self.tracked_vehicles[track_id] = {
                        "entry_time": None,
                        "exit_time": None,
                        "in_roi": False,
                        "date": current_date
                    }

                if in_roi and not self.tracked_vehicles[track_id]["in_roi"]:
                    # Vehicle entered ROI
                    self.tracked_vehicles[track_id]["entry_time"] = current_time
                    self.tracked_vehicles[track_id]["in_roi"] = True

                    # Send entry data to the server
                    post_vehicle_entry(
                        petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                        vehicle_id=str(track_id),
                        entering_time=current_time,
                        date=current_date
                    )

                elif not in_roi and self.tracked_vehicles[track_id]["in_roi"]:
                    # Vehicle exited ROI
                    current_time = datetime.now().strftime("%H:%M:%S")
                    entry_time = self.tracked_vehicles[track_id]["entry_time"]
                    exit_time = current_time
                    filling_time = self.calculate_filling_time(entry_time, exit_time)

                    # Update exit data on the server
                    update_vehicle_exit(
                        petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                        vehicle_id=str(track_id),
                        exit_time=exit_time,
                        filling_time=filling_time,
                        entry_time=self.tracked_vehicles[track_id]["entry_time"]
                    )
                    print(filling_time,exit_time)
                    print("vgfcv hjv hghjhfgvyughfvb yhgv biyuvutrc7tdcvutfvivuyfcugfcviyhvighvugfgxuggfcivyhviytfvytgbi7uvyutfrtctcvtyvyuhvgfhvhjhjujvjbhv")

                    # Mark vehicle as exited
                    self.tracked_vehicles[track_id]["in_roi"] = False
                    self.tracked_vehicles[track_id]["exit_time"] = exit_time

                # Check for helmet
                helmet_detected = False
                for helmet_result in helmet_results:
                    for h_box in helmet_result.boxes:
                        hx1, hy1, hx2, hy2 = map(int, h_box.xyxy[0].tolist())
                        if hx1 >= x1 and hy1 >= y1 and hx2 <= x2 and hy2 <= y2:
                            helmet_detected = True
                            break

                # Draw bounding box and labels
                cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 3)
                id_text = f"ID: {track_id}"
                self.draw_label(processed_frame, id_text, (x1, y1 - 45), color)
                
                status_color = self.HELMET_COLOR if helmet_detected else self.NO_HELMET_COLOR
                status_text = "HELMET" if helmet_detected else "NO HELMET"
                self.draw_label(processed_frame, status_text, (x1, y1 - 10), status_color)

        # Draw ROI polygon
        if len(roi_points) > 2:
            cv2.polylines(processed_frame, [roi_points.reshape((-1, 1, 2))], True, (0, 255, 0), 2)

        return processed_frame, tracked_objects

    def calculate_filling_time(self, entry_time, exit_time):
        """
        Calculate the filling time in minutes.
        """
        fmt = "%H:%M:%S"
        start = datetime.strptime(entry_time, fmt)
        end = datetime.strptime(exit_time, fmt)
        delta = end - start
        return f"{delta.seconds} seconds"


