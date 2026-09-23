# 11: Run record writes the CSV

**What to build:** CSV logging is driven by Snapshots on its own writer thread. The file has exactly the columns and order today's logs have, plus `Heater_State` and `Trip_Reason` at the end, and an event row for every trip, reset, block start and program end. The feedforward map reads a new log the same way it reads old ones.

**Blocked by:** 01, 10

**Status:** done

**Read** `.scratch/rig-architecture/spec.md` (Run record) and `CONTEXT.md` (Display unit) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `RunRecord` wraps the existing `DataLogger` (header metadata and flushing stay there) and owns a writer thread fed by a queue of Snapshots and events. It is the Rig's step-7 consumer.
- Pure `build_row(snapshot, t_unit, p_unit) -> dict`. Display-unit conversion happens here and only here for the file. `Block_Index` is computed in one place.
- A row is written every `sample_rate_ms`, not every tick.
- Header = ticket 01's pinned header for the same configuration, then `Heater_State`, `Trip_Reason`. Re-point ticket 01's header test at `RunRecord`.
- Event rows via `DataLogger.log_event`: `TRIP <kind>` (detail = reason), `RESET`, `RESET_REFUSED`, `BLOCK_START <n> <type>`, `PROGRAM_COMPLETE`, `PROGRAM_STOPPED`, `RAMP_START`, `ADAPTER <t8|simulated>`.
- The CSV-building closure in `main_window.py` is removed; `MainWindow` starts/stops the `RunRecord`.
- Writer thread shutdown flushes everything queued; it is tested with a `ManualClock` and joined, never slept on.

- [x] `build_row` produces the exact header and a known row for a known Snapshot
- [x] Ticket 01's header literal matches `RunRecord`'s header minus the two appended columns
- [x] Round trip: `FeedforwardMap` ingests a CSV written by `RunRecord` with its existing column resolution unchanged
- [x] On the integration fixture, a three-block run writes one row per `sample_rate_ms` and the expected event rows; a trip writes `TRIP <kind>` and `Trip_Reason` on subsequent rows
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

2026-09-22: Done.
- New `t8_daq_system/data/run_record.py`: pure `build_row(snapshot, t_unit, p_unit) -> dict`,
  pure `build_header(tc_names, gauge_names, has_ps) -> list[str]`, and `RunRecord` class with
  sentinel-based writer thread (no sleep, joins cleanly with `ManualClock`-driven tests).
- `DataLogger.log_reading` gained optional `timestamp` param (backward-compatible).
- `ProgramRun` accumulates `_pending_events`; `take_events()` drains them per tick so
  the Rig can relay `BLOCK_START`, `PROGRAM_COMPLETE`, `RAMP_START` to RunRecord.
- `Rig` gained `set_run_record`/`clear_run_record`, forwards Snapshots at step 7,
  and emits `TRIP`, `RESET`, `RESET_REFUSED`, `PROGRAM_STOPPED`, `ADAPTER` events.
- `build_csv_header` in `main_window.py` now delegates to `build_header` (canonical schema).
  The CSV-building closure was removed from `_on_snapshot`; `_on_toggle_logging` creates
  and starts a `RunRecord` wired to the Rig, stops and joins it on stop.
- Ticket-01 characterisation header test re-pointed at `RunRecord.build_header`.
- Tests: 22 unit tests in `test_run_record.py`, 2 integration tests in
  `test_run_record_integration.py`. All 399 suite tests pass. All three gates green.
