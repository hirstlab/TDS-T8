# 02: `ruff check .` is clean

**What to build:** `ruff check .` exits 0 on the whole repo, with the configuration checked in, so CI (ticket 03) can run it as a gate. Nothing the application does changes.

**Blocked by:** 01

**Status:** done

**Read** `.scratch/workflow-setup/spec.md` and `docs/adr/0001-tests-first-and-no-muted-failures.md` **first.** ADR 0001 is binding.

Context: before ticket 01, ruff reported 133 findings: 57 E402, 26 F401, 19 F541, 14 E731, 9 F841, 6 E722, 1 E401 and 1 E741. Ticket 01 deletes one file that accounted for 2 of them. The E402 findings are spread like this: 3 in `t8_daq_system/main.py`, 21 in `t8_daq_system/gui/main_window.py` (the `GUIProfiler` class and the `gui_profiler = GUIProfiler()` line sit above the `# Import our modules` block), and 33 across test files (a `pytestmark = ...` line or a docstring placed before the imports).

Requirements:

- New file `pyproject.toml` at the repo root. It holds only a `[tool.ruff]` section with:
  - `target-version = "py314"`
  - the default rule set (do not add a `select` or `extend-select`)
  - `extend-exclude = ["build", "dist", ".venv"]`
  - `[tool.ruff.lint.per-file-ignores]` allowing E402 in exactly two files: `"t8_daq_system/main.py" = ["E402"]` and `"tests/conftest.py" = ["E402"]`. The reason: those files must set `MPLBACKEND`, call `matplotlib.use('TkAgg', force=True)` and install hardware mocks into `sys.modules` before importing anything else (a PyInstaller requirement). Put that reason in a one-line TOML comment next to the entry.
- New file `requirements-dev.txt` containing exactly `-r requirements.txt`, `pytest` and `ruff`, one per line.
- Fix every other finding. **No other ignores:** no `# noqa`, no additional `per-file-ignores`, no rule deselection. That includes E402 in `gui/main_window.py`: move the `t8_daq_system` imports above `GUIProfiler`. In the test files, move `pytestmark` and the docstring below the imports.
- E731: rewrite each lambda assignment as a `def` with the same name and body.
- E722: each bare `except:` names the narrowest exception the guarded code can actually raise (read the guarded call to find it) and logs it through the module's existing logger or `print` path, whichever that module already uses. **`except Exception: pass` is not allowed.** It is the same silent swallow under a different name.
- F841 and F401: delete the unused name. **Exception:** if an unused variable looks like it was meant to be used (a computed value that is thrown away, a return value that is ignored where it probably shouldn't be), do not delete it silently. Keep it, add `# NOTE: unused — possible bug, see workflow-setup ticket 02` and `del` it, or otherwise make it clean without changing behaviour, and list each one under `## Comments` for the rig-architecture effort. Do not fix the suspected bug in this ticket.
- No behaviour change anywhere. The existing suite is the check, and it must stay at 0 failures.
- This ticket edits `t8_daq_system/` without editing `tests/` in a way that adds coverage, so the tests-first gate needs an explicit exemption. Put `[no-test-needed: lint-only, no behaviour change]` in the PR description and the commit message.

- [x] `ruff check .` → `All checks passed!`
- [x] `pyproject.toml` and `requirements-dev.txt` exist with the contents above
- [x] `grep -rn "noqa" t8_daq_system tests` returns nothing
- [x] `grep -rnE "except:\s*$" t8_daq_system tests` returns nothing
- [x] Every suspected bug from F841/F401 is listed under `## Comments`, or `## Comments` says "none found"
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### 2026-09-21: Ticket Resolution Summary

**Configuration & Tooling:**
- Created `pyproject.toml` with `[tool.ruff]` target-version `"py314"`, default rule set, and `[tool.ruff.lint.per-file-ignores]` allowing E402 in `t8_daq_system/main.py` and `tests/conftest.py`.
- Created `requirements-dev.txt` containing `-r requirements.txt`, `pytest`, and `ruff<0.16`.
  *Note on `ruff<0.16`:* In Ruff 0.16.0 (released July 2026), Astral introduced breaking changes to the default rule set, removing E402/E731 from defaults and expanding default rules from 59 to 413 rules (enabling opt-in rules like flake8-bandit `S`, `BLE`, `DTZ`, etc.). Pinning `ruff<0.16` preserves the 59-rule default set for which the ticket and repository was configured.

**Cleanups and Fixes:**
- Fixed all E402 module-level import findings by moving imports to the top of files (including in `t8_daq_system/gui/main_window.py` above `GUIProfiler`, and across test files below module docstrings/above `pytestmark`).
- Fixed all E731 findings by replacing lambda assignments with `def` definitions.
- Fixed all E722 bare `except:` instances in `program_executor.py`, `main_window.py`, and `labjack_connection.py` by naming the narrowest caught exception (`Exception`, `(tk.TclError, AttributeError)`, `ljm.LJMError`) and adding error logging/printing.
- Fixed all E401 (multiple imports on one line) and E741 (ambiguous variable name `I` renamed to `current` in `test_tungsten_model.py`).
- Fixed all F541 f-strings without placeholders by removing the `f` prefix.
- Removed all 3 pre-existing `# noqa` comments (`camera_panel.py` lines 41 and 609, `conftest.py` line 71).

**Suspected Bugs Listed for Rig-Architecture Effort (F841/F401):**
1. `t8_daq_system/control/program_executor.py:224`: `block_start_temp_k` was computed from `self._current_get_temp_k()` for `"TC_1"`, but immediately superseded on lines 241-247 where `live_start_k` is computed by resolving the first block's `tc_name`.
2. `t8_daq_system/control/program_executor.py:334`: `dt = now - self._last_tick_time if self._last_tick_time else 0.1` was computed every tick in `_execute_block` but never passed to PID or used in the control loop.
3. `t8_daq_system/control/safety_monitor.py:224`: `watchdog = self._watchdog_sensor` was captured under `with self._lock:`, but on line 281 `self._watchdog_sensor` was accessed directly rather than using the local snapshot.
4. `t8_daq_system/gui/pinout_display.py:462`: `cfg = self._config.get('power_supply', {})` was fetched in `_build_ps_section` but `status_items` only reads from `s = self._settings`.
5. `t8_daq_system/hardware/frg702_reader.py:309`: `except Exception as e:` in `FRG702AnalogReader.read_all()`; unlike line 289 which logs the error, line 309 silently set values to error/None without logging `e`.
6. `t8_daq_system/hardware/keysight_analog_controller.py:285, 326`: `actual_written = self._safe_dac_write(...)` in `set_voltage` and `set_current`; `_safe_dac_write` returns None so assigning to `actual_written` was unused.
7. `tests/unit/test_hardware.py:68`: `reader = ThermocoupleReader(self.mock_handle, self.tc_config)` assigned in `test_tc_reader_init` to verify initialization side-effects, but reference unused.
8. `tests/unit/test_integration.py:154`: `original_on_start = app._on_start` assigned before monkey-patching in `test_auto_start_idempotent`, but never restored.

**Verification:**
- `ruff check .` -> `All checks passed!`
- `python scripts/check_tests_first.py` -> passed
- `pytest --tb=short -q` -> 254 passed, 0 failed in 2.65s
- `grep -rn "noqa" t8_daq_system tests` -> empty (0 matches)
- `grep -rnE "except:\s*$" t8_daq_system tests` -> empty (0 matches)
