# 09: Extract block steps (prefactor)

**What to build:** The control math inside `_execute_block` is pulled out into pure block-step functions — one per block type — that take a temperature and elapsed time and return a voltage request. `ProgramExecutor` calls them, and ticket 01's recorded voltages stay identical. This makes the move onto the Rig loop (ticket 10) a re-wiring, not a rewrite.

**Blocked by:** 01

**Status:** ready-for-agent

**Read** `.scratch/rig-architecture/spec.md` (Block steps and the Program run) and `CONTEXT.md` (Block step) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `step_voltage_ramp`, `step_temp_ramp`, `step_stable_hold` with the signature and `StepResult` the spec gives. `c_to_k` lives beside them as the single °C→K conversion point.
- A step performs no I/O, reads no clock, does not `print`, does not sleep, and never catches its own exceptions.
- PID, feedforward and scheduler values (`Sched_*`, `FF_Voltage`, `PID_Correction`) are produced by the step exactly as today. **Do not change gains, feedforward, gain scheduling or the itinerary** (spec: Out of Scope).
- `ProgramExecutor._execute_block` keeps its loop, sleeps, current guard, writes and logging, and delegates the per-tick math to the step. The practice-mode demo voltage and thermal lag stay in the executor for now (removed in 10/13).
- Ticket 01's characterisation tests pass **unchanged**. If one fails, the extraction is wrong — fix the extraction; do not touch the literals (ADR 0001).

- [ ] Direct tests for each step fed explicit (temp, elapsed) series, no clock
- [ ] A test that a step raising propagates (no swallowing)
- [ ] Ticket 01's tests pass without edits
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
