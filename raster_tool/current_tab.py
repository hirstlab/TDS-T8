"""
current_tab.py
Beam Current tab. QWidget subclass — constructor takes (config: SlitConfig, parent=None).
QTimer at POLL_INTERVAL_MS drives display refresh from the latest cached monitor reading.
The timer never writes; CurrentMonitor runs its own background thread for hardware I/O.
close() stops the timer and the monitor thread.
"""
import sys
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QApplication,
)
from PyQt5.QtCore import QTimer

from current_monitor import CurrentMonitor
from slit_config import SlitConfig


POLL_INTERVAL_MS = 250   # display refresh rate; CurrentMonitor polls hardware independently


class CurrentTab(QWidget):
    def __init__(self, config: SlitConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._monitor = CurrentMonitor()

        self._build_ui()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

    def _build_ui(self):
        root = QVBoxLayout(self)

        ctrl_box = QGroupBox("Beam Current Monitor")
        ctrl_layout = QHBoxLayout(ctrl_box)
        self._reading_label = QLabel("-- µA")
        self._reading_label.setStyleSheet("font-size: 18pt; font-weight: bold;")
        start_btn = QPushButton("Start Monitor")
        start_btn.clicked.connect(self._monitor.start)
        stop_btn = QPushButton("Stop Monitor")
        stop_btn.clicked.connect(self._monitor.stop)
        ctrl_layout.addWidget(self._reading_label)
        ctrl_layout.addWidget(start_btn)
        ctrl_layout.addWidget(stop_btn)
        root.addWidget(ctrl_box)
        root.addStretch()

    def _refresh(self):
        val = self._monitor.latest_ua
        if val is None:
            self._reading_label.setText("-- µA")
        else:
            self._reading_label.setText(f"{val:.3f} µA")

    def close(self):
        self._poll_timer.stop()
        self._monitor.stop()
        super().close()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    tab = CurrentTab(SlitConfig())
    print("[OK] current_tab: CurrentTab constructed")
    sys.exit(0)
