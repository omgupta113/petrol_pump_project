# main.py (Streamlit entry point)
import streamlit as st
import cv2
import numpy as np
from video_processor import VideoProcessor
import tempfile
import os
from datetime import datetime

def main():
    st.set_page_config(
        page_title="Vehicle Tracking System",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state
    if 'roi_points' not in st.session_state:
        st.session_state.roi_points = []
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'tracked_vehicles' not in st.session_state:
        st.session_state.tracked_vehicles = {}
    
    # Initialize video processor
    processor = VideoProcessor()

    # Sidebar controls
    with st.sidebar:
        st.title("Controls")
        uploaded_file = st.file_uploader("Upload Video", type=["mp4", "avi", "mov"])
        st.session_state.video_path = None
        
        if uploaded_file is not None:
            # Save uploaded file to temp file
            tfile = tempfile.NamedTemporaryFile(delete=False) 
            tfile.write(uploaded_file.read())
            st.session_state.video_path = tfile.name
        
        # ROI Section
        st.subheader("ROI Configuration")
        if st.button("Reset ROI"):
            st.session_state.roi_points = []
            
        # Processing controls
        st.subheader("Processing")
        col1, col2 = st.columns(2)
        if col1.button("Start Processing"):
            if st.session_state.video_path and len(st.session_state.roi_points) >= 3:
                st.session_state.processing = True
            else:
                st.warning("Please select video and set valid ROI first")
        if col2.button("Stop Processing"):
            st.session_state.processing = False

    # Main content area
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Live Feed")
        video_placeholder = st.empty()
        
    with col2:
        st.subheader("Processed Feed")
        processed_placeholder = st.empty()
        
        # Statistics
        stats_col1, stats_col2 = st.columns(2)
        stats_col1.metric("Current Vehicles", len([v for v in st.session_state.tracked_vehicles.values() if v['in_roi']]))
        stats_col2.metric("Total Vehicles", len(st.session_state.tracked_vehicles))

    # ROI selection handling
    if st.session_state.video_path and not st.session_state.processing:
        cap = cv2.VideoCapture(st.session_state.video_path)
        ret, frame = cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with col1:
                st.image(frame, channels="RGB", use_column_width=True)
                
                # Get ROI points from user clicks
                if st.button("Click to select ROI points"):
                    st.session_state.roi_points = []
                    st.write("Click on the image above to select ROI points (minimum 3)")
                
                if st.session_state.roi_points:
                    st.write(f"ROI Points: {st.session_state.roi_points}")

    # Video processing loop
    if st.session_state.processing and st.session_state.video_path:
        cap = cv2.VideoCapture(st.session_state.video_path)
        
        while cap.isOpened() and st.session_state.processing:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Process frame
            processed_frame, tracked_objects = processor.process_frame(
                frame, 
                np.array(st.session_state.roi_points))
            
            # Update displays
            video_placeholder.image(frame, channels="BGR", use_column_width=True)
            processed_placeholder.image(processed_frame, channels="BGR", use_column_width=True)
            
            # Update statistics
            current_ids = {int(track[4]) for track in tracked_objects}
            st.session_state.tracked_vehicles.update(
                {track_id: {"in_roi": True} for track_id in current_ids}
            )
            
        cap.release()
        st.session_state.processing = False

if __name__ == "__main__":
    main()