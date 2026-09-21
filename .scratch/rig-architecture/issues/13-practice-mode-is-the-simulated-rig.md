# 13: Practice mode is the Simulated rig

**What to build:** Practice mode is nothing but the Rig running the Simulated rig adapter. The real PID, feedforward, safety, Heater output and Run record run in practice exactly as on hardware. Every `practice_mode` branch outside the Rig's adapter choice is gone, and a rule test keeps it that way.

**Blocked by:** 12

**Status:** ready-for-agent

**Read** `docs/adr/0005-practice-mode-is-a-rig-adapter.md`, `AGENTS.md` §12.1 item 4 and `.scratch/rig-architecture/spec.md` (The Simulated rig) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Delete `MockPowerSupplyController` from `gui/main_window.py` and every `practice_mode` branch in `main_window.py`, `core/data_acquisition.py` and `control/` (≈33 references today). The toggle handler in `main_window.py` submitting `SelectAdapter` is the only survivor outside `rig/`.
- The simulated TC temperature applies to the primary control TC only; other TCs read room temperature (AGENTS.md practice-mode faithfulness rule).
- `ADAPTER simulated` / `ADAPTER t8` event rows are written when the adapter changes.
- Add to `test_architecture_rules.py`: the identifier `practice_mode` appears only under `rig/` and in `gui/main_window.py`'s toggle handler.
- Tests that used `MockPowerSupplyController` from `main_window.py` move to the Simulated rig; `tests/mock_ps.py` stays only for whatever ticket 14 still needs.

- [ ] Practice run on the integration fixture uses the same `ProgramRun`/`HeaterOutput`/evaluator objects as the T8 path (asserted by behaviour: a trip in practice cuts output exactly as on T8)
- [ ] `practice_mode` rule test passes
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
