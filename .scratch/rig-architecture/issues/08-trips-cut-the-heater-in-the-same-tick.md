# 08: Trips cut the heater in the same tick

**What to build:** The Rig loop evaluates safety and applies the Heater output every tick. Any trip cuts the heater on the tick it is detected, latches, and puts its reason in the Snapshot until a reset is accepted. The five-minute ramp-down is gone: every trip is an instant cutoff. A failed shut-off write is shown as the most severe state rather than lost.

**Blocked by:** 03, 06, 07

**Status:** done

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md` and `.scratch/rig-architecture/spec.md` (The Rig loop steps 5–6; The Heater output; Testing Decisions §2) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Fill the Rig's step 5 with the pure evaluator (ticket 06) and a trip-driven heater resolution (ticket 07) that is applied on **every** tick a trip appears, not only on control steps. A read failure raises `labjack_lost` here.
- `SetOutput`, `SetVoltage`, `Nudge` and `ResetTrip` commands now reach `HeaterOutput`. The adapter write goes through the Rig only.
- Write failure → trip of the matching kind (`labjack_lost` for link errors). A failed `set_output(False)` sets `HeaterStatus.shutoff_unverified = True`.
- The Snapshot's `heater` field shows `off`/`on`/`tripped`, kind, reason, `shutoff_unverified`; `permissive_ok`/`permissive_reason` come from the evaluator.
- Remove `SafetyMonitor._rampdown_loop`, `_trigger_controlled_rampdown`, `RAMPDOWN_DURATION_SEC`, the safety monitor's own thread and PS reference, and every GUI path that reads ramp-down progress. `_handle_safety_shutdown` and `_on_pressure_interlock` stop writing the supply; they only render what the Snapshot says. Delete ramp-down tests (including `test_regression_rampdown_after_hold`) in the same commit, and say which in the PR.
- The executor (still `ProgramExecutor`) is stopped via the Rig when a trip latches, in the same tick.
- Tests use the integration fixture from the spec: real `Rig` + `SimulatedRig` + `ManualClock` + real `HeaterOutput` + evaluator, driven by `tick(n)`.

- [x] `set_pressure` above threshold → `pressure_high` trip; the adapter receives `set_output(False)` and `write_voltage(0.0)` on that same tick
- [x] `stall_gauge` → no trip at 4.9 s, `pressure_stale` at 5.1 s
- [x] `disconnect` → `labjack_lost`; `reconnect` → first calls off / 0 V / pin; reset accepted afterwards, not before
- [x] `fail_next_write` on `set_output(False)` → `shutoff_unverified` in the Snapshot
- [x] Reset while the condition persists → refused with reason; after it clears → accepted
- [x] No reference to ramp-down remains in `t8_daq_system/`
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

- 2026-09-22: Implemented Rig step 5 safety evaluation and trip-driven heater resolution per ADR 0003 & 0004.
  - Rig runs `SafetyEvaluator` and commands `HeaterOutput` on every tick. Any trip immediately cuts the supply (`set_output(False)` and `write_voltage(0.0)`) and aborts running programs in the same tick.
  - Integrated command dispatching: `SetOutput`, `SetVoltage`, `Nudge`, `ResetTrip` route through `HeaterOutput` with hardware writes handled solely by `Rig`.
  - Added adapter write failure handling resulting in `labjack_lost` trips and `shutoff_unverified = True` on failed deassert writes.
  - Completely purged rampdown routines (`_rampdown_loop`, `_trigger_controlled_rampdown`, `RAMPDOWN_DURATION_SEC`, background thread, UI progress hooks) and deleted obsolete test `test_regression_rampdown_after_hold`.
  - Added full test suite in `tests/integration/test_rig_trips.py` verifying all trip conditions, timing thresholds, disconnect/reconnect workflows, unverified shutoffs, and reset semantics.
  - All 3 gates pass: `ruff check .` (0 errors), `python scripts/check_tests_first.py` (OK), `pytest --tb=short -q` (355 passed).
