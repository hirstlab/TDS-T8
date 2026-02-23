"""
pinout_display.py
PURPOSE: Live pinout display showing current hardware configuration and pin
         assignments, updated in real-time with live sensor readings.

Allows users to verify that the physical wiring matches what the software
expects, and to confirm that unit conversions are working correctly by showing
both the raw thermocouple voltage and the resulting temperature side-by-side.
"""

import tkinter as tk
from tkinter import ttk


# Human-readable thermocouple type descriptions
_TC_TYPE_DESC = {
    'B': 'Type B  Pt-Rh  (0 – 1820 °C)',
    'C': 'Type C  W-Re   (0 – 2315 °C)',
    'E': 'Type E  Chr-Con (-270 – 1000 °C)',
    'J': 'Type J  Fe-Con  (-210 – 1200 °C)',
    'K': 'Type K  Chr-Alu (-270 – 1372 °C)',
    'N': 'Type N  Nic-Nis (-270 – 1300 °C)',
    'R': 'Type R  Pt-Rh   (-50 – 1768 °C)',
    'S': 'Type S  Pt-Rh   (-50 – 1768 °C)',
    'T': 'Type T  Cu-Con  (-270 – 400 °C)',
}

_MONO = ('Courier', 9)
_BOLD = ('Arial', 9, 'bold')
_HDR  = ('Arial', 10, 'bold')


def _dot(parent, color='#333333'):
    """Return a small square Canvas widget used as a status indicator."""
    c = tk.Canvas(parent, width=14, height=14, bg=color,
                  highlightthickness=1, highlightbackground='black')
    return c


class PinoutDisplay(tk.Toplevel):
    """
    Live pinout display Toplevel window.

    Shows the current hardware assignment for every LabJack T8 analog input,
    every digital I/O line, the XGS-600 serial connection, and the Keysight
    power-supply VISA resource.

    For each thermocouple channel the display shows:
      • The physical AIN pin / differential pair
      • The thermocouple type and units
      • The latest converted temperature
      • The latest raw millivolt input voltage (from AIN# register, before EF)
      • The latest differential voltage (same value, labelled for clarity)

    Call ``update_readings(all_readings, raw_voltages)`` whenever new data
    arrives from the acquisition thread to refresh the live values.
    Call ``refresh_config(config, app_settings)`` after a settings change to
    rebuild the table.

    Parameters
    ----------
    parent : tk.Widget
    config : dict          current internal config dict
    app_settings : AppSettings
    """

    REFRESH_MS = 200  # How often to redraw live value cells (ms)

    def __init__(self, parent, config, app_settings):
        super().__init__(parent)
        self.title("Live Pinout Display")
        self.geometry("780x650")
        self.minsize(660, 500)
        self.resizable(True, True)
        self.transient(parent)

        self._config   = config
        self._settings = app_settings

        # Latest readings supplied by main_window
        self._all_readings   = {}   # {sensor_name: value}
        self._raw_voltages   = {}   # {tc_name + '_rawV': volts}

        # Widget references updated per rebuild (name -> dict of labels/dots)
        self._tc_rows   = {}   # tc_name -> {'dot': Canvas, 'temp': Label, 'raw': Label}
        self._frg_rows  = {}   # frg_name -> {'dot': Canvas, 'val': Label}

        self._build_chrome()
        self._build_content()
        self._schedule_refresh()

        # Centre over parent
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h   = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def update_readings(self, all_readings: dict, raw_voltages: dict | None = None):
        """
        Store the latest sensor readings so the periodic refresh can display them.

        Parameters
        ----------
        all_readings  : dict  {sensor_name: value}  (temp in °C, pressure in
                              configured unit, PS values)
        raw_voltages  : dict  {tc_name + '_rawV': volts}  optional raw TC
                              voltages read directly from AIN# registers before
                              the T8's extended-feature conversion.
        """
        self._all_readings = all_readings or {}
        if raw_voltages is not None:
            self._raw_voltages = raw_voltages

    def refresh_config(self, config: dict, app_settings):
        """Rebuild the display after a config/settings change."""
        self._config   = config
        self._settings = app_settings
        for widget in self._content_frame.winfo_children():
            widget.destroy()
        self._tc_rows  = {}
        self._frg_rows = {}
        self._build_content()

    # ──────────────────────────────────────────────────────────────────────────
    # Build helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build_chrome(self):
        """Build the fixed outer frame (title bar, legend, scrollable area, close btn)."""
        hdr = ttk.Frame(self)
        hdr.pack(fill=tk.X, padx=10, pady=(8, 4))

        ttk.Label(hdr, text="LabJack T8  —  Live Pinout & Signal Verification",
                  font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        ttk.Label(hdr,
                  text="● = live data   ○ = no / stale data",
                  font=('Arial', 8), foreground='#555555').pack(side=tk.RIGHT)

        ttk.Separator(self, orient='horizontal').pack(fill=tk.X, padx=8, pady=2)

        # Scrollable canvas
        outer = ttk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        canvas    = tk.Canvas(outer, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._content_frame = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=self._content_frame, anchor='nw')

        def _on_content_resize(event):
            canvas.configure(scrollregion=canvas.bbox('all'))

        def _on_canvas_resize(event):
            canvas.itemconfig(win_id, width=event.width)

        self._content_frame.bind('<Configure>', _on_content_resize)
        canvas.bind('<Configure>', _on_canvas_resize)

        # Mouse-wheel scrolling
        def _scroll(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind_all('<MouseWheel>', _scroll)

        # Close button
        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, padx=8, pady=(2, 8))
        ttk.Button(btn_row, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _section(self, text):
        """Add a bold section header to the content frame."""
        ttk.Label(self._content_frame, text=text, font=_HDR).pack(
            anchor='w', padx=6, pady=(10, 2))

    def _separator(self):
        ttk.Separator(self._content_frame, orient='horizontal').pack(
            fill=tk.X, padx=6, pady=4)

    # ──────────────────────────────────────────────────────────────────────────
    # Content sections
    # ──────────────────────────────────────────────────────────────────────────

    def _build_content(self):
        self._build_tc_section()
        self._separator()
        self._build_dio_section()
        self._separator()
        self._build_xgs_section()
        self._separator()
        self._build_ps_section()

    # ── Thermocouples ─────────────────────────────────────────────────────────

    def _build_tc_section(self):
        self._section("LabJack T8  —  Analog Inputs (Thermocouples)")

        f = ttk.Frame(self._content_frame)
        f.pack(fill=tk.X, padx=12, pady=2)

        # Column header row
        col_defs = [
            # (header_text, width_chars, anchor)
            ('',         2,  'w'),   # dot placeholder
            ('T8 Pin',   9,  'w'),
            ('Pair',     5,  'w'),
            ('Sensor',   12, 'w'),
            ('Type',     30, 'w'),
            ('Unit',     6,  'w'),
            ('Live Temp',     11, 'e'),
            ('Raw Voltage (V)', 17, 'e'),
            ('Diff Voltage (V)', 17, 'e'),
        ]
        hdr_row = ttk.Frame(f)
        hdr_row.pack(fill=tk.X)
        for txt, w, anchor in col_defs:
            ttk.Label(hdr_row, text=txt, font=_BOLD,
                      width=w, anchor=anchor).pack(side=tk.LEFT, padx=2)

        ttk.Separator(f, orient='horizontal').pack(fill=tk.X, pady=2)

        # Assigned channels
        thermocouples = self._config.get('thermocouples', [])
        assigned = set()

        for tc in thermocouples:
            if not tc.get('enabled', True):
                continue
            ch   = tc['channel']
            name = tc['name']
            assigned.add(ch)
            tc_type = tc.get('type', 'K')
            units   = tc.get('units', 'C')
            type_desc = _TC_TYPE_DESC.get(tc_type, f'Type {tc_type}')

            row = ttk.Frame(f)
            row.pack(fill=tk.X, pady=1)

            dot = _dot(row)
            dot.pack(side=tk.LEFT, padx=(2, 4))

            pin_str  = f"AIN{ch}"
            pair_str = f"+/GND"

            for val, w, anchor in [
                (pin_str,    9,  'w'),
                (pair_str,   5,  'w'),
                (name,       12, 'w'),
                (type_desc,  30, 'w'),
                (units,      6,  'w'),
            ]:
                ttk.Label(row, text=val, width=w, anchor=anchor,
                          font=_MONO).pack(side=tk.LEFT, padx=2)

            temp_lbl = ttk.Label(row, text="—", width=11, anchor='e',
                                 font=_MONO, foreground='#1a5f7a')
            temp_lbl.pack(side=tk.LEFT, padx=2)

            raw_lbl  = ttk.Label(row, text="—", width=17, anchor='e',
                                 font=_MONO, foreground='#5a3e7a')
            raw_lbl.pack(side=tk.LEFT, padx=2)

            diff_lbl = ttk.Label(row, text="—", width=17, anchor='e',
                                 font=_MONO, foreground='#5a3e7a')
            diff_lbl.pack(side=tk.LEFT, padx=2)

            self._tc_rows[name] = {
                'dot':  dot,
                'temp': temp_lbl,
                'raw':  raw_lbl,
                'diff': diff_lbl,
            }

        # Unassigned AIN channels
        unassigned = [i for i in range(8) if i not in assigned]
        if unassigned:
            ttk.Separator(f, orient='horizontal').pack(fill=tk.X, pady=3)
            for ch in unassigned:
                row = ttk.Frame(f)
                row.pack(fill=tk.X, pady=1)
                _dot(row).pack(side=tk.LEFT, padx=(2, 4))
                for val, w, anchor in [
                    (f"AIN{ch}",       9,  'w'),
                    ("",               5,  'w'),
                    ("(unassigned)",   12, 'w'),
                    ("",               30, 'w'),
                    ("",               6,  'w'),
                    ("",               11, 'e'),
                    ("",               17, 'e'),
                    ("",               17, 'e'),
                ]:
                    ttk.Label(row, text=val, width=w, anchor=anchor,
                              font=_MONO, foreground='#999999').pack(
                        side=tk.LEFT, padx=2)

        if not thermocouples:
            ttk.Label(f, text="  No thermocouples configured.",
                      foreground='gray').pack(anchor='w', pady=4)

    # ── Digital I/O ───────────────────────────────────────────────────────────

    def _build_dio_section(self):
        self._section("LabJack T8  —  Digital I/O (Turbo Pump)")

        s      = self._settings
        turbo  = self._config.get('turbo_pump', {})
        start_ch  = turbo.get('start_stop_channel', 'DIO0')
        status_ch = turbo.get('status_channel',     'DIO1')
        enabled   = getattr(s, 'turbo_pump_enabled', True)

        f = ttk.Frame(self._content_frame)
        f.pack(fill=tk.X, padx=12, pady=2)

        hdr_row = ttk.Frame(f)
        hdr_row.pack(fill=tk.X)
        for txt, w in [('T8 Pin', 10), ('Direction', 12), ('Function', 38), ('Enabled', 8)]:
            ttk.Label(hdr_row, text=txt, font=_BOLD,
                      width=w, anchor='w').pack(side=tk.LEFT, padx=2)
        ttk.Separator(f, orient='horizontal').pack(fill=tk.X, pady=2)

        fg = 'black' if enabled else '#888888'
        for pin, direction, func in [
            (start_ch,  'Output', 'Turbo Pump Start/Stop  (active HIGH = start)'),
            (status_ch, 'Input',  'Turbo Pump Status  (HIGH = running)'),
        ]:
            row = ttk.Frame(f)
            row.pack(fill=tk.X, pady=1)
            for val, w in [(pin, 10), (direction, 12), (func, 38),
                           ('Yes' if enabled else 'No', 8)]:
                ttk.Label(row, text=val, width=w, anchor='w',
                          font=_MONO, foreground=fg).pack(side=tk.LEFT, padx=2)

        del_row = ttk.Frame(f)
        del_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(del_row,
                  text=f"  Start delay: {getattr(s,'turbo_pump_start_delay_ms',500)} ms   "
                       f"Stop delay: {getattr(s,'turbo_pump_stop_delay_ms',500)} ms   "
                       f"Min restart: {getattr(s,'turbo_pump_min_restart_delay_s',30)} s",
                  font=('Arial', 8), foreground='#555555').pack(anchor='w')

    # ── XGS-600 / FRG-702 ────────────────────────────────────────────────────

    def _build_xgs_section(self):
        self._section("XGS-600 Controller  —  RS-232  (FRG-702 Gauges)")

        s = self._settings
        f = ttk.Frame(self._content_frame)
        f.pack(fill=tk.X, padx=12, pady=2)

        # Serial port info box
        info = ttk.LabelFrame(f, text="Serial Port Config", padding=6)
        info.pack(fill=tk.X, pady=(0, 6))
        for label, value in [
            ("COM Port:",  s.xgs600_port),
            ("Baud Rate:", str(s.xgs600_baudrate)),
            ("Timeout:",   f"{s.xgs600_timeout} s"),
            ("Address:",   s.xgs600_address),
        ]:
            r = ttk.Frame(info)
            r.pack(fill=tk.X, pady=1)
            ttk.Label(r, text=label, width=14, anchor='w',
                      font=_BOLD).pack(side=tk.LEFT, padx=2)
            ttk.Label(r, text=value,  anchor='w',
                      font=_MONO).pack(side=tk.LEFT)

        gauges = self._config.get('frg702_gauges', [])
        if not gauges:
            ttk.Label(f, text="  No FRG-702 gauges configured.",
                      foreground='gray').pack(anchor='w', pady=4)
            return

        # Gauge assignment table
        hdr_row = ttk.Frame(f)
        hdr_row.pack(fill=tk.X)
        for txt, w in [('', 2), ('XGS-600 Code', 14), ('Name', 18),
                       ('Units', 8), ('Live Pressure', 18)]:
            ttk.Label(hdr_row, text=txt, font=_BOLD,
                      width=w, anchor='w').pack(side=tk.LEFT, padx=2)
        ttk.Separator(f, orient='horizontal').pack(fill=tk.X, pady=2)

        for gauge in gauges:
            if not gauge.get('enabled', True):
                continue
            name = gauge['name']
            row  = ttk.Frame(f)
            row.pack(fill=tk.X, pady=1)
            dot  = _dot(row)
            dot.pack(side=tk.LEFT, padx=(2, 4))
            for val, w in [(gauge['sensor_code'], 14), (name, 18),
                           (gauge.get('units', 'mbar'), 8)]:
                ttk.Label(row, text=val, width=w, anchor='w',
                          font=_MONO).pack(side=tk.LEFT, padx=2)
            val_lbl = ttk.Label(row, text="—", width=18, anchor='w',
                                font=_MONO, foreground='#1a5f7a')
            val_lbl.pack(side=tk.LEFT, padx=2)
            self._frg_rows[name] = {'dot': dot, 'val': val_lbl}

    # ── Power Supply ──────────────────────────────────────────────────────────

    def _build_ps_section(self):
        self._section("Keysight N5761A  —  VISA / Ethernet")

        s    = self._settings
        cfg  = self._config.get('power_supply', {})
        visa = (s.visa_resource or '').strip() or cfg.get('visa_resource') or 'Not configured'

        f = ttk.Frame(self._content_frame)
        f.pack(fill=tk.X, padx=12, pady=2)

        info = ttk.LabelFrame(f, text="Connection & Safety Limits", padding=6)
        info.pack(fill=tk.X, pady=2)

        for label, value in [
            ("VISA Resource:",  visa),
            ("Voltage Limit:",  f"{s.ps_voltage_limit} V"),
            ("Current Limit:",  f"{s.ps_current_limit} A"),
            ("V Range (plot):", f"{s.ps_v_range_min} – {s.ps_v_range_max} V"),
            ("I Range (plot):", f"{s.ps_i_range_min} – {s.ps_i_range_max} A"),
        ]:
            r = ttk.Frame(info)
            r.pack(fill=tk.X, pady=1)
            ttk.Label(r, text=label, width=18, anchor='w',
                      font=_BOLD).pack(side=tk.LEFT, padx=2)
            ttk.Label(r, text=str(value), anchor='w',
                      font=_MONO).pack(side=tk.LEFT)

    # ──────────────────────────────────────────────────────────────────────────
    # Live-refresh loop
    # ──────────────────────────────────────────────────────────────────────────

    def _schedule_refresh(self):
        try:
            self.after(self.REFRESH_MS, self._do_refresh)
        except tk.TclError:
            pass  # Window was destroyed

    def _do_refresh(self):
        """Update live value labels and status dots from stored readings."""
        # Thermocouple rows
        for name, widgets in self._tc_rows.items():
            temp_val = self._all_readings.get(name)
            raw_val  = self._raw_voltages.get(f"{name}_rawV")

            # Status dot
            dot_color = '#00CC00' if temp_val is not None else '#333333'
            try:
                widgets['dot'].config(bg=dot_color)
            except tk.TclError:
                continue

            # Temperature
            if temp_val is not None:
                # Find TC unit from config
                unit = 'C'
                for tc in self._config.get('thermocouples', []):
                    if tc['name'] == name:
                        unit = tc.get('units', 'C')
                        break
                widgets['temp'].config(
                    text=f"{temp_val:>9.2f} °{unit}",
                    foreground='#1a5f7a'
                )
            else:
                widgets['temp'].config(text="—", foreground='#888888')

            # Raw / differential voltage
            if raw_val is not None:
                # Display in millivolts (TC signals are millivolt-range)
                mv = raw_val * 1000.0
                volt_str = f"{raw_val:>+10.6f} V  ({mv:>+8.3f} mV)"
                widgets['raw'].config(text=volt_str,  foreground='#5a3e7a')
                widgets['diff'].config(text=volt_str, foreground='#5a3e7a')
            else:
                widgets['raw'].config(text="—  (no raw read)", foreground='#888888')
                widgets['diff'].config(text="—  (no raw read)", foreground='#888888')

        # FRG-702 rows
        for name, widgets in self._frg_rows.items():
            val = self._all_readings.get(name)
            dot_color = '#00CC00' if val is not None else '#333333'
            try:
                widgets['dot'].config(bg=dot_color)
            except tk.TclError:
                continue

            if val is not None:
                widgets['val'].config(
                    text=f"{val:.3e}",
                    foreground='#1a5f7a'
                )
            else:
                widgets['val'].config(text="—", foreground='#888888')

        self._schedule_refresh()
