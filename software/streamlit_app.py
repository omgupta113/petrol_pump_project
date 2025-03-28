import streamlit as st
import cv2
import numpy as np
from datetime import datetime
import os
import time
from video_processor import VideoProcessor

def main():
    st.set_page_config(page_title="Vehicle Tracking System Pro", layout="wide")
    
    # Initialize session state variables
    if 'video_path' not in st.session_state:
        st.session_state.video_path = None
    if 'roi_points' not in st.session_state:
        st.session_state.roi_points = []
    if 'is_processing' not in st.session_state:
        st.session_state.is_processing = False
    if 'tracked_ids' not in st.session_state:
        st.session_state.tracked_ids = set()
    if 'current_vehicles' not in st.session_state:
        st.session_state.current_vehicles = 0
    if 'total_vehicles' not in st.session_state:
        st.session_state.total_vehicles = 0
    if 'cap' not in st.session_state:
        st.session_state.cap = None
    if 'output_video' not in st.session_state:
        st.session_state.output_video = None
    if 'frame' not in st.session_state:
        st.session_state.frame = None

    # Initialize video processor
    if 'video_processor' not in st.session_state:
        st.session_state.video_processor = VideoProcessor()

    # Page layout
    st.title("Vehicle Tracking System Pro")

    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        
        # File upload
        uploaded_file = st.file_uploader("Upload Video", type=["mp4", "avi", "mov"])
        if uploaded_file:
            st.session_state.video_path = save_uploaded_file(uploaded_file)
            st.success(f"File uploaded: {uploaded_file.name}")
        
        # ROI Selection
        if st.button("Select ROI"):
            if st.session_state.video_path:
                select_roi()
            else:
                st.error("Please upload a video file first")
        
        # Processing controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Processing", disabled=not st.session_state.roi_points or st.session_state.is_processing):
                start_processing()
        with col2:
            if st.button("Stop Processing", disabled=not st.session_state.is_processing):
                stop_processing()
        
        if st.button("Reset ROI"):
            reset_roi()
        
        # Statistics
        st.header("Statistics")
        st.metric("Current Vehicles", st.session_state.current_vehicles)
        st.metric("Total Vehicles", st.session_state.total_vehicles)

    # Main content area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("Video Feed")
        video_placeholder = st.empty()
        
        if st.session_state.frame is not None:
            video_placeholder.image(st.session_state.frame, channels="BGR", use_column_width=True)
    
    with col2:
        st.header("ROI Points")
        st.write(st.session_state.roi_points)

    # Video processing loop
    if st.session_state.is_processing:
        process_video(video_placeholder)

def save_uploaded_file(uploaded_file):
    """Save uploaded file to temporary location"""
    if not os.path.exists("temp"):
        os.makedirs("temp")
    
    file_path = os.path.join("temp", uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def select_roi():
    """Handle ROI selection using Streamlit"""
    cap = cv2.VideoCapture(st.session_state.video_path)
    ret, frame = cap.read()
    if ret:
        st.session_state.roi_points = []
        st.session_state.frame = frame
        cap.release()
        st.experimental_set_query_params(page="roi_selection")
        st.rerun()

def reset_roi():
    """Reset ROI points"""
    st.session_state.roi_points = []
    st.success("ROI reset successfully")

def start_processing():
    """Initialize video processing"""
    st.session_state.is_processing = True
    st.session_state.cap = cv2.VideoCapture(st.session_state.video_path)
    
    # Get video properties
    width = int(st.session_state.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(st.session_state.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(st.session_state.cap.get(cv2.CAP_PROP_FPS))
    
    # Create output video writer
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"output_{timestamp}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    st.session_state.output_video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    st.session_state.tracked_ids = set()
    st.session_state.total_vehicles = 0
    st.session_state.current_vehicles = 0

def stop_processing():
    """Stop video processing"""
    st.session_state.is_processing = False
    if st.session_state.cap:
        st.session_state.cap.release()
    if st.session_state.output_video:
        st.session_state.output_video.release()
    st.success("Processing stopped")

def process_video(placeholder):
    """Process video frames"""
    cap = st.session_state.cap
    while st.session_state.is_processing and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            stop_processing()
            break
        
        # Process frame
        processed_frame, tracked_objects = st.session_state.video_processor.process_frame(
            frame, st.session_state.roi_points
        )
        
        # Update display
        placeholder.image(processed_frame, channels="BGR", use_column_width=True)
        
        # Update counters
        update_counters(tracked_objects)
        
        # Save frame
        st.session_state.output_video.write(processed_frame)
        
        # Add small delay to allow UI updates
        time.sleep(0.01)

def update_counters(tracked_objects):
    """Update vehicle counters"""
    st.session_state.current_vehicles = len(tracked_objects)
    current_ids = {int(track[4]) for track in tracked_objects}
    st.session_state.tracked_ids.update(current_ids)
    st.session_state.total_vehicles = len(st.session_state.tracked_ids)

if __name__ == "__main__":
    main()