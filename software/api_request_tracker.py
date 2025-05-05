import logging
import threading
import time
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('api_request_tracker')

class VehicleRequestTracker:
    """
    Class to track and manage API requests for vehicles.
    Ensures POST requests are completed before allowing PUT requests.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._vehicles = {}  # Track request status for each vehicle
        self._server_id_map = {}  # Map from server ID to key in _vehicles
        self._retry_thread = None
        self._is_running = False
        self._debug_log = []
    
    def track_post_request(self, track_id, petrol_pump_id, payload, result=None):
        """
        Register a POST request for a new vehicle entry.
        
        Args:
            track_id: Local tracking ID
            petrol_pump_id: ID of the petrol pump
            payload: Request payload
            result: Response from server (if available)
        
        Returns:
            bool: True if registered, False if already exists
        """
        with self._lock:
            # Generate a unique key
            key = f"{petrol_pump_id}_{track_id}"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            
            # Check if already tracked
            if key in self._vehicles:
                if self._vehicles[key]["posted"]:
                    logger.warning(f"Duplicate POST attempt for vehicle {track_id}")
                    self._log_debug(f"DUPLICATE POST detected - Vehicle: {track_id}")
                    return False
            
            # Create or update tracking record
            server_id = None
            if result and "VehicleID" in result:
                server_id = result["VehicleID"]
                # Add to server ID map for quicker lookup
                self._server_id_map[server_id] = key
            
            vehicle_data = {
                "track_id": track_id,
                "petrol_pump_id": petrol_pump_id,
                "posted": result is not None,  # True if we have a response
                "post_payload": payload,
                "post_timestamp": timestamp,
                "server_vehicle_id": server_id,
                "put_attempted": False,
                "put_completed": False,
                "put_payload": None,
                "put_timestamp": None,
                "retry_count": 0,
                "last_retry": None
            }
            
            self._vehicles[key] = vehicle_data
            
            # Log the action
            action = "updated" if key in self._vehicles else "created"
            logger.info(f"POST request {action} for vehicle {track_id}")
            self._log_debug(f"POST request tracked - Vehicle: {track_id}, Server ID: {server_id}")
            
            # Start retry thread if not running
            self._ensure_retry_thread()
            
            return True
    
    def update_post_status(self, track_id, petrol_pump_id, result):
        """
        Update the status of a POST request with server response.
        
        Args:
            track_id: Local tracking ID
            petrol_pump_id: ID of the petrol pump
            result: Response from server
        
        Returns:
            bool: True if updated, False if not found
        """
        with self._lock:
            key = f"{petrol_pump_id}_{track_id}"
            if key not in self._vehicles:
                logger.warning(f"Cannot update POST status: Vehicle {track_id} not found")
                self._log_debug(f"UPDATE POST FAILED - Vehicle: {track_id} not found")
                return False
            
            # Update tracking data
            self._vehicles[key]["posted"] = True
            self._vehicles[key]["retry_count"] = 0
            
            # Extract server vehicle ID if present
            if result and "VehicleID" in result:
                server_id = result["VehicleID"]
                self._vehicles[key]["server_vehicle_id"] = server_id
                # Add to server ID map
                self._server_id_map[server_id] = key
                logger.info(f"Updated vehicle {track_id} with server ID {server_id}")
                self._log_debug(f"POST SUCCESS - Vehicle: {track_id}, Server ID: {server_id}")
            else:
                logger.warning(f"Server response for vehicle {track_id} missing VehicleID")
                self._log_debug(f"POST MISSING ID - Vehicle: {track_id}")
            
            return True
    
    def track_put_request(self, track_id, petrol_pump_id, payload, allow_if_not_posted=False):
        """
        Register a PUT request to update vehicle exit.
        Will only allow if a POST has been completed for this vehicle.
        """
        with self._lock:
            key = None
            server_id = None
            vehicle = None
            
            # First check if this is a server ID being passed
            if track_id and isinstance(track_id, str) and track_id.startswith("14") and "-" in track_id:  # Rough check for server ID format
                # This looks like a server ID
                logger.debug(f"Treating {track_id} as a server ID")
                
                # Try to find the vehicle using the server ID map
                if track_id in self._server_id_map:
                    key = self._server_id_map[track_id]
                    logger.debug(f"Found key {key} using server ID map for {track_id}")
                    vehicle = self._vehicles.get(key)
                    server_id = track_id
                else:
                    # If not in map, search all vehicles for this server ID
                    logger.debug(f"Server ID {track_id} not in map, searching all vehicles")
                    for vkey, vdata in self._vehicles.items():
                        if vdata.get("server_vehicle_id") == track_id:
                            key = vkey
                            vehicle = vdata
                            server_id = track_id
                            # Add to map for future use
                            self._server_id_map[track_id] = key
                            logger.debug(f"Found key {key} by searching for server ID {track_id}")
                            break
            
            # If not found as server ID, try regular lookup
            if vehicle is None:
                key = f"{petrol_pump_id}_{track_id}"
                vehicle = self._vehicles.get(key)
                if vehicle:
                    logger.debug(f"Found vehicle with key {key} (regular lookup)")
                    server_id = vehicle.get("server_vehicle_id")
            
            # If still not found, deny the PUT request
            if vehicle is None:
                if not allow_if_not_posted:
                    logger.warning(f"PUT request denied: Vehicle {track_id} not found (POST first)")
                    self._log_debug(f"PUT DENIED - Vehicle: {track_id} POST not found")
                    return False, None
                else:
                    # Create a new entry if allowed to bypass POST
                    logger.warning(f"Creating entry for PUT without POST: Vehicle {track_id}")
                    self._log_debug(f"PUT WITHOUT POST - Creating entry for vehicle: {track_id}")
                    key = f"{petrol_pump_id}_{track_id}"
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                    self._vehicles[key] = {
                        "track_id": track_id,
                        "petrol_pump_id": petrol_pump_id,
                        "posted": False,  # No POST has been completed
                        "post_payload": None,
                        "post_timestamp": None,
                        "server_vehicle_id": None,
                        "put_attempted": True,
                        "put_completed": False,
                        "put_payload": payload,
                        "put_timestamp": timestamp,
                        "retry_count": 0,
                        "last_retry": None
                    }
                    # No server ID available
                    return True, None
            
            # Check if POST has been completed
            if not vehicle["posted"] and not allow_if_not_posted:
                # Check how recently this vehicle was created
                if "post_timestamp" in vehicle:
                    try:
                        post_time = datetime.strptime(vehicle["post_timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                        current_time = datetime.now()
                        # If vehicle was created less than 2 seconds ago, allow PUT even if POST not completed
                        if (current_time - post_time).total_seconds() < 2.0:
                            logger.info(f"Allowing PUT for recent vehicle {track_id} despite POST not confirmed complete")
                            return True, server_id
                    except Exception as e:
                        logger.error(f"Error checking post timestamp: {e}")
                        
                logger.warning(f"PUT request denied: POST for vehicle {track_id} not completed")
                return False, None
            
            # Update tracking data
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            vehicle["put_attempted"] = True
            vehicle["put_payload"] = payload
            vehicle["put_timestamp"] = timestamp
            
            self._log_debug(f"PUT TRACKED - Vehicle: {track_id}, Server ID: {server_id}")
            logger.info(f"PUT request tracked for vehicle {track_id} with server ID {server_id}")
            
            # Start retry thread if not running
            self._ensure_retry_thread()
            
            # Return whether the operation can proceed and the server ID to use
            return True, server_id
    
    def update_put_status(self, track_id, petrol_pump_id, success):
        """
        Update the status of a PUT request.
        
        Args:
            track_id: Local tracking ID or server ID
            petrol_pump_id: ID of the petrol pump
            success: Whether the PUT was successful
            
        Returns:
            bool: True if updated, False if not found
        """
        with self._lock:
            key = None
            
            # First check if this is a server ID
            if isinstance(track_id, str) and track_id.startswith("14") and "-" in track_id:  # Rough check for server ID format
                if track_id in self._server_id_map:
                    key = self._server_id_map[track_id]
                else:
                    # Search all vehicles for this server ID
                    for vkey, vdata in self._vehicles.items():
                        if vdata.get("server_vehicle_id") == track_id:
                            key = vkey
                            # Add to map for future use
                            self._server_id_map[track_id] = key
                            break
            
            # If not found as server ID, try regular lookup
            if key is None:
                key = f"{petrol_pump_id}_{track_id}"
            
            if key not in self._vehicles:
                logger.warning(f"Cannot update PUT status: Vehicle {track_id} not found")
                self._log_debug(f"UPDATE PUT FAILED - Vehicle: {track_id} not found")
                return False
            
            # Update tracking data
            if success:
                self._vehicles[key]["put_completed"] = True
                self._vehicles[key]["retry_count"] = 0
                self._log_debug(f"PUT SUCCESS - Vehicle: {track_id}")
                logger.info(f"PUT request completed for vehicle {track_id}")
            else:
                self._vehicles[key]["retry_count"] += 1
                self._vehicles[key]["last_retry"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                self._log_debug(f"PUT FAILED - Vehicle: {track_id}, Retry count: {self._vehicles[key]['retry_count']}")
                logger.warning(f"PUT request failed for vehicle {track_id} (retry: {self._vehicles[key]['retry_count']})")
            
            return True
    
    def get_pending_requests(self):
        """
        Get all pending requests that need to be retried.
        
        Returns:
            list: List of pending requests
        """
        with self._lock:
            pending = []
            
            for key, vehicle in self._vehicles.items():
                # Check for pending POST requests
                if not vehicle["posted"] and vehicle["retry_count"] < 5:
                    pending.append({
                        "type": "POST",
                        "track_id": vehicle["track_id"],
                        "petrol_pump_id": vehicle["petrol_pump_id"],
                        "payload": vehicle["post_payload"],
                        "retry_count": vehicle["retry_count"]
                    })
                
                # Check for pending PUT requests
                if vehicle["posted"] and vehicle["put_attempted"] and not vehicle["put_completed"] and vehicle["retry_count"] < 5:
                    pending.append({
                        "type": "PUT",
                        "track_id": vehicle["track_id"],
                        "petrol_pump_id": vehicle["petrol_pump_id"],
                        "payload": vehicle["put_payload"],
                        "server_id": vehicle["server_vehicle_id"],
                        "retry_count": vehicle["retry_count"]
                    })
            
            return pending
    
    def _ensure_retry_thread(self):
        """Ensure the retry thread is running."""
        if not self._is_running or (self._retry_thread and not self._retry_thread.is_alive()):
            self._is_running = True
            self._retry_thread = threading.Thread(target=self._retry_pending_requests, daemon=True)
            self._retry_thread.start()
            logger.info("Started request retry thread")
    
    def _retry_pending_requests(self):
        """Background thread to retry pending requests."""
        logger.info("Retry thread started")
        while self._is_running:
            try:
                # Sleep to avoid CPU hogging
                time.sleep(5)
                
                # This method just signals that retries are needed
                # Actual retry logic should be implemented by the caller
                pending = self.get_pending_requests()
                
                if pending:
                    logger.info(f"Retry thread found {len(pending)} pending requests")
                    self._log_debug(f"RETRY THREAD - Found {len(pending)} pending requests")
                    # Signal that retries are needed through an event or callback
                    # Actual retry logic is in the API client
            except Exception as e:
                logger.error(f"Error in retry thread: {str(e)}")
            
        logger.info("Retry thread stopped")
    
    def stop(self):
        """Stop the retry thread."""
        self._is_running = False
        if self._retry_thread and self._retry_thread.is_alive():
            self._retry_thread.join(timeout=1.0)
    
    def _log_debug(self, message):
        """Add a debug log entry with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        self._debug_log.append(f"[{timestamp}] {message}")
        
        # Keep log at reasonable size
        if len(self._debug_log) > 1000:
            self._debug_log = self._debug_log[-1000:]
    
    def get_debug_logs(self):
        """Get the debug logs."""
        with self._lock:
            return self._debug_log.copy()
    
    def get_vehicle_status(self, track_id=None, server_id=None):
        """
        Get the status of a specific vehicle or all vehicles.
        
        Args:
            track_id: Local tracking ID (optional)
            server_id: Server-assigned ID (optional)
            
        Returns:
            dict or list: Vehicle status data
        """
        with self._lock:
            if track_id:
                # Search by track ID
                for key, vehicle in self._vehicles.items():
                    if str(vehicle["track_id"]) == str(track_id):
                        return vehicle
                return None
            
            elif server_id:
                # Search by server ID
                for key, vehicle in self._vehicles.items():
                    if vehicle["server_vehicle_id"] == server_id:
                        return vehicle
                return None
            
            else:
                # Return all vehicles
                return list(self._vehicles.values())
    
    def get_stats(self):
        """
        Get statistics about the tracked requests.
        
        Returns:
            dict: Statistics
        """
        with self._lock:
            total = len(self._vehicles)
            posted = sum(1 for v in self._vehicles.values() if v["posted"])
            put_attempted = sum(1 for v in self._vehicles.values() if v["put_attempted"])
            put_completed = sum(1 for v in self._vehicles.values() if v["put_completed"])
            pending_posts = sum(1 for v in self._vehicles.values() if not v["posted"])
            pending_puts = sum(1 for v in self._vehicles.values() if v["put_attempted"] and not v["put_completed"])
            
            return {
                "total_vehicles": total,
                "posts_completed": posted,
                "posts_pending": pending_posts,
                "puts_attempted": put_attempted,
                "puts_completed": put_completed,
                "puts_pending": pending_puts,
                "success_rate": (put_completed / put_attempted) * 100 if put_attempted > 0 else 0
            }
    
    def refresh_server_id_map(self):
        """Rebuild the server ID map to ensure it's up-to-date."""
        with self._lock:
            # Clear the existing map
            self._server_id_map.clear()
            
            # Rebuild it from all tracked vehicles
            for key, vehicle in self._vehicles.items():
                server_id = vehicle.get("server_vehicle_id")
                if server_id:
                    self._server_id_map[server_id] = key
            
            logger.info(f"Refreshed server ID map with {len(self._server_id_map)} entries")

# Create a global instance
request_tracker = VehicleRequestTracker()