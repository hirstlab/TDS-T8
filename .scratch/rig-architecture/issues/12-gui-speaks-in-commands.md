# 12: GUI speaks in commands

**What to build:** The operator's controls all go through the Rig. A trip shows a non-modal banner with its kind and reason and a Reset button until reset succeeds. The QMS start button is gated by the pressure permissive. Start, stop, confirm, nudge and reset submit commands. The practice toggle is disabled while a program runs or logging is on.

**Blocked by:** 10, 11

**Status:** done

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md`, `docs/adr/0005-practice-mode-is-a-rig-adapter.md` and `.scratch/rig-architecture/spec.md` (GUI) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Trip banner: non-modal, shows `heater.trip_kind` and reason, plus Reset; stays until a Snapshot shows the latch cleared. A refused reset shows its refusal reason. `shutoff_unverified` is shown as the most severe state.
- `messagebox` is never called from any thread but Tk's.
- QMS start asks `snapshot.permissive_ok` (showing `permissive_reason` when false). `_poll_qms_gate`'s own pressure check is removed. On a `pressure_high`/`pressure_stale` trip the Tk thread runs the existing MASsoft abort after the heater is already off; a failed abort is shown, not swallowed.
- `_nudge_voltage` and every start/stop/confirm/set-voltage/output control submit commands; none calls the power supply.
- Practice toggle submits `SelectAdapter`; it is disabled while `snapshot.program.running` or logging is active.
- Tests drive the GUI with Snapshots and assert on what is rendered and which commands were submitted — not on private attributes.

- [x] Rendering a tripped Snapshot shows the banner with kind and reason; a cleared one hides it
- [x] Reset button submits `ResetTrip`; a refused-reset Snapshot shows the refusal
- [x] QMS start is refused with the permissive reason when `permissive_ok` is false
- [x] Nudge/start/stop/confirm submit the matching commands and make no PS call
- [x] Practice toggle disabled while running or logging
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

- 2026-09-24: Ticket 12 implemented and verified.
  - Added non-modal trip banner (`_trip_banner_frame`, `_trip_label`, `_trip_refusal_label`, `_trip_reset_btn`) rendered directly from `Snapshot.heater`.
  - Trips remain visible until snapshot shows latch cleared (`heater.state != "tripped"`).
  - Refused reset displays command rejection reason from snapshot. `shutoff_unverified` displays prominent critical warning.
  - Reset button submits `ResetTrip` command to Rig.
  - All operator controls (`_nudge_voltage`, `_start_programmer_ramp`, `_stop_programmer_ramp_safe`, `_cut_power_output`, `_on_qms_confirmation_click`, `_on_ramp_start`, `set_voltage`, `set_output`) submit typed commands to Rig without direct power supply calls.
  - QMS start is gated strictly by `snapshot.permissive_ok` (with `permissive_reason` surfaced on rejection); removed raw pressure polling from `_poll_qms_gate`.
  - On `pressure_high` or `pressure_stale` trip, MASsoft abort is marshalled to Tk thread after verifying heater cutoff; abort failures surface error rather than being swallowed.
  - Practice toggle submits `SelectAdapter` and is disabled while program is running or logging is active.
  - All 19 unit tests in `tests/unit/test_gui_speaks_in_commands.py` pass; full test suite (418 passed) and all local CI gates pass.
