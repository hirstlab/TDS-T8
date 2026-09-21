"""
Unit tests for rig snapshot dataclasses, adapter protocol, and raw readings.
"""
from dataclasses import FrozenInstanceError
import pytest

from t8_daq_system.rig.adapter import AdapterError, RawReadings, RigAdapter
from t8_daq_system.rig.snapshot import (
    HeaterStatus,
    ProgramStatus,
    Snapshot,
    SourceStatus,
)


def test_source_status_frozen():
    status = SourceStatus(state="connected", message="OK")
    assert status.state == "connected"
    assert status.message == "OK"
    with pytest.raises(FrozenInstanceError):
        status.state = "lost"  # type: ignore[misc]


def test_heater_status_frozen():
    status = HeaterStatus(
        state="off",
        trip_kind=None,
        trip_reason=None,
        shutoff_unverified=False,
    )
    assert status.state == "off"
    with pytest.raises(FrozenInstanceError):
        status.state = "on"  # type: ignore[misc]


def test_program_status_frozen():
    status = ProgramStatus(
        running=True,
        block_index=1,
        block_type="temp_ramp",
        waiting_for_confirmation=False,
        elapsed_in_block=12.5,
        setpoint_k=450.0,
        sched_kp=0.02,
        sched_ki=0.0013,
        sched_kd=0.005,
        sched_zone="low",
        ff_voltage=1.2,
        pid_correction=0.1,
    )
    assert status.running is True
    assert status.setpoint_k == 450.0
    with pytest.raises(FrozenInstanceError):
        status.running = False  # type: ignore[misc]


def test_snapshot_frozen_and_fields():
    snap = Snapshot(
        t=10.0,
        wall_time=1700000010.0,
        tc_c={"TC_1": 25.0},
        tc_raw_v={"TC_1": 0.001},
        pressure_torr={"FRG702_Chamber": 1.2e-7},
        source_age_s={"TC_1": 0.1, "FRG702_Chamber": 0.2},
        ps_volts=0.0,
        ps_amps=0.0,
        commanded_volts=0.0,
        output_enabled=False,
        labjack=SourceStatus(state="connected"),
        xgs=SourceStatus(state="connected"),
        heater=HeaterStatus(state="off"),
        program=ProgramStatus(),
        permissive_ok=True,
        permissive_reason=None,
        adapter="simulated",
    )
    assert snap.t == 10.0
    assert snap.adapter == "simulated"
    with pytest.raises(FrozenInstanceError):
        snap.t = 20.0  # type: ignore[misc]


def test_raw_readings_and_adapter_error():
    err = AdapterError("connection failed")
    assert isinstance(err, Exception)

    readings = RawReadings(
        tc_c={"TC_1": 25.0},
        tc_raw_v={"TC_1": 0.001},
        pressure_torr={"FRG702_Chamber": 1.2e-7},
        pressure_valid={"FRG702_Chamber": True},
        ps_volts=0.0,
        ps_amps=0.0,
        shutoff_readback=False,
    )
    assert readings.tc_c["TC_1"] == 25.0
    with pytest.raises(FrozenInstanceError):
        readings.ps_volts = 1.0  # type: ignore[misc]


def test_rig_adapter_protocol_methods():
    # RigAdapter protocol must define exactly the 7 methods from ADR/spec
    expected_methods = {
        "connect",
        "disconnect",
        "is_connected",
        "read",
        "write_voltage",
        "set_output",
        "pin_current_limit",
    }
    protocol_methods = {
        m
        for m in dir(RigAdapter)
        if not m.startswith("_") and callable(getattr(RigAdapter, m, None))
    }
    assert protocol_methods == expected_methods
