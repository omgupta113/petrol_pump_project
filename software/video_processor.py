import cv2
import numpy as np
from ultralytics import YOLO
from sort import Sort
from config import Config
from datetime import datetime
import threading
import time
import os
import re
import logging
from api_client import post_vehicle_entry, update_vehicle_exit, VEHICLE_TYPE_MAPPING, get_vehicle_status, force_update_stale_vehicles
logger = logging.getLogger('video_processor')

class VideoProcessor:
    def __init__(self):
        # Load models
        self.vehicle_model = YOLO(Config.VEHICLE_MODEL).to('cuda:0')
        
        # Initialize SORT tracker
        self.tracker = Sort(
            max_age=Config.TRACKER_MAX_AGE,
            min_hits=Config.TRACKER_MIN_HITS,
            iou_threshold=Config.TRACKER_IOU_THRESHOLD
        )
        
        # Initialize tracked vehicles
        self.tracked_vehicles = {}
        
        # For video processing
        self.source_path = None
        self.is_rtsp = False
        self.roi_points = None
        self.is_processing = False
        self.processing_thread = None
        self.original_frame = None
        self.processed_frame = None
        self.current_progress = 0
        self.total_frames = 0
        self.detection_fps = 0
        self.frame_count = 0
        
        # Set a timer for periodic forced updates
        self.last_forced_update = time.time()
        self.force_update_interval = 120  # 2 minutes
        
        # Maintenance thread
        self.maintenance_running = False
        self.maintenance_thread = None

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

    def is_rtsp_url(self, url):
        """Check if the provided URL is a valid RTSP URL."""
        rtsp_pattern = re.compile(r'^rtsp://.*')
        return bool(rtsp_pattern.match(url))

    def validate_source(self, source_path):
        """Validate if the source is a valid file or RTSP stream."""
        if self.is_rtsp_url(source_path):
            # For RTSP, check if we can connect to it
            cap = cv2.VideoCapture(source_path)
            success = cap.isOpened()
            if success:
                # Retrieve a frame to confirm it's working
                ret, _ = cap.read()
                cap.release()
                return ret
            return False
        else:
            # For files, check if the file exists
            return os.path.exists(source_path) and os.access(source_path, os.R_OK)

    def start_processing(self, source_path, roi_points):
        """Start video processing in a separate thread with either file or RTSP stream."""
        print(f"Attempting to start processing with: {source_path}")
        
        # Determine if the source is an RTSP stream
        self.is_rtsp = self.is_rtsp_url(source_path)
        
        # Validate the source
        if not self.validate_source(source_path):
            error_type = "RTSP stream connection failed" if self.is_rtsp else "Video file not found"
            print(f"Error: {error_type} at {source_path}")
            return False
        
        # Get total frames for progress estimation (not applicable for RTSP streams)
        self.total_frames = 0
        if not self.is_rtsp:
            try:
                cap = cv2.VideoCapture(source_path)
                self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
            except Exception as e:
                print(f"Warning: Could not get frame count: {e}")
                self.total_frames = 1000  # Fallback to a default value
        
        self.source_path = source_path
        self.roi_points = roi_points
        self.is_processing = True
        self.frame_count = 0
        
        # Reset tracking data
        self.tracked_vehicles = {}
        self.current_progress = 0
        self.detection_fps = 0
        
        if self.processing_thread is None or not self.processing_thread.is_alive():
            self.processing_thread = threading.Thread(target=self._process_video)
            self.processing_thread.daemon = True
            self.processing_thread.start()
            
        # Start maintenance tasks
        self.start_maintenance_tasks()
        
        return True
    
    def stop_processing(self):
        """Stop video processing."""
        self.is_processing = False
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1.0)
        
        # Stop maintenance tasks
        self.stop_maintenance_tasks()

    def _process_video(self):
        """Process video directly with YOLO streaming."""
        try:
            print(f"Starting video processing with: {self.source_path}")
            frame_count = 0
            fps_start_time = time.time()
            fps_frame_count = 0
            
            # Track previously detected objects that were in ROI
            previous_in_roi_track_ids = set()
            current_in_roi_track_ids = set()
            
            # Use YOLO's streaming mode by directly passing the source path
            for result in self.vehicle_model.predict(
                    source=self.source_path,
                    conf=Config.YOLO_CONFIDENCE,
                    classes=Config.YOLO_CLASSES,
                    device='0',
                    stream=True):  # Enable streaming mode for real-time processing
                
                if not self.is_processing:
                    break
                
                # Get original frame and make a copy for visualization
                frame = result.orig_img
                processed_frame = frame.copy()
                
                # Extract detections from results
                detections = []
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    if self.point_in_polygon((center_x, center_y), self.roi_points):
                        detections.append([x1, y1, x2, y2])
                
                tracked_objects = []
                if len(detections) > 0:
                    detections = np.array(detections)
                    tracked_objects = self.tracker.update(detections)
                    
                    current_time = datetime.now().strftime("%H:%M:%S")
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    
                    # Reset current frame's ROI tracking
                    current_in_roi_track_ids = set()
                    
                    for track_idx, track in enumerate(tracked_objects):
                        x1, y1, x2, y2, track_id = track.astype(int)
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        color = Config.COLORS[int(track_id) % len(Config.COLORS)]
                        
                        # Determine vehicle type from detection class
                        cls_id = int(result.boxes[min(track_idx, len(result.boxes)-1)].cls.item()) if len(result.boxes) > 0 else 2  # Default to Car (2)
                        vehicle_type = VEHICLE_TYPE_MAPPING.get(cls_id, "Car")  # Default to Car if class not in mapping
                        
                        # Check if the vehicle is in the ROI
                        in_roi = self.point_in_polygon((center_x, center_y), self.roi_points)
                        
                        if in_roi:
                            current_in_roi_track_ids.add(track_id)
                        
                        if track_id not in self.tracked_vehicles:
                            # Vehicle is newly detected
                            self.tracked_vehicles[track_id] = {
                                "entry_time": None,
                                "exit_time": None,
                                "in_roi": False,
                                "date": current_date,
                                "server_vehicle_id": None,  # Store server-generated vehicle ID
                                "vehicle_type": vehicle_type,  # Store vehicle type
                                "post_attempted": False,
                                "post_completed": False,
                                "put_attempted": False,
                                "put_completed": False
                            }
                            logger.info(f"New vehicle detected: ID {track_id}, Type {vehicle_type}")
                        
                        if in_roi and not self.tracked_vehicles[track_id]["in_roi"]:
                            # Vehicle entered ROI
                            self.tracked_vehicles[track_id]["entry_time"] = current_time
                            self.tracked_vehicles[track_id]["in_roi"] = True
                            self.tracked_vehicles[track_id]["post_attempted"] = True
                            
                            # Log entry
                            logger.info(f"Vehicle entered ROI: ID {track_id}, Time {current_time}")
                            
                            # Send entry data to the server
                            response = post_vehicle_entry(
                                petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                                vehicle_id=str(track_id),
                                entering_time=current_time,
                                date=current_date,
                                vehicle_type=vehicle_type  # Pass vehicle type to the API
                            )
                            
                            # Check and store server response
                            if response and "VehicleID" in response:
                                server_id = response["VehicleID"]
                                self.tracked_vehicles[track_id]["server_vehicle_id"] = server_id
                                self.tracked_vehicles[track_id]["post_completed"] = True
                                logger.info(f"Server assigned ID {server_id} to vehicle {track_id}")
                                print(f"[ENTRY] Track ID {track_id} -> Server ID {server_id}")
                            else:
                                logger.warning(f"No server ID received for vehicle {track_id} entry")
                        
                        # Display additional info in bounding boxes
                        # Draw bounding box and labels
                        cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 3)
                        
                        # ID Text - Show both local and server ID if available
                        if self.tracked_vehicles[track_id].get("server_vehicle_id"):
                            server_id = self.tracked_vehicles[track_id]["server_vehicle_id"]
                            id_text = f"ID: {track_id} (Server: {server_id[-6:]})"
                        else:
                            id_text = f"ID: {track_id}"
                        
                        self.draw_label(processed_frame, id_text, (x1, y1 - 10), color)
                        
                        # Display status indicators
                        post_status = "✓" if self.tracked_vehicles[track_id].get("post_completed") else "○"
                        put_status = "✓" if self.tracked_vehicles[track_id].get("put_completed") else "○"
                        status_text = f"API: POST {post_status} PUT {put_status}"
                        self.draw_label(processed_frame, status_text, (x1, y1 - 45), color)
                        
                        # Display vehicle class if available
                        if Config.SHOW_CLASS_LABEL and cls_id in Config.CLASS_NAMES:
                            cls_text = f"Class: {Config.CLASS_NAMES[cls_id]}"
                            self.draw_label(processed_frame, cls_text, (x1, y1 - 80), color)
                
                # Detect vehicles that were in ROI but are no longer there
                exited_vehicles = previous_in_roi_track_ids - current_in_roi_track_ids
                for track_id in exited_vehicles:
                    if track_id in self.tracked_vehicles and self.tracked_vehicles[track_id]["in_roi"]:
                        # Vehicle exited ROI
                        current_time = datetime.now().strftime("%H:%M:%S")
                        entry_time = self.tracked_vehicles[track_id]["entry_time"]
                        exit_time = current_time
                        filling_time = self.calculate_filling_time(entry_time, exit_time)
                        
                        # Mark as attempting PUT
                        self.tracked_vehicles[track_id]["put_attempted"] = True
                        
                        # Log exit
                        logger.info(f"Vehicle exited ROI: ID {track_id}, Exit Time {exit_time}, Duration {filling_time}")
                        
                        # Check if we have a server-assigned ID
                        vehicle_id_for_update = self.tracked_vehicles[track_id].get("server_vehicle_id")
                        
                        # First check if POST was completed
                        if not self.tracked_vehicles[track_id].get("post_completed", False):
                            # POST not completed - check if we can get status from the tracker
                            status = get_vehicle_status(track_id=str(track_id))
                            if status and status.get("posted") and status.get("server_vehicle_id"):
                                # We have server ID from tracker
                                vehicle_id_for_update = status.get("server_vehicle_id")
                                self.tracked_vehicles[track_id]["server_vehicle_id"] = vehicle_id_for_update
                                self.tracked_vehicles[track_id]["post_completed"] = True
                                logger.info(f"Retrieved server ID {vehicle_id_for_update} from tracker for vehicle {track_id}")
                        
                        # Debug which ID we're using
                        if vehicle_id_for_update:
                            logger.info(f"Using server ID {vehicle_id_for_update} for exit update")
                            print(f"[EXIT] Using server ID {vehicle_id_for_update} for track ID {track_id}")
                        else:
                            logger.warning(f"No server ID available for vehicle {track_id}, using track ID")
                            print(f"[EXIT] Using fallback track ID {track_id} (no server ID)")
                            vehicle_id_for_update = str(track_id)
                        
                        # Update exit data on the server
                        update_result = update_vehicle_exit(
                            petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                            vehicle_id=vehicle_id_for_update,
                            exit_time=exit_time,
                            filling_time=filling_time,
                            entry_time=entry_time
                        )
                        
                        # Check update result
                        if update_result is True:
                            self.tracked_vehicles[track_id]["put_completed"] = True
                            logger.info(f"Successfully updated exit for vehicle {track_id}")
                        elif update_result is False:
                            logger.warning(f"Failed to update exit for vehicle {track_id}")
                        else:
                            logger.info(f"Exit update for vehicle {track_id} running in background")
                        
                        # Mark vehicle as exited
                        self.tracked_vehicles[track_id]["in_roi"] = False
                        self.tracked_vehicles[track_id]["exit_time"] = exit_time
                
                # Update for next frame
                previous_in_roi_track_ids = current_in_roi_track_ids.copy()
                
                # Draw ROI polygon
                if len(self.roi_points) > 2:
                    cv2.polylines(processed_frame, [self.roi_points.reshape((-1, 1, 2))], True, (0, 255, 0), 2)
                
                # Calculate and update FPS
                fps_frame_count += 1
                if time.time() - fps_start_time > 1.0:  # Update FPS every second
                    self.detection_fps = fps_frame_count / (time.time() - fps_start_time)
                    fps_start_time = time.time()
                    fps_frame_count = 0
                
                # Draw FPS on the processed frame
                if Config.SHOW_FPS:
                    fps_text = f"FPS: {self.detection_fps:.1f}"
                    cv2.putText(processed_frame, fps_text, (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                # Update shared data for Streamlit to access
                self.original_frame = frame.copy()
                self.processed_frame = processed_frame
                
                # Update progress (for video files)
                frame_count += 1
                self.frame_count = frame_count
                if self.total_frames > 0 and not self.is_rtsp:
                    self.current_progress = min(1.0, frame_count / self.total_frames)
                elif self.is_rtsp:
                    # For RTSP streams, we don't know the total frames, so we set progress to a cycling value
                    self.current_progress = (frame_count % 100) / 100
                
                # Check if it's time to force update stale vehicles
                current_time = time.time()
                if current_time - self.last_forced_update > self.force_update_interval:
                    try:
                        updated_count = force_update_stale_vehicles()
                        if updated_count > 0:
                            logger.info(f"Forced updates for {updated_count} stale vehicles")
                    except Exception as e:
                        logger.error(f"Error during forced updates: {str(e)}")
                    
                    self.last_forced_update = current_time
                
                # Small delay to reduce CPU usage
                time.sleep(0.001)
            
        except Exception as e:
            print(f"Error in video processing: {str(e)}")
        
        self.is_processing = False
        print("Video processing completed.")
    
    def get_current_frames(self):
        """Get the current original and processed frames."""
        return self.original_frame, self.processed_frame
    
    def get_progress(self):
        """Get the current processing progress."""
        return self.current_progress, self.total_frames, self.is_processing, self.detection_fps
        
    def calculate_filling_time(self, entry_time, exit_time):
        """Calculate the filling time in minutes."""
        fmt = "%H:%M:%S"
        start = datetime.strptime(entry_time, fmt)
        end = datetime.strptime(exit_time, fmt)
        delta = end - start
        return f"{delta.seconds} seconds"
    
    def check_long_staying_vehicles(self):
        """Check for vehicles that have been in the ROI for too long."""
        current_time = datetime.now()
        current_time_str = current_time.strftime("%H:%M:%S")
        
        for track_id, vehicle_data in list(self.tracked_vehicles.items()):
            try:
                if vehicle_data["in_roi"] and vehicle_data["entry_time"]:
                    # Calculate how long the vehicle has been in ROI
                    entry_time = datetime.strptime(vehicle_data["entry_time"], "%H:%M:%S")
                    entry_time = entry_time.replace(
                        year=current_time.year, 
                        month=current_time.month, 
                        day=current_time.day
                    )
                    
                    time_diff = (current_time - entry_time).total_seconds()
                    
                    # If vehicle has been in ROI for more than MAX_ROI_TIME (e.g., 2 minutes),
                    # assume it has exited but was not detected
                    if time_diff > Config.MAX_ROI_TIME:
                        logger.warning(f"Vehicle {track_id} has been in ROI for {time_diff:.1f} seconds. Forcing exit.")
                        
                        # Mark as exited and update server
                        self.tracked_vehicles[track_id]["in_roi"] = False
                        self.tracked_vehicles[track_id]["exit_time"] = current_time_str
                        self.tracked_vehicles[track_id]["put_attempted"] = True
                        
                        # Calculate filling time
                        filling_time = self.calculate_filling_time(vehicle_data["entry_time"], current_time_str)
                        
                        # Get server ID if available
                        vehicle_id_for_update = vehicle_data.get("server_vehicle_id", str(track_id))
                        
                        # Update exit data on the server
                        update_result = update_vehicle_exit(
                            petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                            vehicle_id=vehicle_id_for_update,
                            exit_time=current_time_str,
                            filling_time=filling_time,
                            entry_time=vehicle_data["entry_time"]
                        )
                        
                        if update_result is True:
                            self.tracked_vehicles[track_id]["put_completed"] = True
                            logger.info(f"Successfully forced exit update for vehicle {track_id}")
                        else:
                            logger.warning(f"Failed to force exit update for vehicle {track_id}")
            except Exception as e:
                logger.error(f"Error checking vehicle {track_id}: {e}")
                
    def cleanup_tracked_vehicles(self):
        """Remove old tracked vehicles that have already exited to save memory."""
        current_time = datetime.now()
        removed_count = 0
        
        for track_id, vehicle_data in list(self.tracked_vehicles.items()):
            try:
                # If vehicle has exited and PUT was completed
                if not vehicle_data["in_roi"] and vehicle_data["put_completed"]:
                    if vehicle_data["exit_time"]:
                        try:
                            # Calculate time since exit
                            exit_time = datetime.strptime(vehicle_data["exit_time"], "%H:%M:%S")
                            exit_time = exit_time.replace(
                                year=current_time.year, 
                                month=current_time.month, 
                                day=current_time.day
                            )
                            
                            # If more than 10 minutes since exit, remove from tracking
                            if (current_time - exit_time).total_seconds() > 600:
                                # Remove from tracked_vehicles
                                del self.tracked_vehicles[track_id]
                                removed_count += 1
                        except Exception as e:
                            logger.error(f"Error cleaning up vehicle {track_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing vehicle {track_id} for cleanup: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old vehicle tracking records")
            
    def start_maintenance_tasks(self):
        """Start background maintenance tasks."""
        if not hasattr(self, 'maintenance_thread'):
            self.maintenance_thread = None  # Ensure it exists
            
        if self.maintenance_thread is None or not self.maintenance_thread.is_alive():
            self.maintenance_running = True
            self.maintenance_thread = threading.Thread(target=self._run_maintenance_tasks, daemon=True)
            self.maintenance_thread.start()
            logger.info("Started maintenance tasks")
    
    def _run_maintenance_tasks(self):
        """Run periodic maintenance tasks."""
        while self.maintenance_running and self.is_processing:
            try:
                # Run maintenance tasks every 30 seconds
                time.sleep(30)
                
                # Check for long-staying vehicles
                self.check_long_staying_vehicles()
                
                # Clean up old tracked vehicles
                self.cleanup_tracked_vehicles()
                
            except Exception as e:
                logger.error(f"Error in maintenance tasks: {str(e)}")
    
    def stop_maintenance_tasks(self):
        """Stop the maintenance tasks."""
        self.maintenance_running = False
        if hasattr(self, 'maintenance_thread') and self.maintenance_thread.is_alive():
            self.maintenance_thread.join(timeout=1.0)
            
    def force_vehicle_exit(self, track_id):
        """Force a vehicle to be marked as exited (for admin/debug use)."""
        if isinstance(track_id, str):
            try:
                track_id = int(track_id)
            except ValueError:
                # It might be a server ID, try to find the track ID
                for t_id, vehicle_data in self.tracked_vehicles.items():
                    if vehicle_data.get("server_vehicle_id") == track_id:
                        track_id = t_id
                        break
                
                # If not found, return error
                if isinstance(track_id, str):
                    logger.warning(f"Vehicle with server ID {track_id} not found in tracked vehicles")
                    return False
                
        if track_id in self.tracked_vehicles:
            vehicle_data = self.tracked_vehicles[track_id]
            
            if vehicle_data["in_roi"]:
                current_time = datetime.now().strftime("%H:%M:%S")
                entry_time = vehicle_data["entry_time"]
                filling_time = self.calculate_filling_time(entry_time, current_time)
                
                # Mark as exited
                self.tracked_vehicles[track_id]["in_roi"] = False
                self.tracked_vehicles[track_id]["exit_time"] = current_time
                
                # Get server ID if available
                vehicle_id_for_update = vehicle_data.get("server_vehicle_id", str(track_id))
                
                # Update exit data on the server
                update_result = update_vehicle_exit(
                    petrol_pump_id="IOCL-1",  # Replace with actual petrol pump ID
                    vehicle_id=vehicle_id_for_update,
                    exit_time=current_time,
                    filling_time=filling_time,
                    entry_time=entry_time
                )
                
                if update_result is True:
                    self.tracked_vehicles[track_id]["put_completed"] = True
                    logger.info(f"Successfully forced exit for vehicle {track_id}")
                    return True
                else:
                    logger.warning(f"Failed to force exit for vehicle {track_id}")
                    return False
            else:
                logger.warning(f"Vehicle {track_id} is not in ROI")
                return False
        else:
            logger.warning(f"Vehicle {track_id} not found in tracked vehicles")
            return False
            
    def force_update_all_active_vehicles(self):
        """Force exit update for all active vehicles."""
        updated_count = 0
        
        # Get all vehicles that are still marked as in ROI
        active_vehicles = [track_id for track_id, data in self.tracked_vehicles.items() 
                          if data.get("in_roi", False)]
        
        logger.info(f"Attempting to force update {len(active_vehicles)} active vehicles")
        
        # Force exit for each active vehicle
        for track_id in active_vehicles:
            if self.force_vehicle_exit(track_id):
                updated_count += 1
        
        logger.info(f"Successfully updated {updated_count} out of {len(active_vehicles)} active vehicles")
        return updated_count