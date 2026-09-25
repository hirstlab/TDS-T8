# 14: Retire the old modules

**What to build:** The old shared-everything code is deleted. `DataAcquisition` and `ProgramExecutor` are gone, the tests that exercised them now exercise the Rig on the Simulated rig, and a rule test proves nothing under the control, record or rig code sleeps except through the Clock.

**Blocked by:** 13

**Status:** in-progress

**Read** `AGENTS.md` §12, `.scratch/rig-architecture/spec.md` (Package layout — Retired; Testing Decisions §1 and §4) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Delete `core/data_acquisition.py` (and its dead `temp_ramp_executor` references) and `control/program_executor.py`.
- Ticket 01's original characterisation tests are deleted **only after** their assertions have been re-pointed at `ProgramRun` (done in 10/11) and those re-pointed tests pass. State in the PR which re-pointed test covers each deleted one.
- `tests/integration/test_block_transitions.py`, `test_state_invariants.py` and `tests/fault_injection/test_fault_recovery.py`: every case that still applies is rewritten on the Rig + Simulated rig fixture; cases for removed behaviour are deleted with the reason listed in the PR. No assertion is weakened (ADR 0001). `fast_executor_time` and `tests/mock_ps.py` go when nothing uses them.
- Remove every transitional exception listed in `test_architecture_rules.py` by earlier tickets; the import and heater-write rules now hold with no exceptions.
- Add the rule: the only `time.sleep` under `control/`, `data/run_record.py` and `rig/` is inside `RealClock.sleep_until`.
- Update `AGENTS.md` sections 5.1, 5.3 and 5.5 that describe the removed modules (only what this change makes false; §12.1 rule).

- [ ] `DataAcquisition`, `ProgramExecutor` no longer exist; nothing imports them
- [ ] Architecture rules have no transitional exceptions left
- [ ] No-sleep rule passes
- [ ] Every deleted test is accounted for in the PR (moved, or removed with its behaviour)
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
