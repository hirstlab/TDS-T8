# 10: Program run on the Rig loop

**What to build:** Programs run inside the Rig's control step. `ProgramRun` advances blocks every 0.5 s using the block steps, and its voltage request goes through the Heater output like every other request. A full multi-hour three-block program runs in a test in seconds on the Simulated rig, and a lost control TC, a raising block step, or an operator nudge each do exactly what ADR 0003 says.

**Blocked by:** 05, 08, 09

**Status:** ready-for-agent

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `docs/adr/0003-heater-output-arbitration-and-trips.md` and `.scratch/rig-architecture/spec.md` (The Rig loop step 6; Block steps and the Program run; Testing Decisions §1–§2) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `ProgramRun` owns what the spec lists: block list and index, block-start time and temperature, per-block gain resolution (today's `_resolve_block_control`), bumpless transfer via `PIDController.reset_bumpless`, the FIX-2 two-second completion guard, `_save_run_to_history`, and the QMS confirmation pause released by `ConfirmContinue`.
- `ProgramRun.step(snapshot, now_s)` is called by the Rig on control steps (≥ `CONTROL_PERIOD_S` since the last). Its request goes to `HeaterOutput`; the Rig writes the result.
- A block step that raises → `program_error` trip with exception type and message as the reason; the run ends.
- `LoadProgram`, `StartProgram`, `StopProgram`, `ConfirmContinue` commands drive it. An Operator request while running stops the run first (rule 4).
- The GUI starts/stops programs through these commands. `ProgramExecutor` is no longer used by the app (file deleted in 14). The practice-mode demo voltage and in-executor thermal lag are **not** carried over.
- `Snapshot.program` is filled (running, block index/type, waiting-for-confirmation, elapsed, setpoint K, scheduler values).
- Re-point ticket 01's per-tick voltage assertions at `ProgramRun` + block steps (same literals, same 1e-9 V tolerance) in a new test; keep the originals until 14.
- Add to `test_architecture_rules.py`: calls named `write_voltage`, `set_output`, `set_voltage`, `output_on`, `output_off`, `emergency_shutdown` appear only under `rig/` and `hardware/` (list any remaining transitional callers explicitly with the ticket that removes them).

- [ ] Three-block program (voltage ramp → temp ramp → stable hold) completes in simulated hours on the integration fixture
- [ ] `drop_tc` on the control TC mid-ramp: no trip at 4.9 s, `control_tc_stale` at 5.1 s; off + 0 V that tick; run ended; reason in Snapshot
- [ ] A raising block step → `program_error` trip carrying the exception text
- [ ] Nudge during a run → run stopped, operator voltage applied; nudge with output disabled → output stays disabled
- [ ] Ticket 01's voltage literals reproduce through `ProgramRun` to 1e-9 V
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
