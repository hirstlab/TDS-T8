# 14: Retire the old modules

**What to build:** The old shared-everything code is deleted. `DataAcquisition` and `ProgramExecutor` are gone, the tests that exercised them now exercise the Rig on the Simulated rig, and a rule test proves nothing under the control, record or rig code sleeps except through the Clock.

**Blocked by:** 13

**Status:** done

- [x] `DataAcquisition`, `ProgramExecutor` no longer exist; nothing imports them
- [x] Architecture rules have no transitional exceptions left
- [x] No-sleep rule passes
- [x] Every deleted test is accounted for in the PR (moved, or removed with its behaviour)
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### Completed Implementation
1. **Old modules retired:**
   - Deleted `t8_daq_system/core/data_acquisition.py` and `t8_daq_system/control/program_executor.py`.
   - Verified no remaining references across the codebase.

2. **Test rewrite and mock cleanup:**
   - Rewrote `tests/integration/test_block_transitions.py` on `Rig` + `SimulatedRig` fixture (40 tests passing).
   - Rewrote `tests/integration/test_state_invariants.py` on `Rig` + `SimulatedRig` fixture (4 tests passing).
   - Rewrote `tests/fault_injection/test_fault_recovery.py` on `Rig` + `SimulatedRig` fixture (8 tests passing).
   - Deleted `tests/mock_ps.py` and removed unused `mock_ps`, `mock_temp_provider`, and `make_executor` fixtures from `tests/conftest.py`.

3. **Coverage accounting for deleted tests:**
   - `test_characterisation_control_and_csv.py` (Ticket 01):
     - `test_temp_ramp_execution`: covered by `tests/integration/test_program_run_rig.py` and `tests/integration/test_block_transitions.py`.
     - `test_block_transitions`: covered by `tests/integration/test_block_transitions.py` (all 27 combinations + 3-block permutations on `Rig` + `SimulatedRig`).
     - `test_csv_logging_matches_characterisation`: covered by `tests/integration/test_run_record_integration.py` (Ticket 11).
     - `test_safety_trips_halt_run`: covered by `tests/integration/test_rig_trips.py` (Ticket 08) and `tests/fault_injection/test_fault_recovery.py`.
   - `test_fault_recovery.py`:
     - `test_so_latched_executor_stops_gracefully` & `test_so_latched_dac_not_nonzero_after_fault`: re-pointed to hardware disconnect on Rig + SimulatedRig.
     - `test_ovp_trip_sets_interlock`: re-pointed to pressure interlock trip (> 1e-4 Torr) on Rig + SimulatedRig.
     - `test_comms_timeout_executor_survives`: re-pointed to `fail_next_write()` on Rig + SimulatedRig.
     - `test_output_off_mid_run_executor_stops`: re-pointed to stalled gauge (> 5 s stale allowance) on Rig + SimulatedRig.
     - `test_regression_nudge_does_not_assert_fio1` & `test_regression_nudge_during_run_does_not_assert_fio1`: re-pointed to `Nudge` command on Rig.
     - `test_regression_gui_state_matches_ps_after_so_latch`: re-pointed to open TC trip on Rig.

4. **Architecture rules:**
   - Removed all transitional exceptions from `tests/unit/test_architecture_rules.py`.
   - Added Rule 6: verified that the only `time.sleep` under `control/`, `data/run_record.py` and `rig/` is inside `RealClock.sleep_until`. All 7 architecture rule tests pass.

5. **AGENTS.md updated:**
   - Updated sections 4 (Codebase Map), 5.1 (Thread Safety), 5.3 (Temperature Units), and 5.5 (Practice Mode) to remove descriptions of retired modules and accurately describe the Rig architecture.

6. **All gates pass:**
   - `ruff check .`: 0 errors.
   - `python scripts/check_tests_first.py`: OK.
   - `pytest --tb=short -q`: 419 passed in 4.27s.
