"""
motor_tab.py
Stepper Motors tab. QWidget subclass — constructor takes (config: SlitConfig, parent=None).
QTimer drives read-only periodic state reads; it never writes during polling.
close() calls driver.disconnect() only.
"""
import sys
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QDoubleSpinBox, QFormLayout, QApplication,
)
from PyQt5.QtCore import QTimer

from galil_driver import GalilController
from slit_config import SlitConfig


POLL_INTERVAL_MS = 500


class MotorTab(QWidget):
    def __init__(self, config: SlitConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._driver = GalilController(
            address=config.get("galil_address", "192.168.1.12")
        )
        self._build_ui()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    def _build_ui(self):
        root = QVBoxLayout(self)

        conn_box = QGroupBox("Connection")
        conn_layout = QHBoxLayout(conn_box)
        self._status_label = QLabel("Disconnected")
        conn_btn = QPushButton("Connect")
        conn_btn.clicked.connect(self._connect)
        conn_layout.addWidget(self._status_label)
        conn_layout.addWidget(conn_btn)
        root.addWidget(conn_box)

        axes_box = QGroupBox("Axes")
        axes_form = QFormLayout(axes_box)
        self._pos_labels = {}
        for axis in ("X", "Y"):
            lbl = QLabel("--")
            self._pos_labels[axis] = lbl
            axes_form.addRow(f"{axis} position:", lbl)
        root.addWidget(axes_box)
        root.addStretch()

    def _connect(self):
        if self._driver.connect():
            self._status_label.setText("Connected")
        else:
            self._status_label.setText("Connection failed")

    def _poll(self):
        if not self._driver.is_connected():
            return
        for axis, lbl in self._pos_labels.items():
            pos = self._driver.get_position(axis)
            lbl.setText(f"{pos:.3f}")

    def close(self):
        self._poll_timer.stop()
        self._driver.disconnect()
        super().close()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    cfg = SlitConfig()
    tab = MotorTab(cfg)
    print("[OK] motor_tab: MotorTab constructed")
    sys.exit(0)
