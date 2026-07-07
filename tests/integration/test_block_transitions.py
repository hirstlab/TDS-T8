"""
Layer 1: Block transition smoke tests.
Tests every 2-block and critical 3-block combination.
Patches time.sleep so executor runs at CPU speed.
"""
import pytest
import threading
import time
from t8_daq_system.control.program_block import VoltageRampBlock, StableHoldBlock, TempRampBlock
from t8_daq_system.control.program_executor import ProgramExecutor
from tests.mock_ps import fast_executor_time

pytestmark = pytest.mark.integration

WALL_TIMEOUT = 30  # seconds of real wall-clock time before test gives up


def run_program(executor, blocks, timeout=WALL_TIMEOUT):
    """
    Load and run a block list. Returns (completed, block_starts, block_completes).
    completed: threading.Event that fires when on_program_complete fires.
    """
    block_starts = []
    block_completes = []
    completed = threading.Event()

    executor._on_block_start = lambda idx, blk: block_starts.append(idx)
    executor._on_block_complete = lambda idx: block_completes.append(idx)
    executor._on_program_complete = lambda: completed.set()

    executor.load_program(blocks)
    executor.start()
    completed.wait(timeout=timeout)
    if executor.is_running():
        executor.stop()
    return completed, block_starts, block_completes


# ── 2-block smoke tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("block_a,block_b", [
    (
        VoltageRampBlock(start_voltage=0.0, end_voltage=2.0, duration_sec=1),
        VoltageRampBlock(start_voltage=2.0, end_voltage=3.0, duration_sec=1),
    ),
    (
        VoltageRampBlock(start_voltage=0.0, end_voltage=2.0, duration_sec=1),
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
    ),
    (
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
        VoltageRampBlock(start_voltage=2.0, end_voltage=0.0, duration_sec=1),
    ),
    (
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
    ),
    (
        VoltageRampBlock(start_voltage=0.0, end_voltage=2.0, duration_sec=1),
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
    ),
    (
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        VoltageRampBlock(start_voltage=2.0, end_voltage=0.0, duration_sec=1),
    ),
    (
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        # StableHold target at 300K so mock TC (fixed at 300K) is within tolerance
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
    ),
    (
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
    ),
    (
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        TempRampBlock(rate_k_per_min=-600.0, end_temp_k=300.0, tc_name="TC_1"),
    ),
])
def test_two_block_transition(mock_ps, block_a, block_b):
    """Every 2-block combo: both blocks execute and on_complete fires."""
    with fast_executor_time():
        provider = lambda tc_name: (lambda: 300.0)
        ex = ProgramExecutor(mock_ps, provider)
        completed, starts, completes = run_program(ex, [block_a, block_b])

    assert completed.is_set(), "on_program_complete never fired"
    assert 0 in starts, "Block 0 never started"
    assert 1 in starts, "Block 1 never started"
    assert 0 in completes, "Block 0 never completed"
    assert 1 in completes, "Block 1 never completed"
    assert not mock_ps.fio1_ever_high(), "FIO1 was asserted HIGH during normal run"


# ── 3-block regression tests (the specific bugs you hit) ──────────────────────

def test_voltage_ramp_tempramp_hold_rampdown(mock_ps):
    """
    BUG REGRESSION: [VoltageRamp(0->3V), TempRamp(ramp to 600K), VoltageRamp(3V->0V)]
    The ramp-down-after-hold case -- executor must run all 3 blocks.
    """
    blocks = [
        VoltageRampBlock(start_voltage=0.0, end_voltage=3.0, duration_sec=1),
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        VoltageRampBlock(start_voltage=3.0, end_voltage=0.0, duration_sec=1),
    ]
    with fast_executor_time():
        provider = lambda tc_name: (lambda: 300.0)
        ex = ProgramExecutor(mock_ps, provider)
        completed, starts, completes = run_program(ex, blocks)

    assert completed.is_set(), "on_program_complete never fired -- block 3 may have been skipped"
    assert starts == [0, 1, 2], f"Not all blocks started: {starts}"
    assert completes == [0, 1, 2], f"Not all blocks completed: {completes}"
    assert not mock_ps.fio1_ever_high()


def test_voltage_ramp_stablehold_rampdown(mock_ps):
    """[VoltageRamp, StableHold, VoltageRamp] -- hold then ramp-down without PID."""
    blocks = [
        VoltageRampBlock(start_voltage=0.0, end_voltage=2.0, duration_sec=1),
        StableHoldBlock(target_temp_k=300.0, tolerance_k=50.0, hold_duration_sec=0.1),
        VoltageRampBlock(start_voltage=2.0, end_voltage=0.0, duration_sec=1),
    ]
    with fast_executor_time():
        provider = lambda tc_name: (lambda: 300.0)
        ex = ProgramExecutor(mock_ps, provider)
        completed, starts, completes = run_program(ex, blocks)

    assert completed.is_set()
    assert starts == [0, 1, 2]
    assert completes == [0, 1, 2]
    assert not mock_ps.fio1_ever_high()


def test_tempramp_stablehold_rampdown(mock_ps):
    """[TempRamp, StableHold, VoltageRamp] -- hold after PID."""
    blocks = [
        TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1"),
        StableHoldBlock(target_temp_k=600.0, tolerance_k=50.0, hold_duration_sec=0.1),
        VoltageRampBlock(start_voltage=2.0, end_voltage=0.0, duration_sec=1),
    ]
    with fast_executor_time():
        provider = lambda tc_name: (lambda: 600.0)
        ex = ProgramExecutor(mock_ps, provider)
        completed, starts, completes = run_program(ex, blocks)

    assert completed.is_set()
    assert starts == [0, 1, 2]
    assert completes == [0, 1, 2]
    assert not mock_ps.fio1_ever_high()


# ── Parametrized 3-block permutations ─────────────────────────────────────────

BLOCK_TYPES = ['V', 'H', 'T']  # Voltage ramp, Hold, TempRamp


def make_block(code, temp_k=300.0):
    if code == 'V':
        return VoltageRampBlock(start_voltage=0.0, end_voltage=2.0, duration_sec=1)
    elif code == 'H':
        return StableHoldBlock(target_temp_k=temp_k, tolerance_k=50.0, hold_duration_sec=0.1)
    else:  # 'T'
        return TempRampBlock(rate_k_per_min=600.0, end_temp_k=600.0, tc_name="TC_1")


# ── Between-block power-continuity regression ─────────────────────────────────

def test_no_power_dropout_between_blocks(mock_ps):
    """
    BUG REGRESSION: the power supply must NOT switch off between blocks.

    Two back-to-back closed-loop blocks with the measured temperature held far
    below setpoint, so the PID commands a substantial positive voltage the whole
    time. Previously each block boundary hard-reset the PID, and because
    compute() returns 0.0 on its first call the DAC dropped to ~0 V for a tick or
    more — the supply visibly turned off and back on. The bumpless transfer must
    keep the commanded voltage continuous across the boundary.
    """
    ticks = []  # (block_index, voltage_v)

    def on_status(s):
        ticks.append((s['block_index'], s['voltage_v']))

    blocks = [
        TempRampBlock(rate_k_per_min=6000.0, end_temp_k=500.0, tc_name="TC_1"),
        TempRampBlock(rate_k_per_min=6000.0, end_temp_k=900.0, tc_name="TC_1"),
    ]
    with fast_executor_time():
        # Temp fixed well below setpoint => persistent positive error => PID
        # holds a high output on both blocks.
        provider = lambda tc_name: (lambda: 300.0)
        ex = ProgramExecutor(mock_ps, provider, on_status=on_status)
        run_program(ex, blocks)

    b0 = [v for (bi, v) in ticks if bi == 0]
    b1 = [v for (bi, v) in ticks if bi == 1]
    assert b0, "block 0 produced no status ticks"
    assert b1, "block 1 produced no status ticks"

    end_b0 = b0[-1]
    assert end_b0 > 0.5, f"precondition: block 0 should command >0.5 V, got {end_b0:.3f}"

    # The first few ticks of block 1 must not collapse toward 0 V.
    first_b1_min = min(b1[:3])
    assert first_b1_min > end_b0 * 0.5, (
        f"power dropped at block boundary: block 0 ended at {end_b0:.3f} V but "
        f"block 1 started at {b1[:3]} V (min {first_b1_min:.3f} V)"
    )


@pytest.mark.parametrize("a,b,c", [
    (a, b, c)
    for a in BLOCK_TYPES
    for b in BLOCK_TYPES
    for c in BLOCK_TYPES
])
def test_three_block_all_permutations(mock_ps, a, b, c):
    """All 27 3-block permutations: on_complete fires after block 3, not block 2."""
    mock_ps.reset()
    # Use 600K as temp to satisfy StableHold if it follows TempRamp
    temp_k = 600.0 if 'T' in [a, b, c] else 300.0
    blocks = [make_block(a, temp_k), make_block(b, temp_k), make_block(c, temp_k)]

    complete_count = [0]

    with fast_executor_time():
        provider = lambda tc_name: (lambda: temp_k)
        ex = ProgramExecutor(mock_ps, provider,
                             on_program_complete=lambda: complete_count.__setitem__(0, complete_count[0] + 1))
        ex.load_program(blocks)
        done = threading.Event()
        ex._on_program_complete = lambda: (done.set(), complete_count.__setitem__(0, complete_count[0] + 1))
        ex.start()
        done.wait(timeout=WALL_TIMEOUT)
        if ex.is_running():
            ex.stop()

    assert done.is_set(), f"[{a},{b},{c}] on_program_complete never fired"
    assert complete_count[0] == 1, f"[{a},{b},{c}] on_program_complete fired {complete_count[0]} times, expected 1"
    assert not mock_ps.fio1_ever_high(), f"[{a},{b},{c}] FIO1 was asserted HIGH"
