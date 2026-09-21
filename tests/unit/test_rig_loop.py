"""
Unit tests for Rig loop, command queue, Snapshot publication, staleness, and reconnection.

WHY THIS EXISTS
---------------
ADR 0002 mandates that a single Rig module owns all hardware I/O and executes a
single loop: read -> publish immutable Snapshot -> safety -> control step -> write.
The GUI, Run record, and safety evaluator never block on or touch hardware directly.

These tests prove ticket 03: the Rig loop drains commands, manages reconnection
safely (forcing off, 0 V, and pinning current limit before trusting reads), tracks
per-source staleness, and publishes Snapshots to consumers.
"""
from dataclasses import FrozenInstanceError, is_dataclass
import queue
import pytest

from t8_daq_system.rig.adapter import RawReadings, RigAdapter
from t8_daq_system.rig.clock import ManualClock
from t8_daq_system.rig.commands import (
    ConfirmContinue,
    LoadProgram,
    Nudge,
    ResetTrip,
    SelectAdapter,
    SetOutput,
    SetVoltage,
    StartProgram,
    StopProgram,
    UpdateConfig,
)
from t8_daq_system.rig.rig import Rig
from t8_daq_system.rig.simulated import SimulatedRig
from t8_daq_system.rig.snapshot import Snapshot
from t8_daq_system.settings.safety_limits import RECONNECT_INTERVAL_S


class CallSpyAdapter(RigAdapter):
    """Spy wrapper around RigAdapter to record call sequence."""

    def __init__(self, target: RigAdapter) -> None:
        self._target = target
        self.calls: list[object] = []

    def connect(self) -> bool:
        self.calls.append("connect")
        return self._target.connect()

    def disconnect(self) -> None:
        self.calls.append("disconnect")
        self._target.disconnect()

    def is_connected(self) -> bool:
        return self._target.is_connected()

    def read(self) -> RawReadings:
        self.calls.append("read")
        return self._target.read()

    def write_voltage(self, volts: float) -> None:
        self.calls.append(("write_voltage", volts))
        self._target.write_voltage(volts)

    def set_output(self, enabled: bool) -> None:
        self.calls.append(("set_output", enabled))
        self._target.set_output(enabled)

    def pin_current_limit(self) -> None:
        self.calls.append("pin_current_limit")
        self._target.pin_current_limit()


def test_command_dataclasses_are_frozen():
    """All command types from the spec must be frozen dataclasses."""
    command_types = [
        LoadProgram,
        StartProgram,
        StopProgram,
        ConfirmContinue,
        Nudge,
        SetVoltage,
        SetOutput,
        ResetTrip,
        SelectAdapter,
        UpdateConfig,
    ]
    for cmd_cls in command_types:
        assert is_dataclass(cmd_cls), f"{cmd_cls.__name__} must be a dataclass"

    nudge = Nudge(direction="up")
    with pytest.raises(FrozenInstanceError):
        nudge.direction = "down"  # type: ignore[misc]

    set_v = SetVoltage(volts=2.5)
    with pytest.raises(FrozenInstanceError):
        set_v.volts = 0.0  # type: ignore[misc]


def test_tick_publishes_snapshot_with_readings_and_source_ages():
    """A tick against SimulatedRig publishes Snapshot with TC °C, pressure in Torr, PS V/I, and source_age_s."""
    clock = ManualClock(start_time=100.0)
    sim_rig = SimulatedRig(clock=clock, tc_names=["TC_1", "TC_2"], gauge_names=["FRG702_Chamber"])
    rig = Rig(adapter=sim_rig, clock=clock)

    rig.run_tick()
    snap = rig.latest()
    assert isinstance(snap, Snapshot)
    assert snap.t == 100.0
    assert snap.tc_c["TC_1"] is not None
    assert snap.tc_c["TC_2"] is not None
    assert snap.pressure_torr["FRG702_Chamber"] == pytest.approx(1e-7)
    assert snap.ps_volts == 0.0
    assert snap.ps_amps == 0.0
    assert snap.source_age_s["TC_1"] == 0.0
    assert snap.source_age_s["TC_2"] == 0.0
    assert snap.source_age_s["FRG702_Chamber"] == 0.0
    assert snap.labjack.state == "connected"
    assert snap.heater.state == "off"
    assert snap.adapter == "simulated"


def test_dropped_tc_age_grows_and_restore_resets():
    """A dropped TC's age grows tick by tick; restoring it resets to 0."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock, tc_names=["TC_1"])
    rig = Rig(adapter=sim_rig, clock=clock)

    rig.run_tick()
    assert rig.latest().source_age_s["TC_1"] == 0.0

    sim_rig.drop_tc("TC_1")
    clock.advance(1.0)
    rig.run_tick()
    snap1 = rig.latest()
    assert snap1.source_age_s["TC_1"] == pytest.approx(1.0)
    assert snap1.tc_c["TC_1"] is None

    clock.advance(2.5)
    rig.run_tick()
    snap2 = rig.latest()
    assert snap2.source_age_s["TC_1"] == pytest.approx(3.5)
    assert snap2.tc_c["TC_1"] is None

    sim_rig.restore_tc("TC_1")
    clock.advance(0.5)
    rig.run_tick()
    snap3 = rig.latest()
    assert snap3.source_age_s["TC_1"] == 0.0
    assert snap3.tc_c["TC_1"] is not None


def test_disconnect_shows_lost_and_reconnect_issues_exact_first_three_calls():
    """disconnect() -> LabJack lost; reconnect() + enough clock -> exact calls: off, 0 V, pin current limit."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    spy = CallSpyAdapter(sim_rig)
    rig = Rig(adapter=spy, clock=clock)

    # Initial tick establishes baseline
    rig.run_tick()
    assert rig.latest().labjack.state == "connected"

    # Simulate link drop
    sim_rig.disconnect()
    spy.calls.clear()
    clock.advance(0.5)
    rig.run_tick()

    snap_lost = rig.latest()
    assert snap_lost.labjack.state == "lost"
    assert snap_lost.heater.trip_kind == "labjack_lost"

    # Reconnect hardware link, but not enough clock has passed for Rig's reconnect timer
    sim_rig.reconnect()
    clock.advance(10.0)  # 10s < RECONNECT_INTERVAL_S (30s)
    spy.calls.clear()
    rig.run_tick()

    assert rig.latest().labjack.state == "lost"
    assert "connect" not in spy.calls

    # Now advance clock to exceed RECONNECT_INTERVAL_S
    clock.advance(RECONNECT_INTERVAL_S - 9.0)  # total exceeds RECONNECT_INTERVAL_S
    spy.calls.clear()
    rig.run_tick()

    assert rig.latest().labjack.state == "connected"
    # The adapter's first three calls upon reconnect must be:
    # set_output(False), write_voltage(0.0), pin_current_limit()
    # in that order, before any read is trusted.
    expected_sequence = [
        "connect",
        ("set_output", False),
        ("write_voltage", 0.0),
        "pin_current_limit",
        "read",
    ]
    assert spy.calls[:5] == expected_sequence


def test_reconnect_not_attempted_more_often_than_reconnect_interval():
    """Reconnect is not attempted more often than RECONNECT_INTERVAL_S."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    spy = CallSpyAdapter(sim_rig)
    rig = Rig(adapter=spy, clock=clock)

    rig.run_tick()
    assert rig.latest().labjack.state == "connected"

    # Simulate disconnection
    sim_rig.disconnect()
    clock.advance(0.5)
    rig.run_tick()
    assert rig.latest().labjack.state == "lost"

    spy.calls.clear()
    # Advance clock incrementally below RECONNECT_INTERVAL_S
    for step in [1.0, 5.0, 10.0, 10.0]:  # sum = 26.0s < RECONNECT_INTERVAL_S (30s)
        clock.advance(step)
        rig.run_tick()

    assert "connect" not in spy.calls

    # Once RECONNECT_INTERVAL_S has passed, reconnect is attempted
    clock.advance(RECONNECT_INTERVAL_S - 25.0)
    rig.run_tick()
    assert "connect" in spy.calls


def test_select_adapter_refused_when_logging_active_and_accepted_when_idle():
    """SelectAdapter is refused with a reason while logging is active, and accepted when idle."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    rig = Rig(adapter=sim_rig, clock=clock)
    rig.run_tick()

    # Refused while logging is active
    rig.set_logging_active(True)
    rig.submit(SelectAdapter(practice=False))
    rig.run_tick()

    snap_refused = rig.latest()
    assert snap_refused.adapter_refusal_reason is not None
    assert "logging" in snap_refused.adapter_refusal_reason.lower()

    # Next tick with no command has reason cleared
    rig.run_tick()
    assert rig.latest().adapter_refusal_reason is None

    # Accepted when idle
    rig.set_logging_active(False)
    rig.submit(SelectAdapter(practice=False))
    rig.run_tick()

    snap_accepted = rig.latest()
    assert snap_accepted.adapter_refusal_reason is None


def test_snapshot_consumer_receives_snapshot():
    """Snapshot is handed to consumer queue on each tick."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    consumer_q: queue.Queue[Snapshot] = queue.Queue()
    rig = Rig(adapter=sim_rig, clock=clock, snapshot_consumer=consumer_q)

    rig.run_tick()
    assert not consumer_q.empty()
    item = consumer_q.get_nowait()
    assert item == rig.latest()


def test_update_config_adjusts_tick_period():
    """UpdateConfig modifies sample rate and recalculates tick period."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    rig = Rig(adapter=sim_rig, clock=clock, sample_rate_ms=1000.0)
    assert rig.tick_period_s == 0.5  # min(1.0, 0.5)

    rig.submit(UpdateConfig(sample_rate_ms=200.0))
    rig.run_tick()
    assert rig.tick_period_s == pytest.approx(0.2)  # min(0.2, 0.5)


def test_read_failure_marks_labjack_lost_and_publishes_snapshot():
    """On AdapterError during read(), LabJack becomes lost, records labjack_lost, and hands Snapshot to queue."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    consumer_q: queue.Queue[Snapshot] = queue.Queue()
    rig = Rig(adapter=sim_rig, clock=clock, snapshot_consumer=consumer_q)

    # Initial tick succeeds
    rig.run_tick()
    assert rig.latest().labjack.state == "connected"
    assert consumer_q.get_nowait() == rig.latest()

    # Simulate link failure on read
    sim_rig.disconnect()
    clock.advance(0.5)
    rig.run_tick()

    snap = rig.latest()
    assert snap is not None
    assert snap.labjack.state == "lost"
    assert snap.heater.trip_kind == "labjack_lost"
    assert not consumer_q.empty()
    assert consumer_q.get_nowait() == snap


def test_select_adapter_refused_when_program_running():
    """SelectAdapter is refused if a program is marked running."""
    clock = ManualClock(start_time=0.0)
    sim_rig = SimulatedRig(clock=clock)
    rig = Rig(adapter=sim_rig, clock=clock)

    # Simulate running program status
    rig._program_status = rig._program_status.__class__(running=True)

    rig.submit(SelectAdapter(practice=False))
    rig.run_tick()

    snap = rig.latest()
    assert snap.adapter_refusal_reason is not None
    assert "program" in snap.adapter_refusal_reason.lower()

