"""
Layer 4: State-sync invariant checker.
InvariantChecker hooks into on_status callback and asserts safety properties every tick.
"""
import pytest
import threading
from t8_daq_system.control.program_block import VoltageRampBlock, StableHoldBlock, TempRampBlock
from t8_daq_system.control.program_executor import ProgramExecutor
from tests.mock_ps import MockPowerSupplyController, fast_executor_time

pytestmark = pytest.mark.integration

WALL_TIMEOUT = 30


class InvariantChecker:
    """
    Attaches to on_status callback. Asserts invariants every tick.
    Violations are recorded with a timestamp; any violation fails the test.
    """

    def __init__(self, executor, ps):
        self._executor = executor
        self._ps = ps
        self.violations = []
        self._tick = 0
        self._last_block_index = -1

    def check(self, status):
        tick = self._tick
        self._tick += 1
        ex = self._executor
        ps = self._ps

        # Invariant 1: block_index is monotonically non-decreasing
        bi = status.get('block_index', 0)
        if bi < self._last_block_index:
            self.violations.append(
                f"tick={tick}: block_index went backwards {self._last_block_index} -> {bi}"
            )
        self._last_block_index = bi

        # Invariant 2: block_index < len(blocks) while running
        if ex.is_running() and bi >= len(ex._blocks):
            self.violations.append(
                f"tick={tick}: block_index={bi} >= len(blocks)={len(ex._blocks)} while running"
            )

        # Invariant 3: if PS output is off, voltage commanded should eventually be 0
        # (can't enforce same-tick due to async, but record if voltage > 0 and output is off)
        if not ps.is_output_on() and status.get('voltage_v', 0.0) > 0.5:
            self.violations.append(
                f"tick={tick}: voltage_v={status['voltage_v']:.2f}V commanded but output is off"
            )

    def assert_no_violations(self):
        if self.violations:
            msg = "Invariant violations:\n" + "\n".join(f"  {v}" for v in self.violations)
            pytest.fail(msg)


def _run_with_invariants(blocks, temp_k=300.0, timeout=WALL_TIMEOUT):
    ps = MockPowerSupplyController()
    ps.reset()

    completed = threading.Event()
    def provider(tc_name):
        return lambda: temp_k

    ex = ProgramExecutor(ps, provider, on_program_complete=lambda: completed.set())
    checker = InvariantChecker(ex, ps)
    ex._on_status = checker.check

    with fast_executor_time():
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=timeout)
        if ex.is_running():
            ex.stop()

    return checker, ex, ps


def test_invariants_voltage_ramp():
    blocks = [VoltageRampBlock(0.0, 3.0, 2), VoltageRampBlock(3.0, 0.0, 2)]
    checker, ex, ps = _run_with_invariants(blocks)
    checker.assert_no_violations()


def test_invariants_stable_hold():
    blocks = [
        VoltageRampBlock(0.0, 2.0, 1),
        StableHoldBlock(300.0, 50.0, 0.1),
        VoltageRampBlock(2.0, 0.0, 1),
    ]
    checker, ex, ps = _run_with_invariants(blocks)
    checker.assert_no_violations()


def test_invariants_temp_ramp():
    blocks = [
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        VoltageRampBlock(3.0, 0.0, 1),
    ]
    checker, ex, ps = _run_with_invariants(blocks, temp_k=300.0)
    checker.assert_no_violations()


def test_block_index_never_decreases():
    """block_index must only go forward."""
    blocks = [
        VoltageRampBlock(0.0, 1.0, 1),
        VoltageRampBlock(1.0, 2.0, 1),
        VoltageRampBlock(2.0, 3.0, 1),
        VoltageRampBlock(3.0, 0.0, 1),
    ]
    checker, ex, ps = _run_with_invariants(blocks)
    checker.assert_no_violations()
