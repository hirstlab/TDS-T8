"""
Unit tests for T8Adapter and pressure canonicalisation in Torr.

WHY THIS EXISTS
---------------
ADR 0002 and ADR 0004 establish that one Rig module owns hardware I/O and that
pressure is canonicalised in Torr internally. Previously, FRG702Reader converted
readings to the operator's display unit (default mbar or Pa) before passing them
to DataAcquisition, causing the 1e-4 Torr safety interlock to trip 25% early in mbar
and immediately in Pa.

T8Adapter wraps LabJack, thermocouple, gauge, and power supply hardware behind
the RigAdapter protocol, ensuring:
1. Every gauge reading leaves read() in Torr regardless of display unit setting.
2. write_voltage touches DAC0 only; pin_current_limit touches DAC1 only.
3. set_output(False) preserves the 3-attempt verify.
4. LJM failures raise AdapterError without swallowing exceptions.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from t8_daq_system.rig.adapter import AdapterError, RigAdapter
from t8_daq_system.rig.t8_adapter import T8Adapter
from t8_daq_system.utils.helpers import convert_pressure

pytestmark = pytest.mark.unit

mock_ljm = sys.modules["labjack"].ljm


@pytest.fixture(autouse=True)
def reset_mock_ljm():
    mock_ljm.reset_mock()
    mock_ljm.LJMError = type("LJMError", (Exception,), {})
    mock_ljm.openS.return_value = 1
    # Default mock register reads:
    # AIN4 (voltage monitor): 0.0V (0V output)
    # AIN5 (current monitor): 0.0V (0A output)
    # FIO1 (shutoff readback): 1 (shut off / disabled)
    def default_read_name(handle, name):
        if name == "AIN4":
            return 0.0
        if name == "AIN5":
            return 0.0
        if name == "FIO1":
            return 1.0
        if name == "DAC0":
            return 0.0
        if name == "DAC1":
            return 5.0
        return 0.0

    mock_ljm.eReadName.side_effect = default_read_name
    mock_ljm.eReadNames.return_value = [25.0]
    yield
    mock_ljm.eReadName.side_effect = None
    mock_ljm.eWriteName.side_effect = None
    mock_ljm.eReadNames.side_effect = None


def _make_config(p_unit: str = "mbar") -> dict:
    return {
        "thermocouples": [
            {"name": "TC_1", "channel": 0, "type": "K", "units": "C", "enabled": True},
        ],
        "frg702_gauges": [
            {"name": "FRG702_Chamber", "sensor_code": "T1", "pin": "AIN6", "units": p_unit, "enabled": True},
        ],
        "frg_interface": "XGS600",
        "xgs600": {
            "enabled": True,
            "port": "COM4",
            "baudrate": 9600,
            "timeout": 1.0,
            "address": "00",
        },
        "power_supply": {
            "enabled": True,
            "voltage_pin": "DAC0",
            "current_pin": "DAC1",
            "voltage_monitor_pin": "AIN4",
            "current_monitor_pin": "AIN5",
            "rated_max_volts": 6.0,
            "rated_max_amps": 180.0,
            "default_voltage_limit": 6.0,
            "default_current_limit": 180.0,
        },
    }


def test_t8_adapter_implements_rig_adapter():
    config = _make_config()
    adapter = T8Adapter(config=config)
    assert isinstance(adapter, RigAdapter)


def test_pressure_unit_bug_regression_same_torr_for_all_display_units():
    """
    REGRESSION TEST FOR UNIT BUG:
    The same physical pressure (e.g. 1.0e-5 Torr from the XGS-600) configured
    for mbar, Torr, or Pa display MUST reach read() as the exact same Torr value
    (1.0e-5 Torr).
    """
    physical_torr = 1.0e-5

    for display_unit in ["mbar", "Torr", "Pa"]:
        config = _make_config(p_unit=display_unit)
        adapter = T8Adapter(config=config)
        assert adapter.connect() is True

        # Mock the XGS-600 controller inside the adapter
        adapter._xgs_controller.is_connected = MagicMock(return_value=True)
        adapter._xgs_controller.read_units = MagicMock(return_value="Torr")
        adapter._xgs_controller.read_pressure = MagicMock(return_value=physical_torr)
        adapter._frg_reader._device_unit = "Torr"

        readings = adapter.read()
        chamber_p = readings.pressure_torr["FRG702_Chamber"]
        assert chamber_p is not None
        assert chamber_p == pytest.approx(physical_torr, rel=1e-6), (
            f"Display unit '{display_unit}' corrupted canonical Torr value: got {chamber_p}, expected {physical_torr}"
        )
        assert readings.pressure_valid["FRG702_Chamber"] is True


def test_screen_shows_pressure_in_selected_display_unit():
    """
    Pure conversion function correctly converts canonical Torr readings to the
    display unit chosen by the operator, ensuring the UI display reflects the selection.
    """
    canonical_torr = 7.50062e-5  # exactly 1.0e-4 mbar

    # Display in mbar
    mbar_val = convert_pressure(canonical_torr, "Torr", "mbar")
    assert mbar_val == pytest.approx(1.0e-4, rel=1e-5)

    # Display in Torr
    torr_val = convert_pressure(canonical_torr, "Torr", "Torr")
    assert torr_val == pytest.approx(7.50062e-5, rel=1e-5)

    # Display in Pa
    pa_val = convert_pressure(canonical_torr, "Torr", "Pa")
    assert pa_val == pytest.approx(0.01, rel=1e-4)


def test_write_voltage_touches_dac0_only():
    """
    CV-only invariant: write_voltage writes DAC0 only; no call path writes DAC1
    except pin_current_limit.
    """
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    mock_ljm.eWriteName.reset_mock()
    adapter.write_voltage(2.5)

    written_registers = [call.args[1] for call in mock_ljm.eWriteName.call_args_list]
    assert "DAC0" in written_registers
    assert "DAC1" not in written_registers


def test_pin_current_limit_sets_dac1_to_full_scale():
    """
    pin_current_limit sets DAC1 to full scale (5.0V / 180A) and is the only DAC1 write.
    """
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    mock_ljm.eWriteName.reset_mock()
    adapter.pin_current_limit()

    written_registers = [call.args[1] for call in mock_ljm.eWriteName.call_args_list]
    assert "DAC1" in written_registers
    assert "DAC0" not in written_registers

    # Find the write to DAC1 and check voltage value (5.0 V is full scale 180 A)
    for call in mock_ljm.eWriteName.call_args_list:
        if call.args[1] == "DAC1":
            assert call.args[2] == pytest.approx(5.0)


def test_mocked_ljm_failure_in_read_raises_adapter_error():
    """A mocked LJM failure during read() raises AdapterError."""
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    # Simulate LJM failure when reading voltage monitor
    def fail_on_read(handle, name):
        if name == "AIN4":
            raise mock_ljm.LJMError("LabJack read timeout")
        return 0.0

    mock_ljm.eReadName.side_effect = fail_on_read

    with pytest.raises(AdapterError, match="LabJack|monitor|read"):
        adapter.read()


def test_mocked_ljm_failure_in_write_voltage_raises_adapter_error():
    """A mocked LJM failure in write_voltage raises AdapterError."""
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    def fail_on_write(handle, name, value):
        if name == "DAC0":
            raise mock_ljm.LJMError("DAC0 write failure")

    mock_ljm.eWriteName.side_effect = fail_on_write

    with pytest.raises(AdapterError, match="DAC0|voltage"):
        adapter.write_voltage(1.5)


def test_mocked_ljm_failure_in_set_output_raises_adapter_error():
    """A mocked LJM failure in set_output raises AdapterError."""
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    def fail_on_fio(handle, name, value=None):
        if name == "FIO1":
            raise mock_ljm.LJMError("FIO1 link dropped")

    mock_ljm.eWriteName.side_effect = fail_on_fio

    with pytest.raises(AdapterError):
        adapter.set_output(False)

    with pytest.raises(AdapterError):
        adapter.set_output(True)


def test_set_output_false_keeps_three_attempt_verify():
    """
    set_output(False) keeps today's 3-attempt verify to ensure output is disabled.
    """
    adapter = T8Adapter(config=_make_config())
    assert adapter.connect() is True

    # When FIO1 readback always says output is ON (0.0), output_off should retry 3 times and fail
    def read_always_on(handle, name):
        if name == "FIO1":
            return 0.0  # 0 = ON, so verify fails
        return 0.0

    mock_ljm.eReadName.side_effect = read_always_on
    mock_ljm.eWriteName.reset_mock()

    with pytest.raises(AdapterError):
        adapter.set_output(False)

    fio1_writes = [call for call in mock_ljm.eWriteName.call_args_list if call.args[1] == "FIO1"]
    assert len(fio1_writes) == 3


def test_rig_runs_with_t8_adapter():
    """Verify Rig runs ticks against T8Adapter publishing snapshots."""
    from t8_daq_system.rig.clock import ManualClock
    from t8_daq_system.rig.rig import Rig

    clock = ManualClock(start_time=100.0)
    config = _make_config()
    adapter = T8Adapter(config=config)
    assert adapter.connect() is True

    # Mock gauge readings on XGS-600
    adapter._xgs_controller.is_connected = MagicMock(return_value=True)
    adapter._xgs_controller.read_units = MagicMock(return_value="Torr")
    adapter._xgs_controller.read_pressure = MagicMock(return_value=2.5e-6)
    adapter._frg_reader._device_unit = "Torr"

    rig = Rig(adapter=adapter, clock=clock, tc_names=["TC_1"], gauge_names=["FRG702_Chamber"])
    rig.run_tick()
    snap = rig.latest()

    assert snap is not None
    assert snap.adapter == "t8"
    assert snap.tc_c["TC_1"] == 25.0
    assert snap.pressure_torr["FRG702_Chamber"] == pytest.approx(2.5e-6)
    assert snap.heater.state == "off"
