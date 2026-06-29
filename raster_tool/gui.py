"""
gui.py
Shared GUI helpers for raster_tool. No hardware imports.
"""
from PyQt5.QtWidgets import QLabel, QFrame
from PyQt5.QtCore import Qt


def make_separator(parent=None) -> QFrame:
    """Return a horizontal QFrame separator line."""
    line = QFrame(parent)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def make_status_label(text: str = "", parent=None) -> QLabel:
    """Return a bold status label."""
    lbl = QLabel(text, parent)
    lbl.setStyleSheet("font-weight: bold;")
    return lbl
