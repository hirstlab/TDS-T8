# 15: No silent exceptions

**What to build:** No failure in the app disappears. Every `except` handler whose whole body is `pass` (57 before this effort; fewer after ticket 14) either handles the error, reports it (log line, Snapshot field, event row or GUI message, whichever fits where it is), or lets it propagate. A rule test keeps it that way.

**Blocked by:** 14

**Status:** done

**Read** `AGENTS.md` §12.1 item 6 and `docs/adr/0003-heater-output-arbitration-and-trips.md` **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Find the handlers with an `ast` walk (body only `pass` or `...`), not grep.
- For each: decide handle / report / propagate. Anything on a heater, safety or shutdown path propagates or reports visibly — never merely logs to stdout. Best-effort cosmetic paths (e.g. a GUI redraw of a closed widget) may log and continue, with a one-line comment saying why that is safe.
- List every handler changed and the decision in the PR, grouped by file.
- If a decision would change safety behaviour beyond what ADR 0003 already says, escalate instead of choosing.
- Add to `test_architecture_rules.py`: no `except` handler under `t8_daq_system/` whose body is only `pass` or `...`.

- [x] The rule test passes with zero exceptions
- [x] Each changed handler on a heater/safety/shutdown path has a test that the failure is now visible (Snapshot, event row, or raised)
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### Completed 2026-09-25:
- Removed all 46 silent `except: pass` handlers across `t8_daq_system/`.
- Propagated errors (`raise`) on safety callback failure paths in `SafetyMonitor` (`_on_warning`, `_on_limit_exceeded`, `_on_shutdown`).
- Propagated `ValueError` on malformed threshold parsing in `HeaterOutput._extract_limit_from_reason`.
- Added descriptive logging and safe comments on best-effort / cosmetic UI, hardware disconnect, and metadata parsing paths.
- Added AST rule test `test_no_silent_exceptions` to `test_architecture_rules.py`.
- Added tests in `test_safety_monitor.py` verifying callback exceptions propagate, and in `test_heater_output.py` verifying malformed trip reason parsing raises `ValueError`.
- Added test in `test_power_supply.py` verifying `KeysightAnalogController` handles missing EF registers gracefully.
- All gates pass: `ruff check .`, `python scripts/check_tests_first.py`, and `pytest --tb=short -q` (425 tests pass).

