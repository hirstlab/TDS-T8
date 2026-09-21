# 03: Rig loop publishes Snapshots

**What to build:** A real `Rig` that owns one adapter and, each tick, reads every input and publishes an immutable Snapshot. Driven against the Simulated rig one tick at a time, a test can watch temperatures, pressures and per-source staleness appear in `rig.latest()`, pull the LabJack and see `labjack_lost`, and reconnect and see the supply forced off before anything else happens.

**Blocked by:** 02

**Status:** ready-for-agent

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `docs/adr/0003-heater-output-arbitration-and-trips.md` and `.scratch/rig-architecture/spec.md` (The Rig loop; The Snapshot) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `Rig.run_tick()` does one pass in the order the spec gives. This ticket implements steps 1 (drain the command queue), 2 (reconnect), 3 (read), 4 (staleness + publish) and 7 (hand the Snapshot to a consumer queue — any callable/queue for now; the Run record arrives in ticket 11). Steps 5 and 6 (safety, control step) are explicit no-op hooks that tickets 08 and 10 fill.
- The thread body is only `run_tick()` then `clock.sleep_until(next_tick)`. Tick period = `min(sample_rate_ms / 1000, CONTROL_PERIOD_S)`.
- Commands are frozen dataclasses on a `queue.Queue`. Define all of the spec's command types now; this ticket only acts on `SelectAdapter` (rejected, with a reason in the next Snapshot, while a Program runs or logging is active — "logging active" is a flag the caller sets) and `UpdateConfig`.
- On a failed `read()`: LabJack `SourceStatus` becomes `lost` and the Snapshot records a `labjack_lost` condition (the trip itself is wired in ticket 08; here it is a field the test can see).
- Reconnect at most every `RECONNECT_INTERVAL_S`. On success the first three adapter calls are `set_output(False)`, `write_voltage(0.0)`, `pin_current_limit()`, in that order, before any read is trusted.
- `Rig.latest()` is safe to call from another thread (lock around the single reference).
- Tests call `run_tick()` directly with a `ManualClock`. No test starts the thread.

- [ ] A tick against the Simulated rig publishes a Snapshot with TC °C, pressure in Torr, PS V/I, and `source_age_s` for every source
- [ ] A dropped TC's age grows tick by tick; restoring it resets to 0
- [ ] `disconnect()` → Snapshot shows LabJack `lost`; `reconnect()` + enough clock → the adapter's first three calls are exactly off, 0 V, pin current limit
- [ ] Reconnect is not attempted more often than `RECONNECT_INTERVAL_S`
- [ ] `SelectAdapter` is refused with a reason while logging is flagged active, and accepted when idle
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
