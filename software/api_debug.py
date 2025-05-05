import streamlit as st
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime
from api_client import get_request_stats, get_request_debug_logs, get_vehicle_status

# Set page configuration
st.set_page_config(
    page_title="API Request Debug Dashboard",
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
    .log-container {
        height: 400px;
        overflow-y: auto;
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        font-size: 12px;
        margin-bottom: 15px;
    }
    .status-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 10px;
        font-size: 12px;
        font-weight: bold;
        color: white;
    }
    .status-success {
        background-color: #28a745;
    }
    .status-pending {
        background-color: #ffc107;
        color: #212529;
    }
    .status-error {
        background-color: #dc3545;
    }
    .refresh-section {
        display: flex;
        align-items: center;
        margin-bottom: 10px;
    }
    .refresh-btn {
        margin-right: 15px;
    }
    .auto-refresh {
        display: flex;
        align-items: center;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Initialize session state
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = False
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 5
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()
    
    # Header
    st.markdown('<p class="header-style">API Request Debug Dashboard</p>', unsafe_allow_html=True)
    
    # Refresh controls
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown('<div class="refresh-section">', unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh Data", help="Fetch latest data", key="refresh_btn")
        
        auto_refresh = st.checkbox("Auto Refresh", value=st.session_state.auto_refresh, key="auto_refresh_check")
        if auto_refresh != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_refresh
            st.experimental_rerun()
        
        if st.session_state.auto_refresh:
            refresh_interval = st.select_slider(
                "Refresh Interval (seconds)",
                options=[1, 2, 3, 5, 10, 15, 30, 60],
                value=st.session_state.refresh_interval,
                key="refresh_interval_slider"
            )
            if refresh_interval != st.session_state.refresh_interval:
                st.session_state.refresh_interval = refresh_interval
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        current_time = datetime.now().strftime("%H:%M:%S")
        st.markdown(f"<div class='metric-card'><strong>Current Time:</strong><br/>{current_time}</div>", unsafe_allow_html=True)
    
    # Auto refresh logic
    if st.session_state.auto_refresh:
        current_time = time.time()
        if current_time - st.session_state.last_refresh > st.session_state.refresh_interval:
            refresh = True
            st.session_state.last_refresh = current_time
    
    # Main content tabs
    tabs = st.tabs(["📊 Overview", "📝 Request Logs", "🔍 Vehicle Details"])
    
    with tabs[0]:  # Overview Tab
        # Fetch current stats
        stats = get_request_stats()
        
        # Display metrics
        st.subheader("API Request Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Total Vehicles</h3>
                <p style="font-size: 24px; margin: 0;">{stats.get('total_vehicles', 0)}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            # Pending operations
            pending_posts = stats.get('posts_pending', 0)
            pending_puts = stats.get('puts_pending', 0)
            total_pending = pending_posts + pending_puts
            
            st.markdown(f"""
            <div class="metric-card">
                <h3>Pending Operations</h3>
                <p style="font-size: 24px; margin: 0;">{total_pending}</p>
                <p style="font-size: 14px; margin: 0;">(POST: {pending_posts}, PUT: {pending_puts})</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            # Success rate
            success_rate = stats.get('success_rate', 0)
            
            st.markdown(f"""
            <div class="metric-card">
                <h3>Success Rate</h3>
                <p style="font-size: 24px; margin: 0;">{success_rate:.1f}%</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            # Completed operations
            posts_completed = stats.get('posts_completed', 0)
            puts_completed = stats.get('puts_completed', 0)
            total_completed = posts_completed + puts_completed
            
            st.markdown(f"""
            <div class="metric-card">
                <h3>Completed Operations</h3>
                <p style="font-size: 24px; margin: 0;">{total_completed}</p>
                <p style="font-size: 14px; margin: 0;">(POST: {posts_completed}, PUT: {puts_completed})</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Vehicle status summary
        st.subheader("Vehicle Status Summary")
        
        all_vehicles = get_vehicle_status()
        if all_vehicles:
            # Convert to DataFrame
            df_vehicles = pd.DataFrame(all_vehicles)
            
            # Add status column
            def determine_status(row):
                if not row.get('posted', False):
                    return "POST Pending"
                elif row.get('put_attempted', False) and not row.get('put_completed', False):
                    return "PUT Pending"
                elif row.get('put_completed', True):
                    return "Completed"
                else:
                    return "In ROI"
            
            if len(df_vehicles) > 0:
                df_vehicles['status'] = df_vehicles.apply(determine_status, axis=1)
                
                # Count by status
                status_counts = df_vehicles['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                
                # Plot
                st.bar_chart(status_counts.set_index('Status'))
                
                # Show recent vehicles
                st.subheader("Recent Vehicles")
                
                # Sort by timestamp if available
                if 'post_timestamp' in df_vehicles.columns:
                    df_recent = df_vehicles.sort_values('post_timestamp', ascending=False).head(5)
                else:
                    df_recent = df_vehicles.tail(5)
                
                # Display nicely formatted recent vehicles
                for _, vehicle in df_recent.iterrows():
                    status = vehicle.get('status', 'Unknown')
                    track_id = vehicle.get('track_id', 'Unknown')
                    server_id = vehicle.get('server_vehicle_id', 'Not assigned')
                    posted = vehicle.get('posted', False)
                    put_completed = vehicle.get('put_completed', False)
                    
                    status_class = "status-success" if put_completed else "status-pending"
                    if not posted:
                        status_class = "status-error"
                    
                    st.markdown(f"""
                    <div class="metric-card">
                        <span class="status-badge {status_class}">{status}</span>
                        <h3>Vehicle ID: {track_id}</h3>
                        <p><strong>Server ID:</strong> {server_id}</p>
                        <p><strong>POST:</strong> {"Completed" if posted else "Pending"} | 
                           <strong>PUT:</strong> {"Completed" if put_completed else "Not Started/Pending"}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No vehicle data available.")
        else:
            st.info("No vehicle data available.")
    
    with tabs[1]:  # Request Logs Tab
        # Fetch debug logs
        logs = get_request_debug_logs()
        
        st.subheader("API Request Logs")
        
        # Filter options
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            filter_text = st.text_input("🔍 Filter Logs", help="Filter logs by text")
        
        with col2:
            filter_type = st.multiselect(
                "Filter by Type",
                options=["POST", "PUT", "SUCCESS", "DENIED", "FAILED", "TRACKED", "RETRY"],
                default=[]
            )
        
        with col3:
            max_logs = st.number_input("Max Logs", min_value=10, max_value=1000, value=100, step=10)
        
        # Apply filters
        filtered_logs = logs
        
        if filter_text:
            filtered_logs = [log for log in filtered_logs if filter_text.lower() in log.lower()]
        
        if filter_type:
            filtered_logs = [log for log in filtered_logs if any(t in log for t in filter_type)]
        
        # Limit number of logs
        filtered_logs = filtered_logs[-max_logs:] if len(filtered_logs) > max_logs else filtered_logs
        
        # Display logs
        if filtered_logs:
            # Color-code different log types
            formatted_logs = []
            for log in filtered_logs:
                if "SUCCESS" in log:
                    log = f'<span style="color: green;">{log}</span>'
                elif "FAILED" in log or "DENIED" in log:
                    log = f'<span style="color: red;">{log}</span>'
                elif "POST" in log:
                    log = f'<span style="color: blue;">{log}</span>'
                elif "PUT" in log:
                    log = f'<span style="color: purple;">{log}</span>'
                
                formatted_logs.append(log)
            
            logs_html = "<br>".join(formatted_logs)
            st.markdown(f'<div class="log-container">{logs_html}</div>', unsafe_allow_html=True)
            
            # Export logs
            logs_text = "\n".join(filtered_logs)
            st.download_button(
                label="📥 Export Logs",
                data=logs_text,
                file_name=f"api_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain"
            )
        else:
            st.info("No logs matching your filters.")
    
    with tabs[2]:  # Vehicle Details Tab
        st.subheader("Vehicle Details")
        
        # Search options
        col1, col2 = st.columns(2)
        
        with col1:
            search_track_id = st.text_input("🔍 Search by Track ID", help="Enter local tracking ID")
        
        with col2:
            search_server_id = st.text_input("🔍 Search by Server ID", help="Enter server-assigned ID")
        
        search_btn = st.button("🔍 Search", help="Find vehicle details")
        
        if search_btn or (st.session_state.auto_refresh and (search_track_id or search_server_id)):
            if search_track_id:
                vehicle = get_vehicle_status(track_id=search_track_id)
            elif search_server_id:
                vehicle = get_vehicle_status(server_id=search_server_id)
            else:
                vehicle = None
            
            if vehicle:
                # Format vehicle details for display
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                
                # Basic info
                track_id = vehicle.get('track_id', 'Unknown')
                server_id = vehicle.get('server_vehicle_id', 'Not assigned')
                
                st.markdown(f"### Vehicle ID: {track_id}")
                st.markdown(f"**Server ID:** {server_id}")
                
                # Status indicators
                posted = vehicle.get('posted', False)
                put_attempted = vehicle.get('put_attempted', False)
                put_completed = vehicle.get('put_completed', False)
                
                post_status = "✅ Completed" if posted else "❌ Pending"
                put_status = "✅ Completed" if put_completed else "❌ Pending" if put_attempted else "⏸️ Not Started"
                
                st.markdown(f"**POST Status:** {post_status}")
                st.markdown(f"**PUT Status:** {put_status}")
                
                # Timestamps
                post_time = vehicle.get('post_timestamp', 'Unknown')
                put_time = vehicle.get('put_timestamp', 'Not attempted')
                
                st.markdown(f"**POST Time:** {post_time}")
                st.markdown(f"**PUT Time:** {put_time}")
                
                # Retry information
                retry_count = vehicle.get('retry_count', 0)
                last_retry = vehicle.get('last_retry', 'Never')
                
                st.markdown(f"**Retry Count:** {retry_count}")
                st.markdown(f"**Last Retry:** {last_retry}")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Show payloads if available
                col1, col2 = st.columns(2)
                
                with col1:
                    post_payload = vehicle.get('post_payload')
                    if post_payload:
                        st.subheader("POST Payload")
                        st.json(post_payload)
                
                with col2:
                    put_payload = vehicle.get('put_payload')
                    if put_payload:
                        st.subheader("PUT Payload")
                        st.json(put_payload)
            else:
                st.warning("No vehicle found with the specified ID.")
        else:
            # Show all vehicles
            all_vehicles = get_vehicle_status()
            if all_vehicles:
                # Convert to DataFrame
                df_vehicles = pd.DataFrame(all_vehicles)
                
                # Select columns for display
                display_cols = [
                    'track_id', 'server_vehicle_id', 'posted', 'put_attempted', 
                    'put_completed', 'retry_count'
                ]
                
                display_cols = [col for col in display_cols if col in df_vehicles.columns]
                
                if len(display_cols) > 0:
                    # Rename columns for better display
                    rename_map = {
                        'track_id': 'Track ID',
                        'server_vehicle_id': 'Server ID',
                        'posted': 'POST Completed',
                        'put_attempted': 'PUT Attempted',
                        'put_completed': 'PUT Completed',
                        'retry_count': 'Retry Count'
                    }
                    
                    # Display data table
                    st.dataframe(
                        df_vehicles[display_cols].rename(columns=rename_map),
                        use_container_width=True,
                        height=400
                    )
                    
                    # Export options
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        csv = df_vehicles.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Export as CSV",
                            data=csv,
                            file_name=f"vehicle_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime='text/csv'
                        )
                    
                    with col2:
                        json_str = df_vehicles.to_json(orient='records')
                        st.download_button(
                            label="📥 Export as JSON",
                            data=json_str,
                            file_name=f"vehicle_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime='application/json'
                        )
                else:
                    st.info("No relevant data columns found.")
            else:
                st.info("No vehicle data available.")

if __name__ == "__main__":
    main()