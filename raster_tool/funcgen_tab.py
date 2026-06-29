"""
funcgen_tab.py
Function Generators tab for raster_tool.
Controls two RIGOL DG1022Z generators (4 channels total) via USB-TMC/VISA.

Tab is a QWidget subclass — mirrors motor_tab.py / current_tab.py conventions:
  * constructor takes (config: SlitConfig, parent=None)
  * QTimer at POLL_INTERVAL_MS drives read-only get_state() polling; never writes
  * close() calls driver.close() only — never resets or disables outputs

Safety: all voltage spinboxes enforce MAX_GEN_VOLTS as their maximum so the UI
cannot express a value above the hardware safety ceiling. All channels default
to 0 V and output OFF.
"""

import sys
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QGroupBox, QDoubleSpinBox, QComboBox, QLineEdit, QTextEdit,
    QFrame, QFormLayout, QApplication, QMessageBox,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from funcgen_driver import DG1022Z, discover, MAX_GEN_VOLTS
from slit_config import SlitConfig


POLL_INTERVAL_MS = 2000   # read-only VISA poll (4 channels × ~50 ms round-trip)

SHAPES = ["Sine", "Triangle", "Square", "Pulse", "DC"]


class _ChannelPanel(QGroupBox):
    """
    Control panel for a single generator channel.
    Instantiated by FuncgenTab; driver/channel assigned via set_driver().
    """

    def __init__(self, channel_label: str, parent=None):
        super().__init__(channel_label, parent)
        self._driver = None
        self._channel = 1
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._shape_combo = QComboBox()
        self._shape_combo.addItems(SHAPES)
        self._shape_combo.currentTextChanged.connect(self._on_shape_change)
        form.addRow("Shape:", self._shape_combo)

        self._freq_spin = QDoubleSpinBox()
        self._freq_spin.setRange(1e-3, 25e6)
        self._freq_spin.setDecimals(3)
        self._freq_spin.setSuffix(" Hz")
        self._freq_spin.setValue(1000.0)
        self._freq_label = QLabel("Frequency:")
        form.addRow(self._freq_label, self._freq_spin)

        # Amplitude: max = MAX_GEN_VOLTS; default 0 V
        self._amp_spin = QDoubleSpinBox()
        self._amp_spin.setRange(0.0, MAX_GEN_VOLTS)
        self._amp_spin.setDecimals(4)
        self._amp_spin.setSuffix(" Vpp")
        self._amp_spin.setValue(0.0)
        self._amp_label = QLabel("Amplitude:")
        form.addRow(self._amp_label, self._amp_spin)

        # Offset: ±MAX_GEN_VOLTS; default 0 V
        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-MAX_GEN_VOLTS, MAX_GEN_VOLTS)
        self._offset_spin.setDecimals(4)
        self._offset_spin.setSuffix(" V")
        self._offset_spin.setValue(0.0)
        self._offset_label = QLabel("Offset:")
        form.addRow(self._offset_label, self._offset_spin)

        self._phase_spin = QDoubleSpinBox()
        self._phase_spin.setRange(-360.0, 360.0)
        self._phase_spin.setDecimals(2)
        self._phase_spin.setSuffix(" °")
        self._phase_spin.setValue(0.0)
        form.addRow("Phase:", self._phase_spin)

        # Output load — EEL5000 input is high-Z; always default to INFinity
        self._load_edit = QLineEdit("INFinity")
        self._load_edit.setMaximumWidth(110)
        form.addRow("Output load:", self._load_edit)

        layout.addLayout(form)

        # ── HV consequence label ─────────────────────────────────────────────
        # EEL5000 gain = 1000x: 1 V generator → 1 kV/plate.
        # Plate-to-plate = 2× per-plate (ES5 single-ended, ±plate arrangement).
        self._hv_label = QLabel("→ 0.000 kV/plate (0.000 kV plate-to-plate)")
        self._hv_label.setStyleSheet("color: #8B0000; font-weight: bold;")
        layout.addWidget(self._hv_label)

        self._amp_spin.valueChanged.connect(self._update_hv_label)
        self._offset_spin.valueChanged.connect(self._update_hv_label)
        self._shape_combo.currentTextChanged.connect(self._update_hv_label)

        # ── Output toggle + Apply ────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._output_btn = QPushButton("Output OFF")
        self._output_btn.setCheckable(True)
        self._output_btn.setChecked(False)   # default OFF
        self._output_btn.clicked.connect(self._on_output_toggle)
        self._output_btn.setStyleSheet(
            "QPushButton:checked { background-color: #228B22; color: white; font-weight: bold; }"
        )
        btn_row.addWidget(self._output_btn)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.clicked.connect(self.apply)
        btn_row.addWidget(self._apply_btn)

        layout.addLayout(btn_row)

        # ── Read-back display ────────────────────────────────────────────────
        self._readback_label = QLabel("Readback: (not connected)")
        self._readback_label.setWordWrap(True)
        self._readback_label.setStyleSheet("color: gray; font-size: 8pt;")
        layout.addWidget(self._readback_label)

        # ── Clamp / error warning ────────────────────────────────────────────
        self._warn_label = QLabel("")
        self._warn_label.setWordWrap(True)
        self._warn_label.setStyleSheet("color: #B8860B; font-style: italic; font-size: 8pt;")
        layout.addWidget(self._warn_label)

    # ── Slot handlers ────────────────────────────────────────────────────────

    def _on_shape_change(self, shape: str):
        is_dc = (shape == "DC")
        self._freq_spin.setEnabled(not is_dc)
        self._amp_spin.setEnabled(not is_dc)
        self._freq_label.setEnabled(not is_dc)
        self._amp_label.setEnabled(not is_dc)
        if is_dc:
            self._offset_label.setText("Hold voltage:")
            self._offset_spin.setSuffix(" V (hold)")
        else:
            self._offset_label.setText("Offset:")
            self._offset_spin.setSuffix(" V")
        self._update_hv_label()

    def _update_hv_label(self):
        """
        Live HV consequence: EEL5000 gain = 1000x → 1 V generator = 1 kV/plate.
        For AC shapes the amplitude (Vpp) field value is used directly.
        For DC the hold voltage (offset field) is used.
        Plate-to-plate = 2 × per-plate.
        """
        shape = self._shape_combo.currentText()
        if shape == "DC":
            volts = abs(self._offset_spin.value())
        else:
            volts = self._amp_spin.value()
        kv_per_plate = volts          # 1 V → 1 kV (gain 1000x, unit conversion ×1000/1000)
        kv_pp = 2.0 * kv_per_plate
        self._hv_label.setText(
            f"→ {kv_per_plate:.3f} kV/plate ({kv_pp:.3f} kV plate-to-plate)"
        )

    def _on_output_toggle(self, checked: bool):
        if checked:
            self._output_btn.setText("Output ON")
        else:
            self._output_btn.setText("Output OFF")
        if self._driver is None:
            self._warn_label.setText("Not connected — toggle stored, will apply on connect.")
            return
        try:
            if checked:
                self._driver.output_on(self._channel)
            else:
                self._driver.output_off(self._channel)
            self._warn_label.setText("")
        except Exception as exc:
            self._warn_label.setText(f"Output toggle error: {exc}")

    # ── Public interface used by FuncgenTab ──────────────────────────────────

    def apply(self):
        """Push current UI settings to hardware. Called by Apply button and Apply All."""
        if self._driver is None:
            self._warn_label.setText("Not connected.")
            return
        shape = self._shape_combo.currentText()
        freq = self._freq_spin.value()
        amp = self._amp_spin.value()
        offset = self._offset_spin.value()
        phase = self._phase_spin.value()
        load = self._load_edit.text().strip() or "INFinity"
        output_on = self._output_btn.isChecked()

        try:
            self._driver.set_output_load(self._channel, load)
            warning = self._driver.set_waveform(self._channel, shape, freq, amp, offset, phase)
            if output_on:
                self._driver.output_on(self._channel)
            else:
                self._driver.output_off(self._channel)
            self._warn_label.setText(f"Applied. {warning}".strip() if warning else "Applied.")
        except Exception as exc:
            self._warn_label.setText(f"Apply error: {exc}")

    def update_readback(self, state: dict):
        """Update read-back field from a get_state() result dict."""
        on_str = "ON" if state.get("output_on") else "OFF"
        self._readback_label.setText(
            f"Shape={state.get('shape','?')}  "
            f"Freq={state.get('freq', 0):.3f} Hz  "
            f"Amp={state.get('amp', 0):.4f} Vpp  "
            f"Offset={state.get('offset', 0):.4f} V  "
            f"Phase={state.get('phase', 0):.2f}°  "
            f"Load={state.get('load','?')}  "
            f"Output={on_str}"
        )
        self._readback_label.setStyleSheet("color: black; font-size: 8pt;")

    def set_driver(self, driver, channel: int):
        """Assign hardware driver and channel number (called from FuncgenTab)."""
        self._driver = driver
        self._channel = channel
        if driver is None:
            self._readback_label.setText("Readback: (not connected)")
            self._readback_label.setStyleSheet("color: gray; font-size: 8pt;")


# ── Main tab widget ──────────────────────────────────────────────────────────

class FuncgenTab(QWidget):
    """
    Function Generators tab — two RIGOL DG1022Z generators, 4 channels total.
    Constructor: FuncgenTab(config: SlitConfig, parent=None)

    A/B serial assignment is persisted in SlitConfig under keys
    "funcgen_serial_a" and "funcgen_serial_b" so the assignment survives
    replug and reboot (keyed to serial, not USB port order).
    """

    def __init__(self, config: SlitConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._drivers = [None, None]     # index 0 = Gen A, index 1 = Gen B
        self._discovered = []            # list[dict] from discover()

        self._build_ui()

        # Read-only polling timer — never writes to hardware.
        # Tab-switching is safe because this timer only calls get_state().
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        # On startup, populate dropdowns from saved discovery and auto-select
        # saved serials if the instruments are already known.
        self._restore_saved_serials()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ── Discovery / connection bar ───────────────────────────────────────
        conn_box = QGroupBox("Generator Assignment && Connection")
        conn_layout = QHBoxLayout(conn_box)

        self._discover_btn = QPushButton("Refresh / Discover")
        self._discover_btn.clicked.connect(self._on_discover)
        conn_layout.addWidget(self._discover_btn)

        conn_layout.addWidget(QLabel("Gen A:"))
        self._gen_a_combo = QComboBox()
        self._gen_a_combo.setMinimumWidth(300)
        conn_layout.addWidget(self._gen_a_combo)

        conn_layout.addWidget(QLabel("Gen B:"))
        self._gen_b_combo = QComboBox()
        self._gen_b_combo.setMinimumWidth(300)
        conn_layout.addWidget(self._gen_b_combo)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        conn_layout.addWidget(self._connect_btn)

        self._conn_status_a = QLabel("Gen A: Disconnected")
        self._conn_status_b = QLabel("Gen B: Disconnected")
        conn_layout.addWidget(self._conn_status_a)
        conn_layout.addWidget(self._conn_status_b)

        root.addWidget(conn_box)

        # ── Four channel panels in a 2×2 grid ───────────────────────────────
        panels_box = QGroupBox("Channel Controls")
        panels_grid = QGridLayout(panels_box)

        self._panels = []
        label_positions = [
            ("Gen A  Ch 1", 0, 0),
            ("Gen A  Ch 2", 0, 1),
            ("Gen B  Ch 1", 1, 0),
            ("Gen B  Ch 2", 1, 1),
        ]
        for label, row, col in label_positions:
            panel = _ChannelPanel(label)
            self._panels.append(panel)
            panels_grid.addWidget(panel, row, col)

        root.addWidget(panels_box)

        # ── Apply All ────────────────────────────────────────────────────────
        apply_all_btn = QPushButton("Apply All Channels")
        apply_all_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        apply_all_btn.clicked.connect(self._on_apply_all)
        root.addWidget(apply_all_btn)

        # ── SCPI Console (collapsible) ───────────────────────────────────────
        self._console_visible = False

        self._console_toggle_btn = QPushButton("▶  SCPI Console")
        self._console_toggle_btn.clicked.connect(self._toggle_console)
        root.addWidget(self._console_toggle_btn)

        self._console_frame = QFrame()
        self._console_frame.setVisible(False)
        console_layout = QVBoxLayout(self._console_frame)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target generator:"))
        self._scpi_target_combo = QComboBox()
        self._scpi_target_combo.addItems(["Gen A", "Gen B"])
        target_row.addWidget(self._scpi_target_combo)
        target_row.addStretch()
        console_layout.addLayout(target_row)

        input_row = QHBoxLayout()
        self._scpi_input = QLineEdit()
        self._scpi_input.setPlaceholderText("Enter SCPI command or query…")
        self._scpi_input.returnPressed.connect(self._on_scpi_send)
        input_row.addWidget(self._scpi_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._on_scpi_send)
        input_row.addWidget(send_btn)

        query_btn = QPushButton("Query")
        query_btn.clicked.connect(self._on_scpi_query)
        input_row.addWidget(query_btn)

        errors_btn = QPushButton("Read Errors")
        errors_btn.clicked.connect(self._on_read_errors)
        input_row.addWidget(errors_btn)

        console_layout.addLayout(input_row)

        self._scpi_log = QTextEdit()
        self._scpi_log.setReadOnly(True)
        self._scpi_log.setMaximumHeight(160)
        self._scpi_log.setFont(QFont("Courier", 9))
        console_layout.addWidget(self._scpi_log)

        root.addWidget(self._console_frame)

    # ── Discovery / connection ───────────────────────────────────────────────

    def _on_discover(self):
        self._discovered = discover()
        items = ["(none)"] + [f"{d['idn']}  ({d['serial']})" for d in self._discovered]
        for combo in (self._gen_a_combo, self._gen_b_combo):
            combo.clear()
            combo.addItems(items)
        self._restore_saved_serials()

    def _restore_saved_serials(self):
        """Auto-select dropdowns from persisted serial assignments."""
        saved_a = self._config.get("funcgen_serial_a", "")
        saved_b = self._config.get("funcgen_serial_b", "")
        for combo, saved in ((self._gen_a_combo, saved_a), (self._gen_b_combo, saved_b)):
            if not saved:
                continue
            for i in range(combo.count()):
                if saved in combo.itemText(i):
                    combo.setCurrentIndex(i)
                    break

    def _resource_for_combo(self, combo: QComboBox):
        text = combo.currentText()
        if text == "(none)" or not text:
            return None
        for d in self._discovered:
            if d["serial"] in text or d["idn"] in text:
                return d["resource"]
        return None

    def _serial_for_resource(self, resource):
        if resource is None:
            return ""
        for d in self._discovered:
            if d["resource"] == resource:
                return d["serial"]
        return ""

    def _on_connect(self):
        self._close_drivers()

        resource_a = self._resource_for_combo(self._gen_a_combo)
        resource_b = self._resource_for_combo(self._gen_b_combo)

        # Persist serial assignments (keyed on serial, not port order)
        self._config.set("funcgen_serial_a", self._serial_for_resource(resource_a))
        self._config.set("funcgen_serial_b", self._serial_for_resource(resource_b))

        def _try_open(resource, label):
            if resource is None:
                return None, f"{label}: Not assigned"
            try:
                drv = DG1022Z(resource)
                return drv, f"{label}: Connected  {drv.idn()}"
            except Exception as exc:
                return None, f"{label}: Error — {exc}"

        drv_a, msg_a = _try_open(resource_a, "Gen A")
        drv_b, msg_b = _try_open(resource_b, "Gen B")

        self._drivers[0] = drv_a
        self._drivers[1] = drv_b
        self._conn_status_a.setText(msg_a)
        self._conn_status_b.setText(msg_b)

        # Wire panels to drivers
        # panels[0] = Gen A Ch1, panels[1] = Gen A Ch2
        # panels[2] = Gen B Ch1, panels[3] = Gen B Ch2
        self._panels[0].set_driver(drv_a, 1)
        self._panels[1].set_driver(drv_a, 2)
        self._panels[2].set_driver(drv_b, 1)
        self._panels[3].set_driver(drv_b, 2)

    def _close_drivers(self):
        for i, drv in enumerate(self._drivers):
            if drv is not None:
                try:
                    # Close VISA session only — never resets or disables outputs.
                    # Instrument retains state (frequency, amplitude, output on/off)
                    # after the session is closed.
                    drv.close()
                except Exception:
                    pass
                self._drivers[i] = None

    # ── Apply All ────────────────────────────────────────────────────────────

    def _on_apply_all(self):
        errors = []
        for panel in self._panels:
            try:
                panel.apply()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            QMessageBox.warning(self, "Apply All", "Errors on some channels:\n" + "\n".join(errors))

    # ── Read-only polling ────────────────────────────────────────────────────

    def _poll(self):
        """
        Read-only hardware poll. Never writes. Safe while user is on another tab.
        Called by QTimer every POLL_INTERVAL_MS ms.
        """
        mapping = [
            (self._panels[0], self._drivers[0], 1),
            (self._panels[1], self._drivers[0], 2),
            (self._panels[2], self._drivers[1], 1),
            (self._panels[3], self._drivers[1], 2),
        ]
        for panel, drv, ch in mapping:
            if drv is None:
                continue
            try:
                state = drv.get_state(ch)
                panel.update_readback(state)
            except Exception as exc:
                panel._readback_label.setText(f"Poll error: {exc}")

    # ── SCPI console ─────────────────────────────────────────────────────────

    def _toggle_console(self):
        self._console_visible = not self._console_visible
        self._console_frame.setVisible(self._console_visible)
        self._console_toggle_btn.setText(
            "▼  SCPI Console" if self._console_visible else "▶  SCPI Console"
        )

    def _target_driver(self):
        return self._drivers[self._scpi_target_combo.currentIndex()]

    def _log(self, text: str):
        self._scpi_log.append(text)

    def _on_scpi_send(self):
        cmd = self._scpi_input.text().strip()
        if not cmd:
            return
        drv = self._target_driver()
        if drv is None:
            self._log(f">> {cmd}\n   [Not connected]")
            return
        try:
            drv.write(cmd)
            self._log(f">> {cmd}\n   [sent]")
        except Exception as exc:
            self._log(f">> {cmd}\n   [ERROR: {exc}]")

    def _on_scpi_query(self):
        cmd = self._scpi_input.text().strip()
        if not cmd:
            return
        drv = self._target_driver()
        if drv is None:
            self._log(f"?? {cmd}\n   [Not connected]")
            return
        try:
            resp = drv.query(cmd)
            self._log(f"?? {cmd}\n   {resp}")
        except Exception as exc:
            self._log(f"?? {cmd}\n   [ERROR: {exc}]")

    def _on_read_errors(self):
        drv = self._target_driver()
        target = self._scpi_target_combo.currentText()
        if drv is None:
            self._log(f"[{target}] Not connected")
            return
        self._log(f"[{target}] Error queue:")
        for _ in range(20):   # guard: drain at most 20 entries
            try:
                err = drv.get_error()
                self._log(f"  {err}")
                if err.startswith("+0") or err.startswith("0,"):
                    break    # "+0,No error" means queue is empty
            except Exception as exc:
                self._log(f"  [read error: {exc}]")
                break

    # ── Teardown ─────────────────────────────────────────────────────────────

    def close(self):
        self._poll_timer.stop()
        # Close VISA sessions only — never resets or disables outputs.
        # Instrument holds its output state (frequency, waveform, output on/off)
        # after the VISA session is closed. This is intentional: the DG1022Z
        # only loses state on *RST, :SYSTem:PRESet, or a power cycle, none of
        # which we ever send.
        self._close_drivers()
        super().close()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    cfg = SlitConfig()
    tab = FuncgenTab(cfg)
    print("[OK] funcgen_tab: constructed")
    # Do not call app.exec_() — just verify construction succeeds
