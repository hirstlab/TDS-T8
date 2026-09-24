# 12: GUI speaks in commands

**What to build:** The operator's controls all go through the Rig. A trip shows a non-modal banner with its kind and reason and a Reset button until reset succeeds. The QMS start button is gated by the pressure permissive. Start, stop, confirm, nudge and reset submit commands. The practice toggle is disabled while a program runs or logging is on.

**Blocked by:** 10, 11

**Status:** in-progress

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md`, `docs/adr/0005-practice-mode-is-a-rig-adapter.md` and `.scratch/rig-architecture/spec.md` (GUI) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Trip banner: non-modal, shows `heater.trip_kind` and reason, plus Reset; stays until a Snapshot shows the latch cleared. A refused reset shows its refusal reason. `shutoff_unverified` is shown as the most severe state.
- `messagebox` is never called from any thread but Tk's.
- QMS start asks `snapshot.permissive_ok` (showing `permissive_reason` when false). `_poll_qms_gate`'s own pressure check is removed. On a `pressure_high`/`pressure_stale` trip the Tk thread runs the existing MASsoft abort after the heater is already off; a failed abort is shown, not swallowed.
- `_nudge_voltage` and every start/stop/confirm/set-voltage/output control submit commands; none calls the power supply.
- Practice toggle submits `SelectAdapter`; it is disabled while `snapshot.program.running` or logging is active.
- Tests drive the GUI with Snapshots and assert on what is rendered and which commands were submitted — not on private attributes.

- [ ] Rendering a tripped Snapshot shows the banner with kind and reason; a cleared one hides it
- [ ] Reset button submits `ResetTrip`; a refused-reset Snapshot shows the refusal
- [ ] QMS start is refused with the permissive reason when `permissive_ok` is false
- [ ] Nudge/start/stop/confirm submit the matching commands and make no PS call
- [ ] Practice toggle disabled while running or logging
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
