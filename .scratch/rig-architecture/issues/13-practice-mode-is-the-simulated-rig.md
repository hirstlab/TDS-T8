# 13: Practice mode is the Simulated rig

**What to build:** Practice mode is nothing but the Rig running the Simulated rig adapter. The real PID, feedforward, safety, Heater output and Run record run in practice exactly as on hardware. Every `practice_mode` branch outside the Rig's adapter choice is gone, and a rule test keeps it that way.

**Blocked by:** 12

**Status:** done

**Read** `docs/adr/0005-practice-mode-is-a-rig-adapter.md`, `AGENTS.md` §12.1 item 4 and `.scratch/rig-architecture/spec.md` (The Simulated rig) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Delete `MockPowerSupplyController` from `gui/main_window.py` and every `practice_mode` branch in `main_window.py`, `core/data_acquisition.py` and `control/` (≈33 references today). The toggle handler in `main_window.py` submitting `SelectAdapter` is the only survivor outside `rig/`.
- The simulated TC temperature applies to the primary control TC only; other TCs read room temperature (AGENTS.md practice-mode faithfulness rule).
- `ADAPTER simulated` / `ADAPTER t8` event rows are written when the adapter changes.
- Add to `test_architecture_rules.py`: the identifier `practice_mode` appears only under `rig/` and in `gui/main_window.py`'s toggle handler.
- Tests that used `MockPowerSupplyController` from `main_window.py` move to the Simulated rig; `tests/mock_ps.py` stays only for whatever ticket 14 still needs.

- [x] Practice run on the integration fixture uses the same `ProgramRun`/`HeaterOutput`/evaluator objects as the T8 path (asserted by behaviour: a trip in practice cuts output exactly as on T8)
- [x] `practice_mode` rule test passes
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### Landed 2026-09-24
- Deleted `MockPowerSupplyController` from `t8_daq_system/gui/main_window.py`.
- Removed all `practice_mode` branches from `t8_daq_system/control/program_executor.py`, `t8_daq_system/core/data_acquisition.py`, and `t8_daq_system/gui/main_window.py`. The only remaining occurrence of `practice_mode` outside `rig/` is in `MainWindow._toggle_practice_mode`.
- Added AST rule test `test_practice_mode_identifier_only_under_rig_and_gui_toggle` in `tests/unit/test_architecture_rules.py`.
- Added `ADAPTER <adapter>` event emission in `Rig.set_run_record()` and when handling `SelectAdapter` in `Rig._handle_command()`.
- Added integration test suite `tests/integration/test_practice_mode_simulated_rig.py` covering:
  - Practice run uses the exact same `ProgramRun`, `HeaterOutput`, and `SafetyEvaluator` pipeline as hardware path, cutting output immediately on trip.
  - Non-primary TCs remain at room temperature in `SimulatedRig` while primary TC heats realistically via `TungstenSim`.
  - Switching adapters records `ADAPTER simulated` and `ADAPTER t8` event rows in RunRecord CSV.
- Updated `AGENTS.md` Section 5.5 per ADR 0005.
- Bench verification needed: practice-mode smoke run with operator UI on lab PC.
