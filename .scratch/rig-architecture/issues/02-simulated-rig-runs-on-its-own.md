# 02: Simulated rig runs on its own

**What to build:** The building blocks the Rig module stands on, proven by a Simulated rig that behaves like tungsten. After this ticket a test can command a voltage on the Simulated rig, advance a manual clock, and read back current and temperature that follow the physics — with no thread, no Tk and no hardware.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `docs/adr/0005-practice-mode-is-a-rig-adapter.md` and `.scratch/rig-architecture/spec.md` (Package layout; Every number has one home; The Rig adapter seam; The Snapshot; The Simulated rig) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements (new package `t8_daq_system/rig/`, plus `t8_daq_system/settings/safety_limits.py`):

- `Clock` protocol with `now()`, `sleep_until(t)`, `wall_time()`; `RealClock`; `ManualClock` with `advance(seconds)` whose `sleep_until` returns immediately.
- `safety_limits.py` holds the eight named constants from the spec table, with the values and one-line reasons given there. Nothing reads them yet except what this ticket builds.
- Frozen dataclasses `Snapshot`, `SourceStatus`, `ProgramStatus`, `HeaterStatus` with the fields the spec lists. `RawReadings` and `AdapterError` as the adapter seam needs.
- `RigAdapter` protocol with **exactly** the operations the spec lists, no others.
- `TungstenSim` moves from `tests/simulation/tungsten_thermal_model.py` into the rig package; the test module re-imports it from there so existing tests keep passing unchanged.
- `SimulatedRig` implements `RigAdapter` as specified: voltage → current = V / R(T) → temperature, advanced to `clock.now()` on each `read()`; primary TC reports model temperature, other TCs room temperature; gauges report a configurable pressure in Torr (default 1e-7). Fault-injection methods: `drop_tc`, `restore_tc`, `set_pressure`, `stall_gauge`, `fail_next_write`, `disconnect`, `reconnect`.
- Nothing outside `rig/` and `settings/` changes. Nothing in the app uses these yet.

- [ ] For a fixed voltage, the Simulated rig settles to `TungstenSim.steady_state_temp` for that voltage (within the model's own tolerance)
- [ ] `set_output(False)` gives zero current and the specimen cools
- [ ] Each fault-injection method has a test showing its effect on `read()` / writes (dropped TC reads `None`, stalled gauge invalid, `fail_next_write` raises `AdapterError` once, `disconnect` makes `read()` raise)
- [ ] `ManualClock` tests: `advance` moves `now()` and `wall_time()`; `sleep_until` never blocks
- [ ] No test sleeps
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
