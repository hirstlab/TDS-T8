"""
Shared pytest fixtures and configuration for TDS-T8 unit tests.

This conftest.py provides automatic mocking of hardware dependencies
(labjack, serial, tkinter, matplotlib) so that tests can run in any
environment -- even without the physical hardware or a display.

Usage:
    Simply run ``pytest`` from the project root.  The mocks below are
    applied **before** any test module is collected, so import-time
    side-effects in the production code are neutralised.
"""

import sys
import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock heavy / hardware dependencies that are unavailable in CI or
# headless environments.  These must be inserted into sys.modules
# BEFORE the test collector tries to import test files.
# ---------------------------------------------------------------------------

# ---- winreg (Windows registry — unavailable on Linux/macOS) ----
if "winreg" not in sys.modules:
    sys.modules["winreg"] = MagicMock()

# ---- LabJack LJM ----
_mock_ljm = MagicMock()
_mock_ljm.LJMError = type("LJMError", (Exception,), {})
_mock_labjack = MagicMock()
_mock_labjack.ljm = _mock_ljm
sys.modules.setdefault("labjack", _mock_labjack)
sys.modules.setdefault("labjack.ljm", _mock_ljm)

# ---- PySerial (used by xgs600_controller) ----
_mock_serial = MagicMock()
_mock_serial.Serial = MagicMock
_mock_serial.SerialException = type("SerialException", (Exception,), {})
sys.modules.setdefault("serial", _mock_serial)
sys.modules.setdefault("serial.tools", MagicMock())
sys.modules.setdefault("serial.tools.list_ports", MagicMock())

# ---- tkinter (GUI framework) ----
if "tkinter" not in sys.modules:
    _mock_tk = MagicMock()
    _mock_tk.__path__ = []
    sys.modules["tkinter"] = _mock_tk
    sys.modules["tkinter.ttk"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.font"] = MagicMock()
    sys.modules["tkinter.commondialog"] = MagicMock()
    sys.modules["tkinter.simpledialog"] = MagicMock()

# ---- matplotlib (plotting library) ----
if "matplotlib" not in sys.modules:
    _mock_mpl = MagicMock()
    _mock_mpl.__path__ = []
    sys.modules["matplotlib"] = _mock_mpl
    sys.modules["matplotlib.pyplot"] = MagicMock()
    sys.modules["matplotlib.figure"] = MagicMock()
    sys.modules["matplotlib.backends"] = MagicMock()
    sys.modules["matplotlib.backends.backend_tkagg"] = MagicMock()
    sys.modules["matplotlib.dates"] = MagicMock()

# ---------------------------------------------------------------------------
# Re-export MockPowerSupplyController from mock_ps module so that it is
# accessible both as a standalone class and via conftest fixtures.
# ---------------------------------------------------------------------------
from tests.mock_ps import MockPowerSupplyController  # noqa: E402


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ps():
    ps = MockPowerSupplyController()
    ps.reset()
    return ps


@pytest.fixture
def mock_temp_provider():
    """Returns a factory: mock_temp_provider(temp_k) -> get_temp_k_fn_provider"""
    def factory(temp_k=300.0):
        return lambda tc_name: (lambda: temp_k)
    return factory


@pytest.fixture
def make_executor(mock_ps):
    """Builds a ProgramExecutor wired to mock_ps. Usage: make_executor(temp_k=300.0)"""
    from t8_daq_system.control.program_executor import ProgramExecutor
    executors = []

    def factory(temp_k=300.0, on_block_start=None, on_block_complete=None,
                on_program_complete=None, on_status=None):
        provider = lambda tc_name: (lambda: temp_k)
        ex = ProgramExecutor(
            power_supply=mock_ps,
            get_temp_k_fn_provider=provider,
            on_block_start=on_block_start,
            on_block_complete=on_block_complete,
            on_program_complete=on_program_complete,
            on_status=on_status,
        )
        executors.append(ex)
        return ex

    yield factory

    for ex in executors:
        if ex.is_running():
            ex.stop()
