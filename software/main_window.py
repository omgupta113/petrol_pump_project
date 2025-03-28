import tkinter as tk
from tkinter import filedialog
import cv2
import numpy as np
from datetime import datetime
from PIL import Image, ImageTk
import os
import time
from custom_widgets import ModernCard, AnimatedButton
from video_processor import VideoProcessor
from styles import UIStyle
from config import Config
import ttkbootstrap as ttk
from ttkbootstrap.style import Style
from tkinter import ttk

class ScrollableFrame(ttk.Frame):
    """A scrollable frame widget"""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        # Create a canvas and scrollbar
        self.canvas = tk.Canvas(self)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Create the scrollable frame inside the canvas
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # Configure the canvas
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # Create a window inside the canvas for the scrollable frame
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Configure canvas to expand with window
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        # Bind mouse wheel to scrolling
        self.scrollable_frame.bind('<Enter>', self._bind_mouse_scroll)
        self.scrollable_frame.bind('<Leave>', self._unbind_mouse_scroll)

        # Pack the canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Configure the canvas to use the scrollbar
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

    def on_canvas_configure(self, event):
        """Update the canvas window size when the canvas is resized"""
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def _on_mouse_scroll(self, event):
        """Handle mouse wheel scrolling"""
        self.canvas.yview_scroll(-1 * int((event.delta / 120)), "units")

    def _bind_mouse_scroll(self, event):
        """Bind mouse wheel to scrolling when mouse enters the frame"""
        self.canvas.bind_all("<MouseWheel>", self._on_mouse_scroll)

    def _unbind_mouse_scroll(self, event):
        """Unbind mouse wheel when mouse leaves the frame"""
        self.canvas.unbind_all("<MouseWheel>")

class VehicleTrackingUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Vehicle Tracking System Pro")
        
        # Initialize style
        self.style = Style(theme="darkly")
        UIStyle.configure_styles(self.style)
        
        # Initialize variables and objects
        self.video_processor = VideoProcessor()
        self.initialize_variables()
        
        # Create UI elements
        self.create_ui()

    def initialize_variables(self):
    # Video processing variables
        self.video_path = None
        self.cap = None
        self.output_video = None
        self.is_processing = False
    
    # ROI selection variables
        self.roi_points = []
        self.temp_roi_frame = None
    
    # Tracking variables
        self.tracked_ids = set()
        self.current_vehicles = 0
        self.total_vehicles = 0


    def create_ui(self):
        """Create modern UI with cards and animations"""
        # Create main container with scrolling
        self.main_container = ScrollableFrame(self.root)
        self.main_container.pack(fill="both", expand=True)
        
        # Create content frame inside scrollable frame
        content_frame = ttk.Frame(self.main_container.scrollable_frame, padding="20")
        content_frame.pack(fill="both", expand=True)
        
        # Control Card
        control_card = ModernCard(content_frame, "Controls")
        control_card.pack(fill="x", pady=(0, 10))
        
        # File selection
        file_frame = ttk.Frame(control_card.content)
        file_frame.pack(fill="x", pady=5)
        
        ttk.Label(file_frame, text="Video File:").pack(side="left")
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, width=50).pack(side="left", padx=5)
        AnimatedButton(file_frame, text="Browse", command=self.browse_file, style="Action.TButton").pack(side="left")
        
        # Control buttons
        buttons_frame = ttk.Frame(control_card.content)
        buttons_frame.pack(fill="x", pady=10)
        
        AnimatedButton(buttons_frame, text="Select ROI", command=self.select_roi, style="Action.TButton").pack(side="left", padx=5)
        self.start_button = AnimatedButton(buttons_frame, text="Start Processing", command=self.start_processing, state="disabled", style="Action.TButton")
        self.start_button.pack(side="left", padx=5)
        self.stop_button = AnimatedButton(buttons_frame, text="Stop", command=self.stop_processing, state="disabled", style="Action.TButton")
        self.stop_button.pack(side="left", padx=5)
        AnimatedButton(buttons_frame, text="Reset ROI", command=self.reset_roi, style="Action.TButton").pack(side="left", padx=5)
        
        # Video Card
        video_card = ModernCard(content_frame, "Video Feed")
        video_card.pack(fill="both", expand=True, pady=10)
        
        self.video_label = ttk.Label(video_card.content)
        self.video_label.pack(pady=10)
        
        # Statistics Card
        stats_card = ModernCard(content_frame, "Vehicle Statistics")
        stats_card.pack(fill="x", pady=10)
        
        stats_frame = ttk.Frame(stats_card.content)
        stats_frame.pack(fill="x", pady=5)
        
        # Current vehicles with animation
        self.current_count_var = tk.StringVar(value="Current Vehicles: 0")
        self.current_count_label = ttk.Label(stats_frame, textvariable=self.current_count_var, style="Counter.TLabel")
        self.current_count_label.pack(side="left", padx=20)
        
        # Total vehicles with animation
        self.total_count_var = tk.StringVar(value="Total Vehicles: 0")
        self.total_count_label = ttk.Label(stats_frame, textvariable=self.total_count_var, style="Counter.TLabel")
        self.total_count_label.pack(side="left", padx=20)
        
        # Status bar with gradient
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(content_frame, textvariable=self.status_var, style="Status.TLabel").pack(fill="x", pady=(10, 0))

    # [Rest of the VehicleTrackingUI class methods remain the same]

    def animate_counter_update(self, label, old_value, new_value, duration=500):
        """Animate counter updates"""
        start_time = time.time()
        
        def update():
            current_time = time.time()
            progress = min(1.0, (current_time - start_time) * 1000 / duration)
            
            if progress < 1.0:
                current_value = int(old_value + (new_value - old_value) * progress)
                label.configure(text=f"Vehicles: {current_value}")
                self.root.after(16, update)
            else:
                label.configure(text=f"Vehicles: {new_value}")
        
        update()

    def reset_roi(self):
        """Reset ROI selection"""
        self.roi_points = []
        self.start_button.configure(state="disabled")
        self.status_var.set("ROI reset. Please select a new ROI.")

    def browse_file(self):
        """Open file dialog to select video file"""
        self.video_path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.avi *.mov")]
        )
        if self.video_path:
            self.file_path_var.set(self.video_path)
            self.status_var.set(f"Selected video: {os.path.basename(self.video_path)}")

    def select_roi(self):
        """Open video and allow user to select ROI"""
        if not self.video_path:
            self.status_var.set("Please select a video file first")
            return

        self.cap = cv2.VideoCapture(self.video_path)
        ret, frame = self.cap.read()
        if not ret:
            self.status_var.set("Error reading video file")
            return

        self.temp_roi_frame = frame.copy()
        roi_window_name = "Select ROI - Click points to create polygon, press 'c' to close, 'r' to reset, 'q' to quit"
        cv2.namedWindow(roi_window_name)
        cv2.setMouseCallback(roi_window_name, self.roi_mouse_callback)

        while True:
            display_frame = self.temp_roi_frame.copy()
            
            # Draw all points and lines
            if len(self.roi_points) > 0:
                points = np.array(self.roi_points, np.int32)
                cv2.polylines(display_frame, [points.reshape((-1, 1, 2))], 
                            False, (0, 255, 0), 2)
                
                # Draw points
                for point in self.roi_points:
                    cv2.circle(display_frame, tuple(point), 5, (0, 255, 0), -1)

            cv2.imshow(roi_window_name, display_frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):  # Quit without saving
                self.roi_points = []
                break
            elif key == ord('c'):  # Close polygon
                if len(self.roi_points) >= 3:
                    self.roi_points = np.array(self.roi_points, np.int32)
                    break
            elif key == ord('r'):  # Reset points
                self.roi_points = []
                self.temp_roi_frame = frame.copy()

        cv2.destroyAllWindows()
        self.cap.release()

        if len(self.roi_points) >= 3:
            self.start_button.configure(state="normal")
            self.status_var.set("ROI selected successfully")
        else:
            self.roi_points = []
            self.start_button.configure(state="disabled")
            self.status_var.set("ROI selection cancelled or incomplete")

    def roi_mouse_callback(self, event, x, y, flags, param):
        """Handle mouse events for ROI selection"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.roi_points.append([x, y])
            # Draw point
            cv2.circle(self.temp_roi_frame, (x, y), 5, (0, 255, 0), -1)
            
            # Draw line if there are at least two points
            if len(self.roi_points) > 1:
                cv2.line(self.temp_roi_frame,
                        tuple(self.roi_points[-2]),
                        tuple(self.roi_points[-1]),
                        (0, 255, 0), 2)

    def update_video_display(self, frame):
        """Update the video display in the UI"""
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = Image.fromarray(frame)
        # Resize while maintaining aspect ratio
        display_width = 800
        ratio = display_width / frame.width
        display_height = int(frame.height * ratio)
        frame = frame.resize((display_width, display_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image=frame)
        self.video_label.configure(image=photo)
        self.video_label.image = photo

    def update_counters(self, tracked_objects):
        """Update vehicle counters in the UI"""
        self.current_vehicles = len(tracked_objects)
        current_ids = {int(track[4]) for track in tracked_objects}
        self.tracked_ids.update(current_ids)
        self.total_vehicles = len(self.tracked_ids)
        
        self.current_count_var.set(f"Current Vehicles in ROI: {self.current_vehicles}")
        self.total_count_var.set(f"Total Unique Vehicles: {self.total_vehicles}")

    def start_processing(self):
        """Start video processing"""
        if not self.video_path or len(self.roi_points) < 3:
            self.status_var.set("Please select video and valid ROI first")
            return

        if self.is_processing:
            return

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.status_var.set("Error opening video file")
            return

        # Get video properties
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(self.cap.get(cv2.CAP_PROP_FPS))

        # Create output video writer
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"output_{timestamp}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.output_video = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        self.is_processing = True
        self.tracked_ids.clear()
        self.total_vehicles = 0
        self.current_vehicles = 0
        self.status_var.set("Processing video...")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.process_video()

    def stop_processing(self):
        """Stop video processing"""
        self.is_processing = False
        if self.cap is not None:
            self.cap.release()
        if self.output_video is not None:
            self.output_video.release()
        self.status_var.set("Processing stopped")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def process_video(self):
        """Process video frames continuously"""
        if not self.is_processing:
            return
            
        ret, frame = self.cap.read()
        if not ret:
            self.stop_processing()
            return
            
        # Process frame
        processed_frame, tracked_objects = self.video_processor.process_frame(frame, self.roi_points)
        
        # Update video display
        self.update_video_display(processed_frame)
        
        # Update counters
        self.update_counters(tracked_objects)
        
        # Save frame
        self.output_video.write(processed_frame)
        
        # Continue processing
        self.root.after(10, self.process_video)