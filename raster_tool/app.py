"""
app.py
raster_tool main application window.
Tab order: Analysis | Stepper Motors | Beam Current
"""
import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget,
    QWidget, QVBoxLayout, QLabel,
)

from slit_config import SlitConfig
from motor_tab import MotorTab
from current_tab import CurrentTab
from funcgen_tab import FuncgenTab


class RasterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("raster_tool")
        self.resize(1280, 860)

        self._config = SlitConfig()

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Analysis tab (placeholder — not yet implemented)
        _analysis = QWidget()
        QVBoxLayout(_analysis).addWidget(QLabel("Analysis — placeholder"))

        self._tabs.addTab(_analysis, "Analysis")
        self._tabs.addTab(MotorTab(self._config), "Stepper Motors")
        self._tabs.addTab(CurrentTab(self._config), "Beam Current")
        self._tabs.addTab(FuncgenTab(self._config), "Function Generators")

    def closeEvent(self, event):
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if hasattr(widget, "close") and callable(widget.close):
                widget.close()
        event.accept()


if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    window = RasterApp()
    window.show()
    sys.exit(app.exec_())
