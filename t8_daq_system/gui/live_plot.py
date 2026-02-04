"""
live_plot.py
PURPOSE: Display real-time updating graphs of sensor data
KEY CONCEPT: Use matplotlib's FigureCanvasTkAgg to embed plots in tkinter

Supports dual Y-axis plotting:
- Left Y-axis: Temperature and Pressure sensors
- Right Y-axis: Power supply voltage and current
"""

import tkinter as tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
from datetime import datetime


class LivePlot:
    def __init__(self, parent_frame, data_buffer):
        """
        Initialize the live plot.

        Args:
            parent_frame: tkinter frame to put the plot in
            data_buffer: DataBuffer object to get data from
        """
        self.data_buffer = data_buffer
        self.parent = parent_frame

        # Create matplotlib figure
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)

        # Create secondary axis for power supply data
        self.ax2 = None  # Created on demand

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Store line objects for each sensor (for efficient updating)
        self.lines = {}

        # Configure the plot appearance
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Temperature (C) / Pressure')
        self.ax.grid(True, alpha=0.3)

        # Format x-axis to show time nicely
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))

        # Color cycle for different sensors
        # Primary sensors (left axis) - blues and greens
        self.primary_colors = ['#1f77b4', '#2ca02c', '#17becf', '#7f7f7f',
                               '#9467bd', '#8c564b', '#e377c2']

        # Power supply colors (right axis) - reds and oranges
        self.ps_colors = {
            'PS_Voltage': '#d62728',   # Red for voltage
            'PS_Current': '#ff7f0e'    # Orange for current
        }

        # Track if we're currently showing PS data
        self._showing_ps = False

    def update(self, sensor_names, ps_names=None, window_seconds=None):
        """
        Refresh the plot with current data.
        Call this periodically (e.g., every 500ms).

        Args:
            sensor_names: List of sensor names to plot (TC and pressure)
            ps_names: Optional list of power supply sensor names
            window_seconds: If provided, only show data from the last X seconds
        """
        self.ax.clear()
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel('Time')

        # Check what types of data we have
        has_tc = any(name.startswith('TC_') for name in sensor_names)
        has_p = any(name.startswith('P_') for name in sensor_names)
        has_ps = bool(ps_names)

        # Configure Left Axis (Temperature)
        if has_tc:
            self.ax.set_ylabel('Temperature (C)', color='#1f77b4')
            self.ax.tick_params(axis='y', labelcolor='#1f77b4', labelleft=True)
            self.ax.yaxis.set_visible(True)
        elif has_p or has_ps:
            # If no TC but we have P/PS, hide the left axis labels/ticks
            self.ax.set_ylabel('')
            self.ax.tick_params(axis='y', labelleft=False)
            self.ax.yaxis.set_visible(True)
        else:
            # Default state (e.g. at startup)
            self.ax.set_ylabel('Temperature (C)', color='#1f77b4')
            self.ax.tick_params(axis='y', labelcolor='#1f77b4', labelleft=True)
            self.ax.yaxis.set_visible(True)

        # Configure Right Axis (Pressure / PS)
        if has_p or has_ps:
            if self.ax2 is None:
                self.ax2 = self.ax.twinx()
            self.ax2.clear()
            self.ax2.yaxis.set_visible(True)
            label = []
            if has_p: label.append('Pressure')
            if has_ps: label.append('Power Supply')
            self.ax2.set_ylabel(' / '.join(label), color='#2ca02c')
            self.ax2.tick_params(axis='y', labelcolor='#2ca02c')
        elif self.ax2 is not None:
            self.ax2.yaxis.set_visible(False)

        self._showing_ps = has_ps

        # Plot sensors
        legend_handles = []
        legend_labels = []

        now = datetime.now() if window_seconds else None

        for i, name in enumerate(sensor_names):
            timestamps, values = self.data_buffer.get_sensor_data(name)
            if not timestamps or not values:
                continue

            # Filter data
            valid_data = []
            for t, v in zip(timestamps, values):
                if v is None:
                    continue
                if window_seconds and (now - t).total_seconds() > window_seconds:
                    continue
                valid_data.append((t, v))

            if valid_data:
                times, vals = zip(*valid_data)
                color = self.primary_colors[i % len(self.primary_colors)]

                # Determine which axis to use
                if name.startswith('P_'):
                    # Pressure on right axis
                    line, = self.ax2.plot(times, vals, label=name, linewidth=2, color=color, linestyle='--')
                else:
                    # Temperature on left axis
                    line, = self.ax.plot(times, vals, label=name, linewidth=2, color=color)

                legend_handles.append(line)
                legend_labels.append(name)

        # Plot power supply data on right axis
        if ps_names:
            for name in ps_names:
                timestamps, values = self.data_buffer.get_sensor_data(name)
                if not timestamps or not values:
                    continue

                valid_data = []
                for t, v in zip(timestamps, values):
                    if v is None:
                        continue
                    if window_seconds and (now - t).total_seconds() > window_seconds:
                        continue
                    valid_data.append((t, v))

                if valid_data:
                    times, vals = zip(*valid_data)
                    color = self.ps_colors.get(name, '#d62728')

                    if name == 'PS_Voltage':
                        label = 'Voltage (V)'
                        linestyle = ':'
                    elif name == 'PS_Current':
                        label = 'Current (A)'
                        linestyle = '-.'
                    else:
                        label = name
                        linestyle = '-'

                    line, = self.ax2.plot(times, vals, label=label,
                                         linewidth=2, color=color,
                                         linestyle=linestyle)
                    legend_handles.append(line)
                    legend_labels.append(label)

        # Combined legend
        if legend_handles:
            self.ax.legend(legend_handles, legend_labels, loc='upper left', fontsize=8)

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.fig.autofmt_xdate()  # Angle the time labels

        # Ensure proper layout
        self.fig.tight_layout()

        self.canvas.draw()

    def clear(self):
        """Clear the plot."""
        self.ax.clear()
        self.ax.grid(True, alpha=0.3)
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Temperature (C) / Pressure')

        if self.ax2 is not None:
            self.ax2.clear()

        self.canvas.draw()

    def set_y_label(self, label):
        """Set the y-axis label."""
        self.ax.set_ylabel(label)
        self.canvas.draw()

    def set_title(self, title):
        """Set the plot title."""
        self.ax.set_title(title)
        self.canvas.draw()

    def set_y_limits(self, ymin=None, ymax=None, axis='primary'):
        """
        Set Y-axis limits.

        Args:
            ymin: Minimum Y value (None for auto)
            ymax: Maximum Y value (None for auto)
            axis: 'primary' for left axis, 'secondary' for right axis
        """
        target_ax = self.ax if axis == 'primary' else self.ax2
        if target_ax is None:
            return

        if ymin is not None and ymax is not None:
            target_ax.set_ylim(ymin, ymax)
        elif ymin is not None:
            target_ax.set_ylim(bottom=ymin)
        elif ymax is not None:
            target_ax.set_ylim(top=ymax)
        else:
            target_ax.set_ylim(auto=True)

        self.canvas.draw()

    def enable_secondary_axis(self, enable=True):
        """
        Enable or disable the secondary Y-axis.

        Args:
            enable: Whether to enable the secondary axis
        """
        if enable:
            if self.ax2 is None:
                self.ax2 = self.ax.twinx()
                self.ax2.set_ylabel('Voltage (V) / Current (A)', color='#d62728')
                self.ax2.tick_params(axis='y', labelcolor='#d62728')
        else:
            if self.ax2 is not None:
                self.ax2.set_visible(False)
                self.ax2 = None

        self.canvas.draw()

    def get_figure(self):
        """Get the matplotlib Figure object for advanced customization."""
        return self.fig

    def get_axes(self):
        """Get the matplotlib Axes objects."""
        return self.ax, self.ax2

    def save_figure(self, filepath, dpi=150):
        """
        Save the current plot to a file.

        Args:
            filepath: Path to save the figure to
            dpi: Resolution in dots per inch
        """
        self.fig.savefig(filepath, dpi=dpi, bbox_inches='tight')
