import streamlit as st
import pandas as pd
import cv2
import numpy as np
from datetime import datetime
from video_processor import VideoProcessor
from streamlit_extras.image_selector import image_selector, show_selection
from api_client import get_vehicle_details
import tempfile
import time
import os
import shutil

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
    .source-selection {
        padding: 15px;
        border: 1px solid #ddd;
        border-radius: 10px;
        margin-bottom: 15px;
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
        'source_path': None,
        'show_roi_selection': False,
        'temp_dir': None,
        'source_type': 'file',  # Default source type: 'file' or 'rtsp'
        'rtsp_url': '',
    }
    for key, value in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Create a dedicated temp directory for this session if not exists
    if not st.session_state.temp_dir:
        # Create a unique temp directory for this session
        st.session_state.temp_dir = tempfile.mkdtemp()
        
    # Initialize video processor (create only once)
    if 'processor' not in st.session_state:
        st.session_state.processor = VideoProcessor()

    # Sidebar controls
    with st.sidebar:
        st.markdown('<p class="header-style">Control Panel</p>', unsafe_allow_html=True)
        
        # Source selection
        st.subheader("📹 Video Source")
        source_type = st.radio("Select Source Type", 
                              ["File Upload", "RTSP Stream"],
                              index=0 if st.session_state.source_type == 'file' else 1)
        
        st.session_state.source_type = 'file' if source_type == "File Upload" else 'rtsp'
        
        # File upload or RTSP URL based on selection
        if st.session_state.source_type == 'file':
            # File uploader
            uploaded_file = st.file_uploader("📤 Upload Surveillance Video", type=["mp4", "avi", "mov"])
            if uploaded_file is not None:
                # Save the file with its original name in our temp directory
                file_extension = os.path.splitext(uploaded_file.name)[1].lower()
                video_path = os.path.join(st.session_state.temp_dir, f"video{file_extension}")
                
                # Write uploaded file to disk with proper extension
                with open(video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Verify the file exists and is readable
                if os.path.exists(video_path) and os.access(video_path, os.R_OK):
                    st.session_state.source_path = video_path
                    st.session_state.show_roi_selection = True
                    st.sidebar.success(f"Video saved at: {video_path}")
                else:
                    st.sidebar.error(f"Failed to save video at: {video_path}")
        else:
            # RTSP URL input
            rtsp_url = st.text_input(
                "🔗 Enter RTSP URL",
                value=st.session_state.rtsp_url,
                placeholder="rtsp://username:password@ip_address:port/path"
            )
            
            # Save RTSP URL to session state
            if rtsp_url != st.session_state.rtsp_url:
                st.session_state.rtsp_url = rtsp_url
            
            # Validate and set RTSP URL
            if st.button("✅ Connect to RTSP Stream"):
                if rtsp_url.startswith("rtsp://"):
                    # Test RTSP connection
                    cap = cv2.VideoCapture(rtsp_url)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret:
                            st.session_state.source_path = rtsp_url
                            st.session_state.show_roi_selection = True
                            st.sidebar.success("RTSP stream connected successfully!")
                            
                            # Save a frame for ROI selection
                            frame_path = os.path.join(st.session_state.temp_dir, "rtsp_frame.jpg")
                            cv2.imwrite(frame_path, frame)
                        else:
                            st.sidebar.error("Could not read from RTSP stream. Check URL and try again.")
                        cap.release()
                    else:
                        st.sidebar.error("Failed to connect to RTSP stream. Check URL and try again.")
                else:
                    st.sidebar.error("Invalid RTSP URL. URL should start with 'rtsp://'")
        
        # ROI Section
        st.markdown("---")
        st.subheader("🎯 ROI Configuration")
        if st.button("🔄 Reset ROI", help="Clear current region of interest"):
            st.session_state.roi_points = []
            st.session_state.show_roi_selection = True
            
        # Processing controls
        st.markdown("---")
        st.subheader("⚙️ Processing Controls")
        col1, col2 = st.columns(2)
        
        start_button = col1.button("▶ Start Processing", help="Begin video analysis")
        stop_button = col2.button("⏹ Stop Processing", help="Halt video analysis")
        
        if start_button:
            if st.session_state.source_path and len(st.session_state.roi_points) >= 3:
                # Start processing with the source path and ROI points
                success = st.session_state.processor.start_processing(
                    st.session_state.source_path, 
                    np.array(st.session_state.roi_points)
                )
                if success:
                    st.session_state.processing = True
                    st.session_state.show_roi_selection = False
                    st.sidebar.success(f"Started processing from: {st.session_state.source_path}")
                else:
                    source_type = "RTSP stream" if st.session_state.source_type == "rtsp" else "video file"
                    st.sidebar.error(f"Failed to start processing from {source_type}")
            else:
                if not st.session_state.source_path:
                    st.warning("Please select a video source first")
                elif len(st.session_state.roi_points) < 3:
                    st.warning("Please define a valid ROI with at least 3 points")
        
        if stop_button:
            st.session_state.processor.stop_processing()
            st.session_state.processing = False

    # Main content tabs
    tab1, tab2 = st.tabs(["🚥 Live Processing", "📊 Vehicle Analytics"])

    with tab1:
        # Video processing columns
        col1, col2 = st.columns(2)
        
        # ROI Selection
        if st.session_state.show_roi_selection and st.session_state.source_path:
            try:
                frame = None
                if st.session_state.source_type == 'rtsp':
                    # For RTSP, use the saved frame
                    frame_path = os.path.join(st.session_state.temp_dir, "rtsp_frame.jpg")
                    if os.path.exists(frame_path):
                        frame = cv2.imread(frame_path)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                else:
                    # For video file, get the first frame
                    cap = cv2.VideoCapture(st.session_state.source_path)
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                if frame is not None:
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
                else:
                    source_type = "RTSP stream" if st.session_state.source_type == "rtsp" else "video file"
                    st.error(f"Could not read from {source_type}: {st.session_state.source_path}")
            except Exception as e:
                source_type = "RTSP stream" if st.session_state.source_type == "rtsp" else "video file"
                st.error(f"Error opening {source_type}: {str(e)}")

        # Video processing display
        if st.session_state.processing:
            # Create placeholders for display
            progress_container = st.container()
            progress_bar = progress_container.progress(0)
            original_placeholder = col1.empty()
            processed_placeholder = col2.empty()
            stats_container = st.empty()
            
            # Main display loop
            while st.session_state.processing:
                # Get the current frames from the processor
                original_frame, processed_frame = st.session_state.processor.get_current_frames()
                progress, total_frames, is_processing, fps = st.session_state.processor.get_progress()
                
                # Only update UI if valid frames exist
                if original_frame is not None and processed_frame is not None:
                    # Update displays
                    original_placeholder.image(
                        cv2.cvtColor(original_frame, cv2.COLOR_BGR2RGB), 
                        caption="Original Video",
                        use_container_width=True
                    )
                    
                    processed_placeholder.image(
                        cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB), 
                        caption="Processed Video with Tracking",
                        use_container_width=True
                    )
                    
                    # Update progress
                    if st.session_state.source_type == 'rtsp':
                        # For RTSP streams, show a "live" indicator instead of progress
                        progress_container.markdown("""
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <div style="background-color: #FF0000; width: 15px; height: 15px; border-radius: 50%; margin-right: 10px;"></div>
                            <span style="font-weight: bold;">LIVE STREAM</span>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # For video files, show progress bar
                        progress_bar.progress(progress)
                    
                    # Display stats
                    stats_container.markdown(f"""
                    <div style="display: flex; justify-content: space-around; flex-wrap: wrap;">
                        <div class="metric-card" style="flex: 1; min-width: 200px; margin: 5px;">
                            <p style="font-weight: bold;">Processing FPS</p>
                            <p style="font-size: 20px;">{fps:.1f}</p>
                        </div>
                        <div class="metric-card" style="flex: 1; min-width: 200px; margin: 5px;">
                            <p style="font-weight: bold;">Tracked Vehicles</p>
                            <p style="font-size: 20px;">{len(st.session_state.processor.tracked_vehicles)}</p>
                        </div>
                        <div class="metric-card" style="flex: 1; min-width: 200px; margin: 5px;">
                            <p style="font-weight: bold;">Source Type</p>
                            <p style="font-size: 20px;">{"RTSP Stream" if st.session_state.source_type == 'rtsp' else "Video File"}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Check if processing has finished (only for video files)
                if not is_processing and st.session_state.source_type != 'rtsp':
                    st.success("✅ Processing completed!")
                    st.session_state.processing = False
                    break
                
                # Add a small delay to reduce CPU usage
                time.sleep(0.1)
                
                # Check if user stopped processing
                if not st.session_state.processing:
                    break
                    
            # Final update after processing completes
            if not is_processing:
                st.success("Processing finished")

    # Update the Vehicle Analytics tab section 
    with tab2:
        st.markdown('<p class="header-style">Vehicle Analytics Dashboard</p>', unsafe_allow_html=True)
        
        # Add petrol pump ID input
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            petrol_pump_id = st.text_input("🔧 Enter Petrol Pump ID", help="Enter the Petrol Pump ID to fetch details")
        
        with col_filter2:
            vehicle_id = st.text_input("🚗 Enter Vehicle ID (Optional)", help="Filter by specific vehicle if needed")

        # Add refresh button
        refresh_data = st.button("🔄 Refresh Data", help="Fetch latest vehicle details from server")

        # Option to use local data from processor
        use_local_data = st.checkbox("Use Local Processing Data (No API Call)", value=True)

        if refresh_data and not use_local_data:
            try:
                # Show loading indicator
                with st.spinner("Fetching data from API..."):
                    # Fetch data from API
                    api_data = get_vehicle_details(petrol_pump_id, vehicle_id if vehicle_id else None)
                    
                    # Process API response
                    if api_data and isinstance(api_data, list) and len(api_data) > 0:
                        # Convert API data to tracked_vehicles format
                        processed_data = {}
                        
                        for item in api_data:
                            try:
                                # Extract filling time duration safely
                                duration = 0
                                filling_time_str = item.get('FillingTime', '')
                                if filling_time_str and isinstance(filling_time_str, str):
                                    try:
                                        # Extract number from string like "30 seconds"
                                        duration_parts = filling_time_str.split()
                                        if len(duration_parts) > 0:
                                            duration = float(duration_parts[0])
                                    except (ValueError, IndexError) as e:
                                        st.warning(f"Could not parse filling time '{filling_time_str}': {e}")
                                
                                # Get vehicle ID safely
                                vehicle_id = item.get('VehicleID', f"unknown-{len(processed_data)}")
                                
                                # Get entry and exit times
                                entry_time = item.get('EnteringTime', '')
                                exit_time = item.get('ExitTime', '')
                                
                                # Determine if vehicle is still in ROI
                                in_roi = False
                                
                                # Add to processed data
                                processed_data[vehicle_id] = {
                                    'vehicle_id': vehicle_id,
                                    'entry_time': entry_time,
                                    'exit_time': exit_time,
                                    'duration': duration,
                                    'in_roi': in_roi,
                                    'last_seen': exit_time if exit_time else entry_time,
                                    'vehicle_type': item.get('VehicleType', 'Unknown')
                                }
                            except Exception as e:
                                st.error(f"Error processing vehicle: {str(e)}")
                        
                        st.session_state.tracked_vehicles = processed_data
                        st.success("✅ Data updated successfully!")
                    else:
                        st.warning("⚠️ No data found for this Petrol Pump ID")
            
            except Exception as e:
                st.error(f"🔴 Error fetching data: {str(e)}")
        
        elif refresh_data and use_local_data:
            # Use local data from processor
            if hasattr(st.session_state.processor, 'tracked_vehicles'):
                # Convert processor data to the expected format
                local_data = {}
                for vehicle_id, vehicle_data in st.session_state.processor.tracked_vehicles.items():
                    try:
                        duration = 0
                        if vehicle_data.get("entry_time") and vehicle_data.get("exit_time"):
                            try:
                                entry = datetime.strptime(vehicle_data["entry_time"], "%H:%M:%S")
                                exit = datetime.strptime(vehicle_data["exit_time"], "%H:%M:%S")
                                duration = (exit - entry).total_seconds()
                            except Exception as e:
                                st.warning(f"Error calculating duration: {e}")
                                duration = 0
                        
                        # Use server vehicle ID if available, otherwise use local ID
                        display_vehicle_id = vehicle_data.get("server_vehicle_id", str(vehicle_id))
                        
                        local_data[display_vehicle_id] = {
                            'vehicle_id': display_vehicle_id,
                            'entry_time': vehicle_data.get("entry_time", ""),
                            'exit_time': vehicle_data.get("exit_time", ""),
                            'duration': duration,
                            'in_roi': vehicle_data.get("in_roi", False),
                            'last_seen': vehicle_data.get("exit_time") if vehicle_data.get("exit_time") else vehicle_data.get("entry_time", ""),
                            'vehicle_type': vehicle_data.get("vehicle_type", "Unknown")
                        }
                    except Exception as e:
                        st.error(f"Error processing vehicle {vehicle_id}: {e}")
                
                st.session_state.tracked_vehicles = local_data
                st.success("✅ Local data loaded successfully!")
            else:
                st.warning("⚠️ No local tracking data available yet")


        # Display tracked vehicle data
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

            # Enhanced Data Table
            st.subheader("Detailed Vehicle Logs")
            try:
                df = pd.DataFrame.from_dict(st.session_state.tracked_vehicles, orient='index')
                
                # Add status indicator column
                df['status'] = np.where(
                    df['exit_time'].isnull(), 
                    'Active 🟢', 
                    'Completed 🔴'
                )
                
                # Convert duration from seconds to a readable format
                df['duration_str'] = df['duration'].apply(
                    lambda x: f"{int(x // 60)}m {int(x % 60)}s" if not pd.isna(x) else ""
                )
                
                # Display enhanced table
                st.dataframe(
                    df[['vehicle_id', 'entry_time', 'exit_time', 
                    'duration_str', 'status', 'last_seen']],
                    column_config={
                        "vehicle_id": "Vehicle ID",
                        "entry_time": "Entry Time",
                        "exit_time": "Exit Time",
                        "duration_str": "Duration",
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
                    file_name=f"vehicle_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )
            except Exception as e:
                st.error(f"Error processing vehicle data: {str(e)}")
        else:
            st.info("ℹ️ No vehicle data available. Use the 'Refresh Data' button to load data.")
    
    # Clean up temp files when session ends
    def cleanup():
        if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
            try:
                shutil.rmtree(st.session_state.temp_dir)
                print(f"Cleaned up temp directory: {st.session_state.temp_dir}")
            except Exception as e:
                print(f"Error cleaning up temp directory: {e}")
    
    # Register cleanup function
    import atexit
    atexit.register(cleanup)
            
if __name__ == "__main__":
    main()