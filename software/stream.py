import streamlit as st
from video_processor import VideoProcessor
from streamlit_extras.image_selector import image_selector, show_selection
import os
# os.environ['PYTHON_ASYNCIO_EVENT_LOOP_POLICY'] = 'asyncio.DefaultEventLoopPolicy'

import asyncio
import nest_asyncio
nest_asyncio.apply()


def main():
    st.set_page_config(page_title="Vehicle Tracking System Pro", layout="wide")

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
    if 'video_processor' not in st.session_state:
        st.session_state.video_processor = None
        # om=VideoProcessor()
    
    # Page layout
    st.title("Vehicle Tracking System Pro")

    # Sidebar controls
    with st.sidebar:
        st.header("Controls")
        
        # File upload
        uploaded_file = st.file_uploader("Upload Video", type=["mp4", "avi", "mov"])
        if uploaded_file:
            st.session_state.video_path = uploaded_file
            st.success(f"File uploaded: {uploaded_file.name}")
        
        # ROI Selection
        roi_col1, roi_col2 = st.columns(2)
        with roi_col1:
            st.button("Select ROI")
        with roi_col2:
            st.button("Reset ROI")
        
        # Processing controls
        proc_col1, proc_col2 = st.columns(2)
        with proc_col1:
            st.button("Start Processing")
        with proc_col2:
            st.button("Stop Processing")
        
        # Statistics
        st.header("Statistics")
        st.metric("Current Vehicles", 0)
        st.metric("Total Vehicles", 0)

    # Main content area
    main_col1, main_col2 = st.columns([3, 1])
    
    with main_col1:
        st.header("Video Feed")
        video_placeholder = st.empty()
        video_placeholder.image("https://via.placeholder.com/800x450?text=Video+Feed", 
                              use_container_width=True)
    
    with main_col2:
        st.header("ROI Points")
        st.write("No ROI points selected")

def save_uploaded_file(uploaded_file):
    """Save uploaded file to temporary location"""
    if not os.path.exists("temp"):
        os.makedirs("temp")
    
    file_path = os.path.join("temp", uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


if __name__ == "__main__":
    main()