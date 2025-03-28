import requests
from datetime import datetime

BASE_URL = "http://13.233.118.66:3000/PetrolPumps/"

def post_vehicle_entry(petrol_pump_id, vehicle_id, entering_time, date):
    """
    Send vehicle entry data to the server.
    """
    vehicle_id=vehicle_id+entering_time
    url = f"{BASE_URL}detail/"
    data = {
        "petrolPumpID": petrol_pump_id,
        "VehicleID": vehicle_id,
        "EnteringTime": entering_time,
        "ExitTime": "",  # Exit time will be updated later
        "FillingTime": "0 mins",  # Placeholder, can be updated later
        "Date": date,
        "ServerConnected": "1"
    }
    response = requests.post(url, json=data)
    if response.status_code == 201:
        print(f"Vehicle {vehicle_id} entry recorded successfully.")
    else:
        print(f"Failed to record vehicle {vehicle_id} entry. Error: {response.text}")

def update_vehicle_exit(petrol_pump_id, vehicle_id, exit_time, filling_time,entry_time):
    """
    Update vehicle exit data on the server.

    """
    vehicle_id=vehicle_id+entry_time
    url = f"{BASE_URL}detail/{petrol_pump_id}/{vehicle_id}"
    data = {
        "exitTime": exit_time,
        "fillingTime": filling_time,
        "serverConnected": "0"
    }
    response = requests.put(url, json=data)
    if response.status_code == 200:
        print(f"Vehicle {vehicle_id} exit updated successfully.")
    else:
        print(f"Failed to update vehicle {vehicle_id} exit. Error: {response.text}")

def get_vehicle_details(petrol_pump_id, vehicle_id=None):
    """
    Get vehicle details for a specific petrol pump (and optionally a specific vehicle).
    """
    if vehicle_id and petrol_pump_id:
        url = f"{BASE_URL}detail/{petrol_pump_id}/{vehicle_id}"
    elif petrol_pump_id :
        url = f"{BASE_URL}detail/{petrol_pump_id}"
    else:
        url = f"{BASE_URL}detail/"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print("Vehicle details retrieved successfully:")
        print(data)
        return data
    else:
        error_msg = response.text
        print(f"Failed to retrieve vehicle details. Error: {error_msg}")
        return None