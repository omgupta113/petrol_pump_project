import streamlit as st
import pandas as pd
import cv2
import numpy as np
from datetime import datetime
from video_processor import VideoProcessor  # Import the optimized video processor
from streamlit_extras.image_selector import image_selector, show_selection
from api_client import get_vehicle_details
import tempfile

st.set_page_config(
    page_title="Vehicle Tracking Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS for styling
st.markdown("""
<style>
    .header-style {
        font-size: 25px;
        font-weight: bold;
        color: #2E86C1;
        padding: 10px;
        border-bottom: 2px solid #2E86C1;
    }
    .metric-card {
        padding: 15px;
        border-radius: 10px;
        background-color: #F8F9F9;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .dataframe th {
        background-color: #2E86C1 !important;
        color: white !important;
    }
    .stButton button {
        background-color: #2E86C1 !important;
        color: white !important;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # Initialize session state
    session_defaults = {
        'roi_points': [],
        'processing': False,
        'tracked_vehicles': {},
        'frame': None,
        'video_path': None
    }
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Initialize video processor
    processor = VideoProcessor()

    # Sidebar controls
    with st.sidebar:
        st.markdown('<p class="header-style">Control Panel</p>', unsafe_allow_html=True)
        
        # File uploader
        uploaded_file = st.file_uploader("📤 Upload Surveillance Video", type=["mp4", "avi", "mov"])
        if uploaded_file is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False) 
            tfile.write(uploaded_file.read())
            st.session_state.video_path = tfile.name
        
        # ROI Section
        st.markdown("---")
        st.subheader("ROI Configuration")
        if st.button("🔄 Reset ROI", help="Clear current region of interest"):
            st.session_state.roi_points = []
            
        # Processing controls
        st.markdown("---")
        st.subheader("Processing Controls")
        col1, col2 = st.columns(2)
        if col1.button("▶ Start Processing", help="Begin video analysis"):
            if st.session_state.video_path and len(st.session_state.roi_points) >= 3:
                st.session_state.processing = True
            else:
                st.warning("Please select video and set valid ROI first")
        if col2.button("⏹ Stop Processing", help="Halt video analysis"):
            st.session_state.processing = False

    # Main content tabs
    tab1, tab2 = st.tabs(["🚥 Live Processing", "📊 Vehicle Analytics"])

    with tab1:
        # Video processing columns
        col1, col2 = st.columns(2)
        
        # ROI Selection
        if st.session_state.video_path and not st.session_state.processing:
            cap = cv2.VideoCapture(st.session_state.video_path)
            ret, frame = cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                st.session_state.frame = frame

                with col1:
                    st.subheader("📍 ROI Selection Panel")
                    try:
                        roi_data = image_selector(
                            image=frame,
                            selection_type="lasso",
                            key="roi_selector"
                        )
                        
                        if roi_data and "selection" in roi_data:
                            if "lasso" in roi_data["selection"]:
                                x_coords = roi_data["selection"]["lasso"][0]["x"]
                                y_coords = roi_data["selection"]["lasso"][0]["y"]
                                points = np.array(list(zip(x_coords, y_coords))).astype(int)
                                
                                if len(points) >= 3:
                                    st.session_state.roi_points = points
                                    st.success(f"ROI set with {len(points)} points")
                                    show_selection(frame, roi_data)
                                else:
                                    st.warning("At least 3 points required for ROI")
                    except Exception as e:
                        st.error(f"ROI selection error: {str(e)}")
                        st.session_state.roi_points = []
                cap.release()

        # Video processing display
        if st.session_state.processing and st.session_state.video_path:
            original_placeholder = col1.empty()
            processed_placeholder = col2.empty()
            progress_bar = st.progress(0)
            
            cap = cv2.VideoCapture(st.session_state.video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_count = 0

            while cap.isOpened() and st.session_state.processing:
                ret, frame = cap.read()
                if not ret:
                    break

                # Process frame
                processed_frame, tracked_objects = processor.process_frame(
                    frame, 
                    np.array(st.session_state.roi_points))
                
                # Update displays
                original_placeholder.image(frame, channels="BGR", use_container_width=True)
                processed_placeholder.image(processed_frame, channels="BGR", use_container_width=True)
                
                # Update progress
                frame_count += 1
                progress_bar.progress(min(frame_count / total_frames, 1.0))  # Ensure progress doesn't exceed 1.0
                
                # Add a small sleep to prevent UI freezing
                import time
                time.sleep(0.01)

            cap.release()
            st.session_state.processing = False
            progress_bar.empty()
            st.success("✅ Processing completed!")

    # Update the Vehicle Analytics tab section
    with tab2:
        st.markdown('<p class="header-style">Vehicle Analytics Dashboard</p>', unsafe_allow_html=True)
        
        # Add petrol pump ID input
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            petrol_pump_id = st.text_input("🔧 Enter Petrol Pump ID", value="IOCL-1", help="Enter the Petrol Pump ID to fetch details")
        
        with col_filter2:
            vehicle_id = st.text_input("🚗 Enter Vehicle ID (Optional)", help="Filter by specific vehicle if needed")

        # Add refresh button
        refresh_data = st.button("🔄 Refresh Data", help="Fetch latest vehicle details from server")

        if refresh_data:
            try:
                # Fetch data from API
                api_data = get_vehicle_details(petrol_pump_id, vehicle_id if vehicle_id else None)
                
                # If API is not available, use processor's tracked vehicles
                if not api_data:
                    api_data = [
                        {
                            "VehicleID": str(k),
                            "EnteringTime": v["entry_time"],
                            "ExitTime": v["exit_time"],
                            "FillingTime": "0 seconds" if not v["exit_time"] else self.calculate_filling_time(v["entry_time"], v["exit_time"]),
                            "ServerConnected": "1" if v["in_roi"] else "0"
                        }
                        for k, v in processor.tracked_vehicles.items()
                    ]
                
                # Process API response
                if api_data and isinstance(api_data, list):
                    # Convert API data to tracked_vehicles format
                    processed_data = {
                        item['VehicleID']: {
                            'vehicle_id': item['VehicleID'],
                            'entry_time': item['EnteringTime'],
                            'exit_time': item['ExitTime'],
                            'duration': float(item['FillingTime'].split()[0]) if item['FillingTime'] else 0,
                            'in_roi': item['ServerConnected'] == "1",
                            'last_seen': item['ExitTime'] if item['ExitTime'] else item['EnteringTime']
                        }
                        for item in api_data
                    }
                    st.session_state.tracked_vehicles = processed_data
                    st.success("✅ Data updated successfully!")
                else:
                    st.warning("⚠️ No data found for this Petrol Pump ID")
            
            except Exception as e:
                st.error(f"🔴 Error fetching data: {str(e)}")

        # Use the processor's tracked vehicles if no API data is available
        if not st.session_state.tracked_vehicles and processor.tracked_vehicles:
            st.session_state.tracked_vehicles = {
                str(k): {
                    'vehicle_id': str(k),
                    'entry_time': v["entry_time"],
                    'exit_time': v["exit_time"],
                    'duration': 0 if not v["exit_time"] or not v["entry_time"] else (
                        datetime.strptime(v["exit_time"], "%H:%M:%S") - 
                        datetime.strptime(v["entry_time"], "%H:%M:%S")).total_seconds(),
                    'in_roi': v["in_roi"],
                    'last_seen': datetime.now().strftime("%H:%M:%S")
                }
                for k, v in processor.tracked_vehicles.items()
                if v["entry_time"] is not None
            }

        # Metrics cards
        if st.session_state.tracked_vehicles:
            col1, col2, col3 = st.columns(3)
            
            # Current Vehicles in ROI
            with col1:
                current_vehicles = len([v for v in st.session_state.tracked_vehicles.values() 
                                    if v['in_roi'] and not v['exit_time']])
                st.markdown(f"""
                <div class="metric-card">
                    <h3>Active Vehicles</h3>
                    <p style="font-size: 24px; margin: 0;">{current_vehicles}</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Total Vehicles
            with col2:
                total_vehicles = len(st.session_state.tracked_vehicles)
                st.markdown(f"""
                <div class="metric-card">
                    <h3>Total Vehicles</h3>
                    <p style="font-size: 24px; margin: 0;">{total_vehicles}</p>
                </div>
                """, unsafe_allow_html=True)
            
            # Average Filling Time
            with col3:
                valid_times = [v['duration'] for v in st.session_state.tracked_vehicles.values() 
                            if v['duration'] > 0]
                avg_time = np.mean(valid_times) if valid_times else 0
                st.markdown(f"""
                <div class="metric-card">
                    <h3>Avg. Filling Time</h3>
                    <p style="font-size: 24px; margin: 0;">{avg_time:.1f} secs</p>
                </div>
                """, unsafe_allow_html=True)

            # Enhanced Data Table with API Data
            st.subheader("Detailed Vehicle Logs")
            df = pd.DataFrame.from_dict(st.session_state.tracked_vehicles, orient='index')
            
            # Add status indicator column
            df['status'] = np.where(
                df['exit_time'].isnull() | (df['exit_time'] == ''), 
                'Active 🟢', 
                'Completed 🔴'
            )
            
            # Format datetime columns if they exist
            datetime_cols = ['entry_time', 'exit_time', 'last_seen']
            for col in datetime_cols:
                if col in df.columns:
                    df[col] = df[col].fillna('')
            
            # Display enhanced table
            st.dataframe(
                df[['vehicle_id', 'entry_time', 'exit_time', 
                'duration', 'status', 'last_seen']],
                column_config={
                    "vehicle_id": "Vehicle ID",
                    "entry_time": "Entry Time",
                    "exit_time": "Exit Time",
                    "duration": "Duration (secs)",
                    "status": "Status",
                    "last_seen": "Last Update"
                },
                use_container_width=True,
                height=500,
                hide_index=True
            )
            
            # Add export button
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export to CSV",
                data=csv,
                file_name=f"vehicle_details_{petrol_pump_id}.csv",
                mime='text/csv'
            )
        else:
            st.info("ℹ️ No vehicle data available. Enter a Petrol Pump ID and click Refresh to load data.")


if __name__ == "__main__":
    main()