"""
sensor_panel.py
PURPOSE: Display current sensor values as text/numbers
"""

import tkinter as tk
from tkinter import ttk


class SensorPanel:
    def __init__(self, parent_frame, sensor_configs):
        """
        Initialize the sensor display panel.

        Args:
            parent_frame: tkinter frame to put displays in
            sensor_configs: combined list of thermocouple and pressure configs
        """
        self.parent = parent_frame
        self.displays = {}        # sensor_name: Label widget for value
        self.status_labels = {}   # sensor_name: Label widget for status
        self.frames = {}          # sensor_name: LabelFrame widget

        # Configure grid weights for even distribution
        for i in range(4):
            parent_frame.columnconfigure(i, weight=1)

        # Create a label for each sensor
        for i, sensor in enumerate(sensor_configs):
            if not sensor.get('enabled', True):
                continue

            name = sensor['name']
            units = sensor.get('units', '')

            # Create frame for this sensor
            frame = ttk.LabelFrame(parent_frame, text=name)
            frame.grid(row=i//4, column=i%4, padx=5, pady=5, sticky='nsew')
            self.frames[name] = frame

            # Large number display
            value_label = ttk.Label(
                frame,
                text="--.-",
                font=('Arial', 24, 'bold')
            )
            value_label.pack(padx=10, pady=0)

            # Units label
            units_label = ttk.Label(frame, text=units)
            units_label.pack(pady=(0, 5))

            # Status indicator
            status_label = ttk.Label(
                frame,
                text="WAITING",
                font=('Arial', 8, 'italic'),
                foreground='gray'
            )
            status_label.pack(side=tk.BOTTOM, pady=2)

            self.displays[name] = value_label
            self.status_labels[name] = status_label

    def update(self, readings):
        """
        Update displayed values and status.

        Args:
            readings: dict like {'TC1': 25.3, 'P1': 45.2}
        """
        for name, value in readings.items():
            if name in self.displays:
                if value is None:
                    # Sensor is enabled but not returning data (or returning -9999)
                    self.displays[name].config(text="---", foreground='gray')
                    self.status_labels[name].config(text="DISCONNECTED", foreground='red')
                else:
                    self.displays[name].config(text=f"{value:.1f}", foreground='black')
                    self.status_labels[name].config(text="CONNECTED", foreground='green')

    def set_error(self, sensor_name, message="ERR"):
        """
        Set a sensor display to show an error state.

        Args:
            sensor_name: Name of the sensor
            message: Error message to display
        """
        if sensor_name in self.displays:
            self.displays[sensor_name].config(text=message, foreground='red')
            self.status_labels[sensor_name].config(text="ERROR", foreground='red')

    def clear_all(self):
        """Reset all displays to default state."""
        for name in self.displays:
            self.displays[name].config(text="--.-", foreground='black')
            self.status_labels[name].config(text="WAITING", foreground='gray')

    def highlight(self, sensor_name, color='green'):
        """
        Highlight a sensor display (e.g., for alarms).

        Args:
            sensor_name: Name of the sensor to highlight
            color: Color to use for highlighting
        """
        if sensor_name in self.displays:
            self.displays[sensor_name].config(foreground=color)

    def get_sensor_names(self):
        """Get list of sensor names in the panel."""
        return list(self.displays.keys())
