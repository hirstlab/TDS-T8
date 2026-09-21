# 01: Test suite passes in any order

**What to build:** `pytest` runs the whole suite to 0 failures and 0 collection errors, and every test passes no matter which tests ran before it. Today the run stops at collection because a dead test file imports `pyvisa`. With that file excluded, 6 tests in `TestIntegration` fail, but only when earlier tests have run first: each one passes when run alone. This ticket removes the dead file and fixes the state leak at its root, so the CI gate added in ticket 03 starts out green.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Read** `.scratch/workflow-setup/spec.md` and `docs/adr/0001-tests-first-and-no-muted-failures.md` **first.** ADR 0001 is binding.

Context, as measured on `main` @ `d5f30ae`:

- `tests/unit/test_keysight_connection.py` imports `pyvisa`. The application stopped using VISA a while ago: the power supply is driven through the T8's DACs by `KeysightAnalogController`, which `tests/unit/test_power_supply.py` covers. Deleting a test for code that no longer exists is not muting it.
- The 6 failing tests are `test_auto_start_acquisition_not_running_without_hardware`, `test_auto_start_idempotent`, `test_log_btn_exists`, `test_main_window_init`, `test_no_start_stop_buttons` and `test_slider_mode_btn_exists`, all in `tests/unit/test_integration.py::TestIntegration`. Every one fails with `StopIteration` raised from `unittest/mock.py`. That means a mock whose `side_effect` is a finite list or iterator gets consumed by an earlier test and is still shared when these run.

Requirements:

- Delete `tests/unit/test_keysight_connection.py`. Remove any other remaining reference to `pyvisa` in `tests/` only where it exists to support that file.
- Find the leak at its source: which object is shared, which earlier test consumes it, and why its scope lets it survive between tests. Fix it there: a correctly scoped fixture, a fresh mock per test, or resetting the module-level state it lives in.
- **Not acceptable as a fix:** reordering tests, marking any test `skip`/`xfail`, running the file in a separate process, turning `side_effect` into an infinite iterator just to hide the exhaustion, or catching `StopIteration`. Each of these hides the leak instead of removing it (ADR 0001).
- If the leak turns out to be module-level state inside `t8_daq_system/` (not in the tests), fix it in the application code without changing runtime behaviour. Record what it was under `## Comments`.
- Under `## Comments`, record the root cause in two or three sentences: the shared object, the test that consumes it, and the fix.

- [ ] `tests/unit/test_keysight_connection.py` no longer exists
- [ ] `pytest -q` → 254 passed, 0 failed, 0 errors (the deleted file collected no tests; if the count differs, explain why under `## Comments`)
- [ ] `pytest -q tests/unit/test_integration.py` passes
- [ ] `pytest -q -p no:randomly` passes
- [ ] `pytest -q tests/unit` passes when run twice in a row
- [ ] Root cause recorded under `## Comments`
- [ ] `python scripts/check_tests_first.py` and `pytest --tb=short -q` pass. (`ruff check .` is not clean until ticket 02, so it is not a gate here. Just don't add new findings: the count must not go above 133.)

## Comments
