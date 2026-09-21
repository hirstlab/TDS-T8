# 01: Pin today's control and CSV behaviour

**What to build:** Characterisation tests that record exactly what today's code does, so every later ticket can prove the refactor changed nothing. For `voltage_ramp`, `temp_ramp` and `stable_hold`, today's `ProgramExecutor` (non-practice path, fake power supply, patched clock, scripted control-TC temperature sequence) writes a known voltage every tick. The recorded sequences also cover a block boundary (bumpless transfer) and the FIX-2 two-second completion guard window. A second test records the CSV header today's logging path produces for a representative configuration (TCs with `_rawV` columns, FRG-702 gauges, PS columns, `Block_Index`, the six scheduler columns).

**Blocked by:** None (can start immediately)

**Status:** done

**Read** `.scratch/rig-architecture/spec.md` (Testing Decisions §1) and `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md` **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Tests only. No application code changes, except the optional header extraction below.
- Expected voltage sequences and the header are stored **as literals in the test file**, generated once from today's code and then pasted in. A test that recomputes its expectation from the code under test is not a characterisation test.
- Drive time with the existing `fast_executor_time` pattern in `tests/mock_ps.py` or an equivalent patch of the executor module's clock. No real sleeping.
- The header test builds the header through the same code path `MainWindow` uses when logging starts. If that path cannot be reached without a Tk root, extract the header-building into a pure function in the same module **as the only application change**, and pin that function; say so in the PR.
- These tests are the only tests in the effort allowed to reference `ProgramExecutor` (the spec says so). Name the file so ticket 14 can find it: `test_characterisation_*.py`.

- [x] One test per block type pins the per-tick voltage sequence to 1e-9 V
- [x] One test pins a two-block sequence across the boundary and the FIX-2 window
- [x] One test pins the CSV header (names and order) for a representative configuration
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

2026-09-21:
- Extracted pure function `build_csv_header(config, has_ps_controller=True)` in `t8_daq_system/gui/main_window.py` as permitted by the ticket spec, and wired `MainWindow._on_start_stop_logging` to use it.
- Created `tests/integration/test_characterisation_control_and_csv.py` with 5 characterisation tests:
  - `test_characterisation_voltage_ramp`: pins per-tick voltage sequence for `voltage_ramp` to 1e-9 V.
  - `test_characterisation_temp_ramp`: pins per-tick voltage sequence for `temp_ramp` with PID + feedforward to 1e-9 V.
  - `test_characterisation_stable_hold`: pins per-tick voltage sequence for `stable_hold` with PID and tolerance/hold window to 1e-9 V.
  - `test_characterisation_two_block_boundary_and_fix2`: pins a 2-block transition (`VoltageRampBlock` -> `TempRampBlock` cooldown) exercising bumpless PID transfer across the boundary and suppression of completion during the 2.0s FIX-2 window to 1e-9 V.
  - `test_characterisation_csv_header`: pins exact column names and ordering for representative config (TCs with `_rawV`, FRG gauge, PS columns, `Block_Index`, and 6 scheduler columns) both via `build_csv_header` and through disk writing via `DataLogger.start_logging`.
- Verified test-first: watched test fail when `build_csv_header` was missing, and verified test fails when assertions are broken.
- Full local gate passed: ruff clean, check_tests_first clean, pytest 259/259 passed.
