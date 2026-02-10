"""
test_turbo_pump_panel.py
PURPOSE: Unit tests for TurboPumpPanel button handler logic.

Since tkinter is fully mocked (headless CI), TurboPumpPanel cannot be
instantiated normally. We re-compile the module source with the import
lines replaced so that TurboPumpPanel inherits from `object` instead of
``ttk.LabelFrame``.
"""

import pytest
import sys
from unittest.mock import Mock, MagicMock

# ---------------------------------------------------------------------------
# Re-compile turbo_pump_panel.py with patched imports so that
# TurboPumpPanel becomes a normal instantiable class.
# ---------------------------------------------------------------------------
from t8_daq_system.gui import turbo_pump_panel as _orig_module

_src_path = _orig_module.__file__
with open(_src_path) as _f:
    _src = _f.read()

# Patch the source: replace tkinter imports and the base class
_patched = _src.replace(
    "import tkinter as tk\nfrom tkinter import ttk, messagebox",
    "from unittest.mock import MagicMock as _Mock\n"
    "tk = _Mock()\n"
    "ttk = _Mock()\n"
    "messagebox = _Mock()\n"
    "# Make LabelFrame = object so TurboPumpPanel is a real class\n"
    "class _LabelFrame: pass"
).replace(
    "class TurboPumpPanel(ttk.LabelFrame):",
    "class TurboPumpPanel(_LabelFrame):"
)

_ns = {'__builtins__': __builtins__}
exec(compile(_patched, _src_path, 'exec'), _ns)
RealPanel = _ns['TurboPumpPanel']
_msgbox_ref = _ns  # We'll swap messagebox in _ns before each test


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_controller():
    ctrl = Mock()
    ctrl.start.return_value = (True, "Start command sent")
    ctrl.stop.return_value = (True, "Stop command sent")
    ctrl.read_status.return_value = "OFF"
    ctrl.is_commanded_on.return_value = False
    return ctrl


@pytest.fixture
def panel():
    p = RealPanel.__new__(RealPanel)
    p.controller = None
    p._pressure_ok = False
    p._current_pressure_torr = None
    # Mock the GUI widgets referenced by handlers
    p.message_label = MagicMock()
    p.status_indicator = MagicMock()
    p.status_label = MagicMock()
    p.on_btn = MagicMock()
    p.off_btn = MagicMock()
    p.turbo_interlock_indicator = MagicMock()
    p.turbo_interlock_label = MagicMock()
    p.pressure_display = MagicMock()
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPanelCommands:
    """Tests for button click handlers."""

    def test_on_calls_start_after_confirm(self, panel, mock_controller):
        mock_msgbox = MagicMock()
        mock_msgbox.askyesno.return_value = True
        _ns['messagebox'] = mock_msgbox

        panel.set_controller(mock_controller)
        panel._pressure_ok = True
        panel._on_turbo_on()
        mock_controller.start.assert_called_once()

    def test_on_cancelled_does_not_start(self, panel, mock_controller):
        mock_msgbox = MagicMock()
        mock_msgbox.askyesno.return_value = False
        _ns['messagebox'] = mock_msgbox

        panel.set_controller(mock_controller)
        panel._pressure_ok = True
        panel._on_turbo_on()
        mock_controller.start.assert_not_called()

    def test_off_calls_stop(self, panel, mock_controller):
        panel.set_controller(mock_controller)
        panel._on_turbo_off()
        mock_controller.stop.assert_called_once()

    def test_on_blocked_by_pressure_interlock(self, panel, mock_controller):
        mock_msgbox = MagicMock()
        _ns['messagebox'] = mock_msgbox

        panel.set_controller(mock_controller)
        panel._pressure_ok = False
        panel._on_turbo_on()
        mock_controller.start.assert_not_called()
        mock_msgbox.showwarning.assert_called_once()

    def test_set_controller_stores_reference(self, panel, mock_controller):
        panel.set_controller(mock_controller)
        assert panel.controller is mock_controller

    def test_set_controller_none_clears(self, panel, mock_controller):
        panel.set_controller(mock_controller)
        panel.set_controller(None)
        assert panel.controller is None
