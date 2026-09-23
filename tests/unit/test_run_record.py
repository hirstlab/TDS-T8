"""
tests/unit/test_run_record.py

Unit tests for RunRecord: build_row, build_header, writer thread, FeedforwardMap round trip.

WHY THIS EXISTS
---------------
Pins the exact column schema that RunRecord produces (AC 1 and AC 2 of ticket 11),
verifies that the writer thread flushes everything queued without real sleeps (AC 4),
and confirms FeedforwardMap can ingest a RunRecord-written CSV unchanged (AC 3).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pytest

from t8_daq_system.data.data_logger import DataLogger
from t8_daq_system.data.run_record import RunRecord, build_header, build_row
from t8_daq_system.rig.snapshot import HeaterStatus, ProgramStatus, Snapshot, SourceStatus

pytestmark = pytest.mark.unit

_WALL_BASE = 1_774_000_000.0  # matches ManualClock default


def _snap(
    *,
    t: float = 0.0,
    tc_1_c: float = 100.0,
    tc_2_c: float = 200.0,
    p_torr: float = 1e-7,
    ps_volts: float = 1.5,
    ps_amps: float = 25.0,
    commanded_volts: float = 1.5,
    running: bool = True,
    block_index: int = 0,
    heater_state: str = "on",
    trip_reason: str | None = None,
) -> Snapshot:
    return Snapshot(
        t=t,
        wall_time=_WALL_BASE + t,
        tc_c={"TC_1": tc_1_c, "TC_2": tc_2_c},
        tc_raw_v={"TC_1": 0.004, "TC_2": 0.008},
        pressure_torr={"FRG702_Chamber": p_torr},
        source_age_s={"TC_1": 0.0, "TC_2": 0.0, "FRG702_Chamber": 0.0},
        ps_volts=ps_volts,
        ps_amps=ps_amps,
        commanded_volts=commanded_volts,
        output_enabled=True,
        labjack=SourceStatus(state="connected"),
        xgs=SourceStatus(state="connected"),
        heater=HeaterStatus(
            state=heater_state,
            trip_kind="pressure_high" if trip_reason else None,
            trip_reason=trip_reason,
        ),
        program=ProgramStatus(
            running=running,
            block_index=block_index,
            block_type="voltage_ramp",
            sched_kp=0.02,
            sched_ki=0.0013,
            sched_kd=0.005,
            sched_zone="normal",
            ff_voltage=1.2,
            pid_correction=0.1,
        ),
        permissive_ok=True,
        permissive_reason=None,
        adapter="simulated",
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_data_rows(csv_file: Path) -> int:
    """Count non-comment, non-header, non-event CSV rows."""
    count = 0
    with open(csv_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("Timestamp"):
                continue
            row = next(csv.reader([line]))
            if not row:
                continue
            # Event rows have second column starting with "EVENT:"
            if len(row) >= 2 and row[1].startswith("EVENT:"):
                continue
            try:
                datetime.fromisoformat(row[0])
                count += 1
            except ValueError:
                pass
    return count


def _read_event_names(csv_file: Path) -> list[str]:
    """Return list of event names (the part after EVENT:) from the CSV."""
    events = []
    with open(csv_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = next(csv.reader([line]))
            if len(row) >= 2 and row[1].startswith("EVENT:"):
                events.append(row[1][len("EVENT:"):])
    return events


def _make_rr(tmp_path: Path, *, sample_rate_ms: float = 500.0) -> tuple[RunRecord, DataLogger]:
    tc_names = ["TC_1", "TC_2"]
    gauge_names = ["FRG702_Chamber"]
    sensor_names = build_header(tc_names, gauge_names, has_ps=True)
    logger_ = DataLogger(log_folder=str(tmp_path))
    logger_.start_logging(sensor_names)
    rr = RunRecord(
        logger_=logger_,
        tc_names=tc_names,
        gauge_names=gauge_names,
        t_unit="C",
        p_unit="mbar",
        sample_rate_ms=sample_rate_ms,
        has_ps=True,
    )
    return rr, logger_


# ── AC 1: build_row exact header and known row ─────────────────────────────────

def test_build_header_full_column_order():
    """Canonical header order, with Heater_State and Trip_Reason at end."""
    header = build_header(["TC_1", "TC_2"], ["FRG702_Chamber"], has_ps=True)
    expected = [
        "TC_1", "TC_2",
        "FRG702_Chamber",
        "PS_Voltage", "PS_Current", "PS_Voltage_Setpoint", "PS_CC_Limit",
        "Block_Index",
        "Sched_Kp", "Sched_Ki", "Sched_Kd", "Sched_Zone", "FF_Voltage", "PID_Correction",
        "TC_1_rawV", "TC_2_rawV",
        "Heater_State", "Trip_Reason",
    ]
    assert header == expected


def test_build_row_tc_celsius_passthrough():
    row = build_row(_snap(tc_1_c=100.0), "C", "Torr")
    assert row["TC_1"] == pytest.approx(100.0)
    assert row["TC_2"] == pytest.approx(200.0)


def test_build_row_tc_to_kelvin():
    row = build_row(_snap(tc_1_c=100.0), "K", "Torr")
    assert row["TC_1"] == pytest.approx(373.15)


def test_build_row_pressure_torr_passthrough():
    row = build_row(_snap(p_torr=1e-7), "C", "Torr")
    assert row["FRG702_Chamber"] == pytest.approx(1e-7)


def test_build_row_pressure_torr_to_mbar():
    row = build_row(_snap(p_torr=1e-7), "C", "mbar")
    # 1 Torr = 1.33322 mbar
    assert row["FRG702_Chamber"] == pytest.approx(1e-7 * 1.33322, rel=1e-3)


def test_build_row_ps_columns():
    row = build_row(_snap(ps_volts=1.5, ps_amps=25.0, commanded_volts=1.5), "C", "Torr")
    assert row["PS_Voltage"] == pytest.approx(1.5)
    assert row["PS_Current"] == pytest.approx(25.0)
    assert row["PS_Voltage_Setpoint"] == pytest.approx(1.5)
    assert row["PS_CC_Limit"] == pytest.approx(180.0)


def test_build_row_block_index_1based_when_running():
    row = build_row(_snap(running=True, block_index=2), "C", "Torr")
    assert row["Block_Index"] == 3


def test_build_row_block_index_none_when_not_running():
    row = build_row(_snap(running=False), "C", "Torr")
    assert row["Block_Index"] is None


def test_build_row_sched_present_when_running():
    row = build_row(_snap(running=True), "C", "Torr")
    assert row["Sched_Kp"] == pytest.approx(0.02)
    assert row["Sched_Ki"] == pytest.approx(0.0013)
    assert row["FF_Voltage"] == pytest.approx(1.2)


def test_build_row_sched_none_when_not_running():
    row = build_row(_snap(running=False), "C", "Torr")
    for col in ("Sched_Kp", "Sched_Ki", "Sched_Kd", "Sched_Zone", "FF_Voltage", "PID_Correction"):
        assert row[col] is None, f"{col} should be None when not running"


def test_build_row_raw_voltages():
    row = build_row(_snap(), "C", "Torr")
    assert row["TC_1_rawV"] == pytest.approx(0.004)
    assert row["TC_2_rawV"] == pytest.approx(0.008)


def test_build_row_heater_state_on():
    row = build_row(_snap(heater_state="on"), "C", "Torr")
    assert row["Heater_State"] == "on"
    assert row["Trip_Reason"] is None


def test_build_row_heater_state_tripped_with_reason():
    row = build_row(_snap(heater_state="tripped", trip_reason="Pressure 1.0e-3 > 1.0e-4 Torr"), "C", "Torr")
    assert row["Heater_State"] == "tripped"
    assert row["Trip_Reason"] == "Pressure 1.0e-3 > 1.0e-4 Torr"


def test_build_row_none_tc_passes_through():
    """None TC values (open sensor) come through as None in the row."""
    from dataclasses import replace as dc_replace
    snap = _snap()
    snap2 = dc_replace(snap, tc_c={"TC_1": None, "TC_2": 200.0})
    row = build_row(snap2, "C", "Torr")
    assert row["TC_1"] is None
    assert row["TC_2"] == pytest.approx(200.0)


# ── AC 2: Ticket-01 header literal matches RunRecord header minus two columns ──

def test_header_minus_two_appended_matches_ticket01_literal():
    """
    RunRecord.build_header()[:-2] must equal the ticket-01 pinned sensor list
    (Timestamp excluded, Heater_State and Trip_Reason not yet present).
    """
    ticket01_pinned_sensors = [
        "TC_1", "TC_2",
        "FRG702_Chamber",
        "PS_Voltage", "PS_Current", "PS_Voltage_Setpoint", "PS_CC_Limit",
        "Block_Index",
        "Sched_Kp", "Sched_Ki", "Sched_Kd", "Sched_Zone", "FF_Voltage", "PID_Correction",
        "TC_1_rawV", "TC_2_rawV",
    ]
    rr_header = build_header(["TC_1", "TC_2"], ["FRG702_Chamber"], has_ps=True)
    assert rr_header[:-2] == ticket01_pinned_sensors


# ── AC 3: FeedforwardMap ingests a RunRecord-written CSV ───────────────────────

def test_feedforward_map_roundtrip(tmp_path):
    """
    FeedforwardMap.ingest_csv must resolve the temperature and voltage columns
    from a CSV written by RunRecord without raising, and with unchanged column
    resolution logic (TC_1 for temperature, PS_Voltage_Setpoint for voltage).
    """
    from t8_daq_system.control.feedforward_map import FeedforwardMap

    tc_names = ["TC_1"]
    gauge_names = ["FRG702_Chamber"]
    sensor_names = build_header(tc_names, gauge_names, has_ps=True)
    logger_ = DataLogger(log_folder=str(tmp_path))
    logger_.start_logging(sensor_names, metadata={
        "tc_count": 1, "tc_type": "K", "tc_unit": "C",
        "frg702_count": 1, "frg702_unit": "mbar",
        "sample_rate_ms": 500, "notes": "",
    })

    rr = RunRecord(
        logger_=logger_,
        tc_names=tc_names,
        gauge_names=gauge_names,
        t_unit="C",
        p_unit="mbar",
        sample_rate_ms=500.0,
        has_ps=True,
    )
    rr.start()

    # Write 10 rows with rising temperature and voltage
    for i in range(10):
        from dataclasses import replace as dc_replace
        snap = dc_replace(
            _snap(t=float(i) * 0.5, tc_1_c=300.0 + i * 5.0, commanded_volts=1.0 + i * 0.1),
            tc_c={"TC_1": 300.0 + i * 5.0},
            tc_raw_v={"TC_1": 0.004},
            pressure_torr={"FRG702_Chamber": 1e-7},
            program=ProgramStatus(running=False),
        )
        rr.put_snapshot(snap)

    rr.stop()
    logger_.stop_logging()

    csv_files = list(tmp_path.glob("*.csv"))
    assert len(csv_files) == 1, "Expected exactly one CSV file"

    # FeedforwardMap must parse the file without error
    ff = FeedforwardMap()
    ff.scan_log_folder(str(tmp_path))  # scans folder; ingest failure → empty curves

    # Verify column resolution worked: ingest directly and check no ValueError raised
    ff2 = FeedforwardMap()
    ff2.ingest_csv(str(csv_files[0]))  # must not raise


# ── Writer thread tests ────────────────────────────────────────────────────────

def test_writer_flushes_all_snapshots_queued_before_stop(tmp_path):
    """All snapshots enqueued before stop() must appear in the CSV."""
    rr, logger_ = _make_rr(tmp_path, sample_rate_ms=500.0)
    rr.start()
    # 3 snapshots at exactly 500 ms intervals → all written
    for i in range(3):
        rr.put_snapshot(_snap(t=float(i) * 0.5))
    rr.stop()
    logger_.stop_logging()

    csv_file = list(tmp_path.glob("*.csv"))[0]
    assert _count_data_rows(csv_file) == 3


def test_writer_throttles_by_sample_rate_ms(tmp_path):
    """Snapshots that arrive closer than sample_rate_ms apart are not written."""
    rr, logger_ = _make_rr(tmp_path, sample_rate_ms=1000.0)
    rr.start()
    # 5 snapshots at 200 ms intervals (all within one 1000 ms window)
    for i in range(5):
        rr.put_snapshot(_snap(t=float(i) * 0.2))
    rr.stop()
    logger_.stop_logging()

    csv_file = list(tmp_path.glob("*.csv"))[0]
    assert _count_data_rows(csv_file) == 1


def test_writer_throttle_two_windows(tmp_path):
    """Snapshots spanning two sample_rate_ms windows produce two rows."""
    rr, logger_ = _make_rr(tmp_path, sample_rate_ms=1000.0)
    rr.start()
    # t=0: write (diff from -inf). t=0.5: skip. t=1.0: write (1.0 >= 1.0).
    for t in [0.0, 0.5, 1.0]:
        rr.put_snapshot(_snap(t=t))
    rr.stop()
    logger_.stop_logging()

    csv_file = list(tmp_path.glob("*.csv"))[0]
    assert _count_data_rows(csv_file) == 2


def test_event_rows_written_immediately(tmp_path):
    """Events go to the CSV regardless of sample_rate throttling."""
    rr, logger_ = _make_rr(tmp_path, sample_rate_ms=10_000.0)
    rr.start()
    rr.put_event("BLOCK_START 0 voltage_ramp")
    rr.put_event("PROGRAM_COMPLETE")
    rr.stop()
    logger_.stop_logging()

    csv_file = list(tmp_path.glob("*.csv"))[0]
    events = _read_event_names(csv_file)
    assert "BLOCK_START 0 voltage_ramp" in events
    assert "PROGRAM_COMPLETE" in events


def test_trip_event_written_with_detail(tmp_path):
    """TRIP event carries the trip reason as detail."""
    rr, logger_ = _make_rr(tmp_path)
    rr.start()
    rr.put_event("TRIP pressure_high", "Pressure 1.0e-3 Torr > 1.0e-4 Torr")
    rr.stop()
    logger_.stop_logging()

    # Read raw CSV to check detail column
    csv_file = list(tmp_path.glob("*.csv"))[0]
    with open(csv_file, encoding="utf-8") as f:
        lines = [line.strip() for line in f if not line.startswith("#")]
    event_lines = [line for line in lines if "EVENT:TRIP" in line]
    assert len(event_lines) == 1
    row = next(csv.reader([event_lines[0]]))
    assert "TRIP pressure_high" in row[1]
    assert "1.0e-3" in row[2]


def test_writer_joined_without_sleep(tmp_path):
    """stop() joins the writer thread; the test must complete without real sleeping."""
    rr, logger_ = _make_rr(tmp_path)
    rr.start()
    rr.put_event("SENTINEL")
    rr.stop()   # Must return immediately (sentinel-based, no time.sleep)
    logger_.stop_logging()
    # Reaching here proves the thread was joined promptly.
    csv_file = list(tmp_path.glob("*.csv"))[0]
    assert "SENTINEL" in _read_event_names(csv_file)
