# 11: Run record writes the CSV

**What to build:** CSV logging is driven by Snapshots on its own writer thread. The file has exactly the columns and order today's logs have, plus `Heater_State` and `Trip_Reason` at the end, and an event row for every trip, reset, block start and program end. The feedforward map reads a new log the same way it reads old ones.

**Blocked by:** 01, 10

**Status:** ready-for-agent

**Read** `.scratch/rig-architecture/spec.md` (Run record) and `CONTEXT.md` (Display unit) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `RunRecord` wraps the existing `DataLogger` (header metadata and flushing stay there) and owns a writer thread fed by a queue of Snapshots and events. It is the Rig's step-7 consumer.
- Pure `build_row(snapshot, t_unit, p_unit) -> dict`. Display-unit conversion happens here and only here for the file. `Block_Index` is computed in one place.
- A row is written every `sample_rate_ms`, not every tick.
- Header = ticket 01's pinned header for the same configuration, then `Heater_State`, `Trip_Reason`. Re-point ticket 01's header test at `RunRecord`.
- Event rows via `DataLogger.log_event`: `TRIP <kind>` (detail = reason), `RESET`, `RESET_REFUSED`, `BLOCK_START <n> <type>`, `PROGRAM_COMPLETE`, `PROGRAM_STOPPED`, `RAMP_START`, `ADAPTER <t8|simulated>`.
- The CSV-building closure in `main_window.py` is removed; `MainWindow` starts/stops the `RunRecord`.
- Writer thread shutdown flushes everything queued; it is tested with a `ManualClock` and joined, never slept on.

- [ ] `build_row` produces the exact header and a known row for a known Snapshot
- [ ] Ticket 01's header literal matches `RunRecord`'s header minus the two appended columns
- [ ] Round trip: `FeedforwardMap` ingests a CSV written by `RunRecord` with its existing column resolution unchanged
- [ ] On the integration fixture, a three-block run writes one row per `sample_rate_ms` and the expected event rows; a trip writes `TRIP <kind>` and `Trip_Reason` on subsequent rows
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
