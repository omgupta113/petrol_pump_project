import aiohttp
import asyncio
import requests
import json
from datetime import datetime
import logging
import time
import concurrent.futures
import threading
from api_request_tracker import request_tracker

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('api_client')

# For mapping YOLO class IDs to vehicle types
VEHICLE_TYPE_MAPPING = {
    2: "Car",
    3: "Motorcycle",
    5: "Bus",
    7: "Truck"
}

# API endpoints
BASE_URL = "http://13.233.118.66:3000"
POST_VEHICLE_ENDPOINT = f"{BASE_URL}/PetrolPumps/details/"
UPDATE_VEHICLE_ENDPOINT = f"{BASE_URL}/PetrolPumps/details"
GET_VEHICLES_ENDPOINT = f"{BASE_URL}/PetrolPumps/details"

# Thread pool for async operations
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# In-memory queue for failed requests to retry later
failed_requests_queue = []
_is_retry_thread_running = False
_retry_thread = None
_lock = threading.Lock()

class RetryableRequest:
    def __init__(self, request_type, endpoint, payload, vehicle_id=None):
        self.request_type = request_type  # 'POST' or 'PUT'
        self.endpoint = endpoint
        self.payload = payload
        self.vehicle_id = vehicle_id
        self.retry_count = 0
        self.timestamp = time.time()
    
    def __str__(self):
        return f"{self.request_type} {self.endpoint} - Payload: {self.payload}"

def _start_retry_thread():
    """Start a background thread to retry failed requests."""
    global _is_retry_thread_running, _retry_thread
    
    with _lock:
        if not _is_retry_thread_running:
            _is_retry_thread_running = True
            _retry_thread = threading.Thread(target=_retry_failed_requests, daemon=True)
            _retry_thread.start()
            logger.info("Started retry thread for failed API requests")

def _retry_failed_requests():
    """Background thread function that periodically retries failed requests."""
    global _is_retry_thread_running, failed_requests_queue
    
    while _is_retry_thread_running:
        try:
            # Sleep to avoid CPU hogging
            time.sleep(5)
            
            with _lock:
                if not failed_requests_queue:
                    continue
                    
                current_time = time.time()
                requests_to_retry = []
                
                # Find requests that are due for retry (at least 5 seconds old)
                for request in failed_requests_queue:
                    if current_time - request.timestamp >= 5:
                        requests_to_retry.append(request)
                
                # Remove the requests we're about to retry from the queue
                if requests_to_retry:
                    failed_requests_queue = [r for r in failed_requests_queue if r not in requests_to_retry]
            
            # Process the retries outside the lock
            for request in requests_to_retry:
                try:
                    if request.request_type == 'POST':
                        response = requests.post(
                            request.endpoint,
                            json=request.payload,
                            timeout=10
                        )
                        if response.status_code == 201:
                            logger.info(f"Successfully retried POST request: {request.endpoint}")
                            # Update the tracker
                            track_id = request.payload.get('VehicleID', 'unknown')
                            petrol_pump_id = request.payload.get('petrolPumpID', 'unknown')
                            request_tracker.update_post_status(track_id, petrol_pump_id, response.json())
                        else:
                            # If still failing after 3 retries, log and drop
                            if request.retry_count >= 3:
                                logger.error(f"Failed to retry POST request after 3 attempts: {request.endpoint}")
                            else:
                                request.retry_count += 1
                                request.timestamp = time.time()
                                with _lock:
                                    failed_requests_queue.append(request)
                    
                    elif request.request_type == 'PUT':
                        put_endpoint = f"{request.endpoint}/{request.vehicle_id}"
                        response = requests.put(
                            put_endpoint,
                            json=request.payload,
                            timeout=10
                        )
                        if response.status_code == 200:
                            logger.info(f"Successfully retried PUT request: {put_endpoint}")
                            # Update the tracker
                            request_tracker.update_put_status(request.vehicle_id, 
                                                             request.endpoint.split('/')[-1], 
                                                             True)
                        else:
                            # If still failing after 3 retries, log and drop
                            if request.retry_count >= 3:
                                logger.error(f"Failed to retry PUT request after 3 attempts: {put_endpoint}")
                            else:
                                request.retry_count += 1
                                request.timestamp = time.time()
                                with _lock:
                                    failed_requests_queue.append(request)
                except Exception as e:
                    logger.error(f"Error during retry: {str(e)}")
                    if request.retry_count < 3:
                        request.retry_count += 1
                        request.timestamp = time.time()
                        with _lock:
                            failed_requests_queue.append(request)
                    
        except Exception as e:
            logger.error(f"Error in retry thread: {str(e)}")

def _queue_failed_request(request_type, endpoint, payload, vehicle_id=None):
    """Add a failed request to the retry queue."""
    global failed_requests_queue
    
    request = RetryableRequest(request_type, endpoint, payload, vehicle_id)
    
    with _lock:
        failed_requests_queue.append(request)
    
    # Ensure the retry thread is running
    _start_retry_thread()
    
    logger.info(f"Queued {request_type} request for retry: {endpoint}")

async def post_vehicle_entry_async(petrol_pump_id, vehicle_type="Car", vehicle_id=None, entering_time=None, date=None):
    """
    Asynchronously post a new vehicle entry to the backend.
    
    Args:
        petrol_pump_id (str): ID of the petrol pump
        vehicle_type (str): Type of vehicle (default: "Car")
        vehicle_id (str): Optional vehicle ID
        entering_time (str): Time of entry (format: "HH:MM:SS")
        date (str): Date of entry (format: "YYYY-MM-DD")
    
    Returns:
        dict: Response from the server or None if request failed
    """
    # Set default values if not provided
    if entering_time is None:
        entering_time = datetime.now().strftime("%H:%M:%S")
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    if vehicle_id is None:
        # Generate a temporary vehicle ID - will be overwritten by server
        time_component = datetime.now().strftime("%H%M%S-%Y%m%d")
        vehicle_id = f"{time_component}-{vehicle_type[:2].upper()}"
    
    # Prepare the payload according to the specified format
    payload = {
        "petrolPumpID": petrol_pump_id,
        "VehicleType": vehicle_type,
        "PetrolPumpNumber": "1",  # Fixed as per requirements
        "Helmet": True,           # Fixed as per requirements
        "EnteringTime": entering_time,
        "ExitTime": "",           # Empty at entry time
        "FillingTime": "",        # Empty at entry time
        "Date": date,
        "ServerUpdate": True,     # Fixed as per requirements
        "VehicleID": vehicle_id
    }
    
    # Register this POST request with the tracker
    # If already tracked, it will be ignored
    request_tracker.track_post_request(vehicle_id, petrol_pump_id, payload)
    
    # Log the request details
    logger.info(f"Posting vehicle entry - Pump ID: {petrol_pump_id}, Track ID: {vehicle_id}, Type: {vehicle_type}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(POST_VEHICLE_ENDPOINT, json=payload, timeout=10) as response:
                response_text = await response.text()
                
                try:
                    response_json = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    response_json = {}
                
                if response.status == 201:
                    # Update the request tracker with success
                    request_tracker.update_post_status(vehicle_id, petrol_pump_id, response_json)
                    
                    server_id = response_json.get('VehicleID', 'Unknown')
                    logger.info(f"Successfully posted vehicle entry. Server assigned ID: {server_id}")
                    logger.info(f"Local ID {vehicle_id} mapped to Server ID {server_id}")
                    
                    return response_json
                else:
                    logger.error(f"Failed to post vehicle entry. Status: {response.status}")
                    logger.error(f"Response: {response_text}")
                    
                    # Queue for retry
                    _queue_failed_request('POST', POST_VEHICLE_ENDPOINT, payload)
                    return None
    except Exception as e:
        logger.error(f"Exception during post_vehicle_entry_async: {str(e)}")
        
        # Queue for retry
        _queue_failed_request('POST', POST_VEHICLE_ENDPOINT, payload)
        return None

async def update_vehicle_exit_async(petrol_pump_id, vehicle_id, exit_time=None, filling_time=None, entry_time=None):
    """
    Asynchronously update a vehicle's exit information.
    
    Args:
        petrol_pump_id (str): ID of the petrol pump
        vehicle_id (str): The vehicle ID received from the server
        exit_time (str): Time of exit (format: "HH:MM:SS")
        filling_time (str): Duration of filling in the format "X seconds"
        entry_time (str): Original entry time (for calculating filling time if not provided)
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    if exit_time is None:
        exit_time = datetime.now().strftime("%H:%M:%S")
    
    # Calculate filling time if not provided
    if filling_time is None and entry_time is not None:
        try:
            entry_dt = datetime.strptime(entry_time, "%H:%M:%S")
            exit_dt = datetime.strptime(exit_time, "%H:%M:%S")
            delta = exit_dt - entry_dt
            filling_time = f"{delta.seconds} seconds"
        except Exception as e:
            logger.warning(f"Could not calculate filling time: {str(e)}")
            filling_time = "unknown"
    
    # Prepare payload for the PUT request
    payload = {
        "ExitTime": exit_time,
        "FillingTime": filling_time
    }
    
    # Wait for POST completion if necessary (with timeout)
    max_retries = 3
    retry_delay = 0.5  # seconds
    
    for retry in range(max_retries):
        # Check if POST has completed
        vehicle_status = request_tracker.get_vehicle_status(track_id=vehicle_id)
        if vehicle_status and vehicle_status.get("posted", False):
            break
            
        # If this is not the last retry, wait and try again
        if retry < max_retries - 1:
            logger.info(f"Waiting for POST to complete for vehicle {vehicle_id} (retry {retry+1}/{max_retries})")
            time.sleep(retry_delay)
    
    # Check with the tracker if we can proceed with PUT
    can_proceed, server_id = request_tracker.track_put_request(vehicle_id, petrol_pump_id, payload)
    
    if not can_proceed:
        # As a fallback, allow PUT even if POST hasn't completed yet
        logger.warning(f"POST not confirmed complete for vehicle {vehicle_id}, attempting PUT anyway")
        can_proceed, server_id = request_tracker.track_put_request(vehicle_id, petrol_pump_id, payload, allow_if_not_posted=True)
    
    # If we have a server ID, use it instead of the local ID
    if server_id:
        logger.info(f"Using server ID {server_id} instead of {vehicle_id} for exit update")
        vehicle_id = server_id
    
    # Log the update details
    logger.info(f"Updating vehicle exit - Pump ID: {petrol_pump_id}, Vehicle ID: {vehicle_id}")
    logger.info(f"Exit data: Time={exit_time}, Filling Time={filling_time}")
    
    # Construct the proper URL for the PUT request
    # Fix: Use proper URL format with path parameters
    update_url = f"{UPDATE_VEHICLE_ENDPOINT}/{petrol_pump_id}/vehicle/{vehicle_id}"
    logger.info(f"UPDATE URL: {update_url}")
    logger.info(f"PUT Payload: {payload}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(update_url, json=payload, timeout=10) as response:
                response_text = await response.text()
                logger.info(f"Server response status: {response.status}")
                logger.info(f"Server response: {response_text}")
                
                if response.status == 200:
                    logger.info(f"Successfully updated vehicle exit: {vehicle_id}")
                    
                    # Update the tracker with success
                    request_tracker.update_put_status(vehicle_id, petrol_pump_id, True)
                    
                    return True
                else:
                    logger.error(f"Failed to update vehicle exit. Status: {response.status}")
                    logger.error(f"Response: {response_text}")
                    logger.error(f"URL: {update_url}, Vehicle ID: {vehicle_id}")
                    
                    # Update the tracker with failure
                    request_tracker.update_put_status(vehicle_id, petrol_pump_id, False)
                    
                    # Queue for retry
                    _queue_failed_request('PUT', UPDATE_VEHICLE_ENDPOINT, payload, vehicle_id)
                    return False
    except Exception as e:
        logger.error(f"Exception during update_vehicle_exit_async: {str(e)}")
        logger.error(f"URL: {update_url}, Vehicle ID: {vehicle_id}")
        
        # Update the tracker with failure
        request_tracker.update_put_status(vehicle_id, petrol_pump_id, False)
        
        # Queue for retry
        _queue_failed_request('PUT', UPDATE_VEHICLE_ENDPOINT, payload, vehicle_id)
        return False

async def get_vehicle_details_async(petrol_pump_id, vehicle_id=None):
    """
    Asynchronously get vehicle details from the server.
    
    Args:
        petrol_pump_id (str): ID of the petrol pump
        vehicle_id (str, optional): If provided, get details for a specific vehicle
    
    Returns:
        list or dict: Vehicle details from the server or None if request failed
    """
    url = f"{GET_VEHICLES_ENDPOINT}/{petrol_pump_id}"
    if vehicle_id:
        url += f"/vehicle/{vehicle_id}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get vehicle details. Status: {response.status}, Response: {error_text}")
                    return None
    except Exception as e:
        logger.error(f"Exception during get_vehicle_details_async: {str(e)}")
        return None

# Synchronous wrappers for the async functions to maintain compatibility with the existing code

def post_vehicle_entry(petrol_pump_id, vehicle_id=None, entering_time=None, date=None, vehicle_type="Car"):
    """
    Synchronous wrapper for post_vehicle_entry_async.
    Submits the API request in a background thread.
    """
    loop = asyncio.new_event_loop()
    
    def _run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            post_vehicle_entry_async(petrol_pump_id, vehicle_type, vehicle_id, entering_time, date)
        )
    
    # Submit to thread pool
    future = executor.submit(_run_async)
    try:
        result = future.result(timeout=0.1)  # Small timeout to avoid blocking
        return result
    except concurrent.futures.TimeoutError:
        # The async operation is still running in the background
        logger.info(f"Vehicle entry submission for {vehicle_id} is running in background")
        return None

def update_vehicle_exit(petrol_pump_id, vehicle_id, exit_time=None, filling_time=None, entry_time=None):
    """
    Synchronous wrapper for update_vehicle_exit_async.
    Submits the API request in a background thread.
    """
    loop = asyncio.new_event_loop()
    
    def _run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            update_vehicle_exit_async(petrol_pump_id, vehicle_id, exit_time, filling_time, entry_time)
        )
    
    # Submit to thread pool
    future = executor.submit(_run_async)
    try:
        result = future.result(timeout=0.1)  # Small timeout to avoid blocking
        return result
    except concurrent.futures.TimeoutError:
        # The async operation is still running in the background
        logger.info(f"Vehicle exit update for {vehicle_id} is running in background")
        return None

def get_vehicle_details(petrol_pump_id, vehicle_id=None):
    """
    Synchronous wrapper for get_vehicle_details_async.
    """
    loop = asyncio.new_event_loop()
    
    def _run_async():
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            get_vehicle_details_async(petrol_pump_id, vehicle_id)
        )
    
    # For data retrieval, we actually wait for the result
    future = executor.submit(_run_async)
    try:
        # Get the API response
        api_data = future.result()
        
        # Early return if no data
        if not api_data:
            logger.warning(f"No data received from API for petrol_pump_id={petrol_pump_id}")
            return []
            
        # Ensure we're working with a list for consistency
        if isinstance(api_data, dict):
            api_data = [api_data]
        
        # Process the data to make it safe
        processed_data = []
        for item in api_data:
            try:
                # Create a processed item with default values for all required fields
                processed_item = {
                    'VehicleID': item.get('VehicleID', 'unknown'),
                    'EnteringTime': item.get('EnteringTime', ''),
                    'ExitTime': item.get('ExitTime', ''),
                    'FillingTime': item.get('FillingTime', ''),
                    'ServerConnected': "0",  # Default to not connected
                    'ServerUpdate': False,   # Default to not updated
                    'Date': item.get('Date', ''),
                    'VehicleType': item.get('VehicleType', 'Car')
                }
                
                # Try to determine if vehicle is active/connected
                if 'ServerConnected' in item:
                    processed_item['ServerConnected'] = item['ServerConnected']
                
                if 'ServerUpdate' in item:
                    processed_item['ServerUpdate'] = item['ServerUpdate']
                
                processed_data.append(processed_item)
            except Exception as e:
                logger.error(f"Error processing item from API: {e}")
                
        return processed_data
    except Exception as e:
        logger.error(f"Error in get_vehicle_details: {str(e)}")
        return []

# Functions to access the request tracker
def get_request_stats():
    """Get statistics about API requests."""
    return request_tracker.get_stats()

def get_request_debug_logs():
    """Get debug logs from the request tracker."""
    return request_tracker.get_debug_logs()

def get_vehicle_status(track_id=None, server_id=None):
    """Get status of a vehicle or all vehicles."""
    return request_tracker.get_vehicle_status(track_id, server_id)

def force_update_stale_vehicles(petrol_pump_id="IOCL-1", max_active_time=300):
    """
    Force update vehicles that have been active for too long.
    
    Args:
        petrol_pump_id (str): ID of the petrol pump
        max_active_time (int): Maximum time in seconds a vehicle should be active
    
    Returns:
        int: Number of vehicles updated
    """
    updated_count = 0
    current_time = datetime.now()
    
    # Get all vehicle statuses
    vehicles = request_tracker.get_vehicle_status()
    if not vehicles:
        logger.warning("No vehicles found in tracker")
        return 0
    
    for vehicle in vehicles:
        try:
            # Check if the vehicle is still marked as in ROI but has been there too long
            if vehicle.get("posted", False) and not vehicle.get("put_completed", False):
                track_id = vehicle.get("track_id")
                server_id = vehicle.get("server_vehicle_id")
                
                # Skip if no server ID (shouldn't happen if posted is True)
                if not server_id:
                    logger.warning(f"Vehicle {track_id} is posted but has no server ID")
                    continue
                
                # Check post timestamp
                post_timestamp = vehicle.get("post_timestamp")
                if not post_timestamp:
                    logger.warning(f"Vehicle {track_id} has no post timestamp")
                    continue
                
                try:
                    # Parse timestamp
                    timestamp_dt = datetime.strptime(post_timestamp, "%Y-%m-%d %H:%M:%S.%f")
                    time_diff = (current_time - timestamp_dt).total_seconds()
                    
                    # If vehicle has been active for too long, force an exit update
                    if time_diff > max_active_time:
                        logger.info(f"Forcing exit update for stale vehicle {track_id} (server ID: {server_id})")
                        
                        # Get current time for exit time
                        exit_time = current_time.strftime("%H:%M:%S")
                        
                        # Calculate filling time (use default if entry time not available)
                        filling_time = "300 seconds"  # Default
                        
                        # Create exit payload
                        payload = {
                            "ExitTime": exit_time,
                            "FillingTime": filling_time
                        }
                        
                        # Force PUT request
                        update_url = f"{UPDATE_VEHICLE_ENDPOINT}/{petrol_pump_id}/vehicle/{server_id}"
                        
                        # Use synchronous request for immediate feedback
                        try:
                            response = requests.put(update_url, json=payload, timeout=10)
                            
                            if response.status_code == 200:
                                logger.info(f"Successfully forced exit update for vehicle {track_id} (server ID: {server_id})")
                                request_tracker.update_put_status(server_id, petrol_pump_id, True)
                                updated_count += 1
                            else:
                                logger.error(f"Failed to update vehicle exit. Status: {response.status_code}")
                                logger.error(f"Response: {response.text}")
                        except Exception as e:
                            logger.error(f"Error sending forced PUT request: {str(e)}")
                        
                except ValueError:
                    logger.warning(f"Invalid timestamp format for vehicle {track_id}: {post_timestamp}")
                    continue
        except Exception as e:
            logger.error(f"Error processing vehicle for forced update: {str(e)}")
    
    return updated_count

def manual_batch_put_request(petrol_pump_id="IOCL-1", vehicle_ids=None):
    """
    Manually send PUT requests for a batch of vehicles.
    
    Args:
        petrol_pump_id (str): ID of the petrol pump
        vehicle_ids (list): List of vehicle IDs to update. If None, update all vehicles
                           with server IDs that haven't had a PUT completed
    
    Returns:
        dict: Results of the operation with success and failure counts
    """
    results = {
        "success": 0,
        "failure": 0,
        "errors": []
    }
    
    # Get current time for exit time
    current_time = datetime.now().strftime("%H:%M:%S")
    
    # If no vehicle IDs specified, get all vehicles with server IDs that need PUT
    if not vehicle_ids:
        all_vehicles = request_tracker.get_vehicle_status()
        vehicle_ids = []
        
        for vehicle in all_vehicles:
            if (vehicle.get("posted", False) and 
                vehicle.get("server_vehicle_id") and 
                not vehicle.get("put_completed", False)):
                vehicle_ids.append(vehicle.get("server_vehicle_id"))
    
    # Process each vehicle
    for vehicle_id in vehicle_ids:
        try:
            # Create a generic exit payload
            payload = {
                "ExitTime": current_time,
                "FillingTime": "5 seconds"  # Default filling time
            }
            
            # Create the URL
            update_url = f"{UPDATE_VEHICLE_ENDPOINT}/{petrol_pump_id}/vehicle/{vehicle_id}"
            
            # Send the PUT request
            response = requests.put(update_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Manual PUT success for vehicle {vehicle_id}")
                results["success"] += 1
            else:
                logger.error(f"Manual PUT failed for vehicle {vehicle_id}. Status: {response.status_code}")
                logger.error(f"Response: {response.text}")
                results["failure"] += 1
                results["errors"].append(f"Vehicle {vehicle_id}: Status {response.status_code}, Response: {response.text}")
        except Exception as e:
            logger.error(f"Error in manual PUT for vehicle {vehicle_id}: {str(e)}")
            results["failure"] += 1
            results["errors"].append(f"Vehicle {vehicle_id}: Exception: {str(e)}")
    
    return results