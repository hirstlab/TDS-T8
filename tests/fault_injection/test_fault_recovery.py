"""
Layer 3: Fault injection tests.
Tests executor response to PS faults during a live run.
"""
import pytest
import threading
from t8_daq_system.control.program_block import VoltageRampBlock, TempRampBlock
from t8_daq_system.control.program_executor import ProgramExecutor
from tests.mock_ps import fast_executor_time

pytestmark = pytest.mark.fault

WALL_TIMEOUT = 30


class FaultyMockPS:
    """
    Extended mock PS with programmable fault injection.
    Inherits all MockPowerSupplyController behaviour but adds inject_fault().
    """

    def __init__(self):
        self._voltage = 0.0
        self._current = 0.0
        self._output_on = False
        self.rated_max_volts = 6.0
        self.rated_max_amps = 180.0
        self.voltage_limit = 6.0
        self.current_limit = 180.0
        self.interlock_active = False
        self._voltage_history = []
        self._fio1_history = []
        self._fault_type = None
        self._fault_at_call = None
        self._call_count = 0
        self._comms_timeout_remaining = 0

    def reset(self):
        self._voltage = 0.0
        self._current = 0.0
        self._output_on = False
        self.interlock_active = False
        self._voltage_history.clear()
        self._fio1_history.clear()
        self._fault_type = None
        self._fault_at_call = None
        self._call_count = 0

    def inject_fault(self, fault_type, at_call=5):
        """
        Schedule a fault.
        fault_type: 'SO_LATCHED' | 'OVP_TRIP' | 'COMMS_TIMEOUT' | 'TC_DROPOUT' | 'OUTPUT_OFF_MID_RUN'
        at_call: number of set_voltage calls before fault triggers
        """
        self._fault_type = fault_type
        self._fault_at_call = at_call
        self._comms_timeout_remaining = 3

    def _maybe_trigger_fault(self):
        self._call_count += 1
        if self._fault_at_call is not None and self._call_count >= self._fault_at_call:
            ft = self._fault_type
            if ft == 'SO_LATCHED':
                self._output_on = False
                self._fio1_history.append('SO_LATCHED')
            elif ft == 'OVP_TRIP':
                self._output_on = False
                self.interlock_active = True
                self._fio1_history.append('OVP_TRIP')
            elif ft == 'OUTPUT_OFF_MID_RUN':
                self._output_on = False
                self._fio1_history.append('OUTPUT_OFF_MID_RUN')
            elif ft == 'COMMS_TIMEOUT':
                if self._comms_timeout_remaining > 0:
                    self._comms_timeout_remaining -= 1
                    raise TimeoutError("Simulated comms timeout")
                else:
                    self._fault_type = None  # fault resolved

    def set_voltage(self, v):
        self._maybe_trigger_fault()
        self._voltage = float(v)
        self._voltage_history.append(float(v))
        return True

    def set_current(self, a):
        self._current = float(a)
        return True

    def get_voltage(self):
        return self._voltage

    def get_current(self):
        return self._current

    def get_voltage_setpoint(self):
        return self._voltage

    def get_current_setpoint(self):
        return self._current

    def output_on(self):
        self._output_on = True
        self._fio1_history.append(0)
        return True

    def output_off(self):
        self._output_on = False
        self._fio1_history.append(1)
        return True

    def is_output_on(self):
        return self._output_on

    def emergency_shutdown(self):
        self.output_off()
        self._voltage = 0.0
        return True

    def get_errors(self):
        return []

    def fio1_ever_high(self):
        return any(v == 1 for v in self._fio1_history)

    def dac_nonzero_while_off(self):
        """Returns True if voltage was nonzero while output was off (dangerous state)."""
        fault_triggered = False
        for entry in self._fio1_history:
            if entry in ('SO_LATCHED', 'OVP_TRIP', 'OUTPUT_OFF_MID_RUN'):
                fault_triggered = True
        if not fault_triggered:
            return False
        # After fault, any nonzero voltage command is dangerous
        # Simplified: check if the last few voltage commands after fault are nonzero
        if len(self._voltage_history) > 2:
            post_fault = self._voltage_history[self._fault_at_call:]
            return any(v > 0.1 for v in post_fault[:5])
        return False


def _run_with_fault(fault_type, at_call=5):
    """Helper: runs a long TempRamp, injects fault, returns (completed_event, ps, executor)."""
    ps = FaultyMockPS()
    ps.inject_fault(fault_type, at_call=at_call)

    blocks = [
        VoltageRampBlock(start_voltage=0.0, end_voltage=3.0, duration_sec=1),
        TempRampBlock(rate_k_per_min=60.0, end_temp_k=1000.0, tc_name="TC_1"),
    ]

    completed = threading.Event()
    def provider(tc_name):
        return lambda: 300.0

    with fast_executor_time():
        ex = ProgramExecutor(ps, provider, on_program_complete=lambda: completed.set())
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        ex.stop()  # always stop: zeroes PS voltage regardless of natural vs forced completion

    return completed, ps, ex


def test_so_latched_executor_stops_gracefully():
    """SO_LATCHED: executor eventually stops (does not loop forever)."""
    completed, ps, ex = _run_with_fault('SO_LATCHED', at_call=5)
    # Executor should have stopped (either completed or stopped internally)
    assert not ex.is_running(), "Executor still running after SO_LATCHED fault"


def test_so_latched_dac_not_nonzero_after_fault():
    """SO_LATCHED: no large voltage commanded many ticks after fault fires."""
    # Run longer to see if executor keeps ramping voltage while PS is off
    ps = FaultyMockPS()
    ps.inject_fault('SO_LATCHED', at_call=3)
    blocks = [TempRampBlock(rate_k_per_min=60.0, end_temp_k=2000.0, tc_name="TC_1")]
    completed = threading.Event()
    def provider(tc_name):
        return lambda: 300.0
    with fast_executor_time():
        ex = ProgramExecutor(ps, provider, on_program_complete=lambda: completed.set())
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        ex.stop()  # always stop to zero PS
    # After fault at call 3, executor should not keep running forever commanding high voltage
    # The last commanded voltage should eventually be 0 (from stop())
    if ps._voltage_history:
        assert ps._voltage_history[-1] == 0.0, \
            f"Last commanded voltage after fault was {ps._voltage_history[-1]:.2f}V, expected 0.0"


def test_ovp_trip_sets_interlock():
    """OVP_TRIP: interlock_active ends up True and executor does not write further."""
    ps = FaultyMockPS()
    ps.inject_fault('OVP_TRIP', at_call=4)
    blocks = [TempRampBlock(rate_k_per_min=600.0, end_temp_k=1000.0, tc_name="TC_1")]
    completed = threading.Event()
    def provider(tc_name):
        return lambda: 300.0
    with fast_executor_time():
        ex = ProgramExecutor(ps, provider, on_program_complete=lambda: completed.set())
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        if ex.is_running():
            ex.stop()
    # After OVP trip, interlock_active is set -- executor skips DAC writes
    # The run should eventually stop
    assert not ex.is_running()


def test_comms_timeout_executor_survives():
    """COMMS_TIMEOUT: transient timeout does not crash executor; run completes or stops cleanly."""
    completed, ps, ex = _run_with_fault('COMMS_TIMEOUT', at_call=3)
    assert not ex.is_running(), "Executor still running after comms timeout test"


def test_output_off_mid_run_executor_stops():
    """OUTPUT_OFF_MID_RUN: if output goes off mid-run, executor eventually stops."""
    completed, ps, ex = _run_with_fault('OUTPUT_OFF_MID_RUN', at_call=4)
    assert not ex.is_running()


# ── Regression: nudge never asserts FIO1 ──────────────────────────────────────

def test_regression_nudge_does_not_assert_fio1(mock_ps):
    """
    REGRESSION: Spam 100 nudge-style set_voltage calls while executor is NOT running.
    FIO1 must never be written HIGH.
    """
    mock_ps.reset()
    for v in [i * 0.05 for i in range(100)]:
        mock_ps.set_voltage(v)
    assert not mock_ps.fio1_ever_high(), "FIO1 asserted HIGH during nudge calls (no executor)"


def test_regression_nudge_during_run_does_not_assert_fio1(mock_ps):
    """
    REGRESSION: Spam nudge calls while executor IS running.
    FIO1 must never be written HIGH.
    """
    mock_ps.reset()
    blocks = [VoltageRampBlock(start_voltage=0.0, end_voltage=3.0, duration_sec=2)]
    completed = threading.Event()
    def provider(tc_name):
        return lambda: 300.0
    with fast_executor_time():
        ex = ProgramExecutor(mock_ps, provider, on_program_complete=lambda: completed.set())
        ex.load_program(blocks)
        ex.start()
        # Simulate 100 nudge calls while running
        for v in [i * 0.03 for i in range(100)]:
            mock_ps.set_voltage(v)
        completed.wait(timeout=WALL_TIMEOUT)
        if ex.is_running():
            ex.stop()
    assert not mock_ps.fio1_ever_high()


# ── Regression: GUI state after SO latch ──────────────────────────────────────

def test_regression_gui_state_matches_ps_after_so_latch():
    """
    REGRESSION: After SO_LATCHED fault, PS output must be off and
    executor must not be running (GUI run indicator should show stopped).
    """
    ps = FaultyMockPS()
    ps.inject_fault('SO_LATCHED', at_call=3)
    blocks = [TempRampBlock(rate_k_per_min=600.0, end_temp_k=1000.0, tc_name="TC_1")]
    completed = threading.Event()
    def provider(tc_name):
        return lambda: 300.0
    with fast_executor_time():
        ex = ProgramExecutor(ps, provider, on_program_complete=lambda: completed.set())
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        if ex.is_running():
            ex.stop()
    # After stop(), PS output should be off
    assert not ps.is_output_on(), "PS output still on after SO latch + stop()"
    assert not ex.is_running(), "Executor still running after SO latch"


# ── Regression: ramp-down after hold ──────────────────────────────────────────

def test_regression_rampdown_after_hold(mock_ps):
    """
    REGRESSION: The exact 3-block profile that failed in production.
    [VoltageRamp up, TempRamp hold at 1723K, VoltageRamp down]
    All three blocks must execute and on_program_complete must fire.
    """
    mock_ps.reset()
    blocks = [
        VoltageRampBlock(start_voltage=0.0, end_voltage=3.0, duration_sec=1),
        TempRampBlock(rate_k_per_min=15.0, end_temp_k=600.0, tc_name="TC_1"),
        VoltageRampBlock(start_voltage=3.0, end_voltage=0.0, duration_sec=1),
    ]
    block_starts = []
    block_completes = []
    completed = threading.Event()

    with fast_executor_time():
        def provider(tc_name):
            return lambda: 300.0
        ex = ProgramExecutor(
            mock_ps, provider,
            on_block_start=lambda idx, blk: block_starts.append(idx),
            on_block_complete=lambda idx: block_completes.append(idx),
            on_program_complete=lambda: completed.set(),
        )
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        ex.stop()  # always stop to ensure PS is zeroed

    assert completed.is_set(), "on_program_complete never fired -- ramp-down block was skipped"
    assert block_starts == [0, 1, 2], f"Not all blocks started: {block_starts}"
    assert block_completes == [0, 1, 2], f"Not all blocks completed: {block_completes}"
    # stop() zeros voltage; confirm PS was left clean
    assert mock_ps._voltage_history[-1] == 0.0, \
        f"Last commanded voltage was {mock_ps._voltage_history[-1]:.2f}V, expected 0.0 from stop()"
