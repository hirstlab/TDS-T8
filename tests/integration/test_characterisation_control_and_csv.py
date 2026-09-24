"""
tests/integration/test_characterisation_control_and_csv.py

Characterisation tests pinning today's ProgramExecutor control behavior and CSV header
for the rig-architecture refactor (ADR 0002 / ticket rig-architecture-01).

WHY THIS EXISTS
---------------
Pins exact per-tick voltage sequences (to 1e-9 V) and CSV header schema as literals,
derived from today's ProgramExecutor and MainWindow logging path.
This file is the only test file in rig-architecture allowed to reference ProgramExecutor,
and will be retired together with it in ticket 14 once all assertions are proven against
the new Rig and ProgramRun architecture.
"""

import math
import threading
import pytest
from tests.mock_ps import MockPowerSupplyController, fast_executor_time
from t8_daq_system.control.program_block import (
    VoltageRampBlock,
    TempRampBlock,
    StableHoldBlock,
)
from t8_daq_system.control.program_executor import ProgramExecutor
from t8_daq_system.gui.main_window import build_csv_header
from t8_daq_system.data.data_logger import DataLogger
from t8_daq_system.data.run_record import build_header as rr_build_header

pytestmark = pytest.mark.integration

WALL_TIMEOUT = 10.0


def _run_blocks(blocks, temp_fn):
    """Run blocks under fast_executor_time and return the recorded voltage history."""
    ps = MockPowerSupplyController()
    completed = threading.Event()
    ex = ProgramExecutor(
        ps,
        lambda tc_name: temp_fn,
        on_program_complete=completed.set,
    )
    with fast_executor_time(0.5):
        ex.load_program(blocks)
        ex.start()
        completed.wait(timeout=WALL_TIMEOUT)
        if ex.is_running():
            ex.stop()
    return ps._voltage_history


def test_characterisation_voltage_ramp():
    """
    Pins the per-tick voltage sequence for VoltageRampBlock to 1e-9 V.
    Ramp 0.0 V -> 3.0 V over 3.0 s in 0.5 s ticks.
    """
    block = VoltageRampBlock(start_voltage=0.0, end_voltage=3.0, duration_sec=3.0)
    history = _run_blocks([block], lambda: 300.0)

    expected = [
        0.500000000,
        1.000000000,
        1.500000000,
        2.000000000,
        2.500000000,
    ]

    assert len(history) == len(expected)
    for actual, exp in zip(history, expected):
        assert math.isclose(actual, exp, abs_tol=1e-9)


def test_characterisation_temp_ramp():
    """
    Pins the per-tick voltage sequence for TempRampBlock to 1e-9 V.
    Ramp 60 K/min to 303 K starting at 300 K with constant 300 K feedback.
    """
    block = TempRampBlock(rate_k_per_min=60.0, end_temp_k=303.0, tc_name="TC_1")
    history = _run_blocks([block], lambda: 300.0)

    expected = [
        0.300325000,
        0.310975000,
        0.321950000,
        0.333250000,
        0.344875000,
    ]

    assert len(history) == len(expected)
    for actual, exp in zip(history, expected):
        assert math.isclose(actual, exp, abs_tol=1e-9)


def test_characterisation_stable_hold():
    """
    Pins the per-tick voltage sequence for StableHoldBlock to 1e-9 V.
    Hold at 320 K (tol 1.0 K, hold 1.0 s) with a scripted temperature sequence.
    """
    readings = [317.0, 317.0, 317.0, 318.0, 319.0, 319.5, 320.0, 320.0, 320.0]
    idx = [0]

    def scripted_temp():
        val = readings[min(idx[0], len(readings) - 1)]
        idx[0] += 1
        return val

    block = StableHoldBlock(target_temp_k=320.0, tolerance_k=1.0, hold_duration_sec=1.0)
    history = _run_blocks([block], scripted_temp)

    expected = [
        0.041300000000,
        0.016950000000,
        0.008941666667,
    ]

    assert len(history) == len(expected)
    for actual, exp in zip(history, expected):
        assert math.isclose(actual, exp, abs_tol=1e-9)


def test_characterisation_two_block_boundary_and_fix2():
    """
    Pins a two-block sequence across the boundary and the FIX-2 window to 1e-9 V.
    Block 0: VoltageRamp 0 -> 1 V over 1.0 s
    Block 1: TempRamp cooldown -60 K/min to 300 K starting at 300 K.
    Exercises bumpless transfer across boundary and the 2.0s FIX-2 window.
    """
    b0 = VoltageRampBlock(start_voltage=0.0, end_voltage=1.0, duration_sec=1.0)
    b1 = TempRampBlock(rate_k_per_min=-60.0, end_temp_k=300.0, tc_name="TC_1")

    history = _run_blocks([b0, b1], lambda: 300.0)

    # Tick 1: Block 0 at 0.5s -> 0.5V
    # Boundary: bumpless transfer seeds PID with 1.0V setpoint
    # Block 1: ticks at 0.5s, 1.0s, 1.5s are protected by FIX-2 (1.29V), finishes at 2.0s
    expected = [
        0.500000000,
        1.290000000,
        1.290000000,
        1.290000000,
    ]

    assert len(history) == len(expected)
    for actual, exp in zip(history, expected):
        assert math.isclose(actual, exp, abs_tol=1e-9)


def test_characterisation_csv_header(tmp_path):
    """
    Pins the CSV header (names and exact order) for a representative configuration.

    Re-pointed at RunRecord.build_header (ticket 11): the canonical schema now
    includes Heater_State and Trip_Reason appended at the end.  The first N-2
    sensor columns are identical to the ticket-01 pinned header.
    """
    tc_names = ["TC_1", "TC_2"]
    gauge_names = ["FRG702_Chamber"]

    # Ticket-01 pinned sensor list (all columns before the two new tail columns)
    ticket01_sensors = [
        "TC_1",
        "TC_2",
        "FRG702_Chamber",
        "PS_Voltage",
        "PS_Current",
        "PS_Voltage_Setpoint",
        "PS_CC_Limit",
        "Block_Index",
        "Sched_Kp",
        "Sched_Ki",
        "Sched_Kd",
        "Sched_Zone",
        "FF_Voltage",
        "PID_Correction",
        "TC_1_rawV",
        "TC_2_rawV",
    ]

    # RunRecord schema = ticket-01 schema + two new tail columns
    rr_sensors = rr_build_header(tc_names, gauge_names, has_ps=True)
    assert rr_sensors[:-2] == ticket01_sensors
    assert rr_sensors[-2] == "Heater_State"
    assert rr_sensors[-1] == "Trip_Reason"

    expected_header = ["Timestamp"] + rr_sensors

    # build_csv_header must delegate to RunRecord and return the same full header
    config = {
        "thermocouples": [
            {"name": "TC_1", "channel": 0, "type": "K", "units": "C", "enabled": True},
            {"name": "TC_2", "channel": 2, "type": "K", "units": "C", "enabled": True},
        ],
        "frg702_gauges": [
            {
                "name": "FRG702_Chamber",
                "sensor_code": "T1",
                "pin": "AIN4",
                "units": "Torr",
                "enabled": True,
            },
        ],
    }
    header = build_csv_header(config, has_ps_controller=True)
    assert header == expected_header

    # File output through DataLogger must match as well
    sensor_names = header[1:]
    logger = DataLogger(log_folder=str(tmp_path))
    filepath = logger.start_logging(sensor_names)
    logger.stop_logging()

    with open(filepath, "r", encoding="utf-8") as f:
        data_lines = [line.strip() for line in f if not line.startswith("#")]

    written_header = data_lines[0].split(",")
    assert written_header == expected_header
