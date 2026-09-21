# 02: `ruff check .` is clean

**What to build:** `ruff check .` exits 0 on the whole repo, with the configuration checked in, so CI (ticket 03) can run it as a gate. Nothing the application does changes.

**Blocked by:** 01

**Status:** ready-for-agent

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

- [ ] `ruff check .` → `All checks passed!`
- [ ] `pyproject.toml` and `requirements-dev.txt` exist with the contents above
- [ ] `grep -rn "noqa" t8_daq_system tests` returns nothing
- [ ] `grep -rnE "except:\s*$" t8_daq_system tests` returns nothing
- [ ] Every suspected bug from F841/F401 is listed under `## Comments`, or `## Comments` says "none found"
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
