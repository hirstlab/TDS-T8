# Spec: Workflow setup — CI gate on GitHub, green on main

Status: ready-for-agent
Date: 2026-09-21
Related: `docs/adr/0001-tests-first-and-no-muted-failures.md`,
`docs/agents/multi-tool-setup.md`, `AGENTS.md` §12

> ADR 0001 is binding: a failing test is fixed or escalated, never muted.
> This effort blocks `.scratch/rig-architecture/`. Nothing there starts until CI is
> green on `main`.

## Problem Statement

TDS-T8 has 254 tests and no CI. Nothing runs them on push, so "the suite passes" is
unverified, and an implementing agent has no place to report a red build. Isaac
does not want to run the suite locally himself — GitHub is where results should
show up.

Baseline measured on 2026-09-21 (Linux, Python 3.11, from `main` @ `6923440`):

- `tests/unit/test_keysight_connection.py` fails at **collection**: it imports
  `pyvisa`, which the application no longer uses (the supply is driven through the
  T8's DACs, not VISA). This aborts the whole run.
- With that file excluded: **248 passed, 6 failed**. All six failures are in
  `tests/unit/test_integration.py::TestIntegration` and **each passes when run on
  its own** — an order-dependent test-isolation defect, not an application defect.
- `ruff check .` (default rules): **133 findings** — 57 E402, 26 F401, 19 F541,
  14 E731, 9 F841, 6 E722 (bare `except`), 1 E401, 1 E741.
- The working tree shows 43 files modified with 13 721 insertions and 13 721
  deletions. `git diff --ignore-cr-at-eol` is empty: **every one is a line-ending
  change**, not real work. There was no `.gitattributes`.

The ticketing workflow files already exist in the tree (added 2026-09-21, not yet
committed): `AGENTS.md` §12, `CLAUDE.md`, `CONTEXT.md`, `docs/adr/0001–0005`,
`docs/agents/*`, `.claude/skills/tds-ticket/`, `.agents/skills/tds-ticket/`,
`.claude/scripts/set_plan.py`, `scripts/check_tests_first.py`,
`tests/unit/test_check_tests_first.py` (11 tests, passing), `.gitattributes`, and a
`.gitignore` that now tracks `AGENTS.md` and the three shared `.claude/` folders.

## Solution

A GitHub Actions workflow on a Windows runner runs three gates in order —
`ruff check .`, `python scripts/check_tests_first.py`, `pytest --tb=short -q` — on
every push and on pull requests to `main`, and `main` is green.

## User Stories

1. As Isaac, I want every push checked on GitHub, so that I never have to run the
   suite myself to know whether a branch is sound.
2. As Isaac, I want a red build to block a merge, so that an implementing agent
   cannot land a regression by not mentioning it.
3. As an implementing agent, I want the same three commands locally and in CI, so
   that I can reproduce a CI failure before pushing.
4. As an implementing agent, I want the tests-first rule enforced by a script, so
   that "tests come first" is a gate and not advice.
5. As a reviewer, I want diffs that show real changes only, so that line-ending
   churn never hides a code change.

## Implementation Decisions

- **Line endings first, by Isaac.** Commit the workflow files as they are, then
  renormalise in its own commit: `git add --renormalize .` →
  `git commit -m "Normalise line endings to LF (.gitattributes)"`. This is a
  `ready-for-developer` step because it rewrites every file in history's next
  commit and must not be mixed with code changes.
- **Workflow file:** `.github/workflows/tests.yml`, modelled on the RBL repository's:
  `windows-latest`, `actions/setup-python@v5`, pip cache keyed on
  `requirements.txt` and `requirements-dev.txt`, `concurrency` cancelling superseded
  runs, triggers `push` (all branches) and `pull_request` to `main`. Two jobs:
  `lint` (ruff, then tests-first gate with `fetch-depth: 0`) and `test` (pytest).
- **Python version:** 3.14 in CI, pinned — the version the development machine
  runs (its `__pycache__` holds `cpython-314` files) and the one RBL's CI uses.
- **`requirements-dev.txt` (new):** `-r requirements.txt` plus `pytest` and `ruff`.
  CI installs this file. Hardware libraries stay mocked by `tests/conftest.py`;
  `labjack-ljm` installs from PyPI without the native driver and is never loaded
  for real in tests.
- **Ruff configuration** lives in a new `pyproject.toml` `[tool.ruff]` section:
  `target-version = "py314"`, default rule set, `extend-exclude` for `build/`,
  `dist/`, `.venv/`. E402 is permitted **only** in `t8_daq_system/main.py` and
  `tests/conftest.py` via `per-file-ignores`, because those files must set
  environment variables (`MPLBACKEND`, `matplotlib.use('TkAgg', force=True)`) and
  install hardware mocks before importing — a documented PyInstaller requirement.
  Every other finding is fixed, not ignored. The six E722 bare `except:` are fixed
  by naming the exception and logging it; none may become `except Exception: pass`.
- **`test_keysight_connection.py`** is deleted. It tests a VISA path the
  application no longer has; the analog controller is covered by
  `tests/unit/test_power_supply.py`. Deleting a test for removed code is not muting.
- **The six order-dependent `TestIntegration` failures** are diagnosed to root cause
  (shared module state, a mock leaking between tests, or a fixture with the wrong
  scope) and fixed so the suite passes in any order. Fixing the leak is required;
  reordering tests or running the file in isolation is not a fix.
- **Branch protection** on `main` requiring both jobs is set by Isaac in GitHub
  settings (`ready-for-developer`).

## Testing Decisions

- `tests/unit/test_check_tests_first.py` already covers the gate script.
- Acceptance for the isolation fix: `pytest -p no:randomly -q` and
  `pytest -q tests/unit/test_integration.py` both pass, and the full suite passes
  twice in a row in CI.

## Out of Scope

- The type gate and mypy ratchet used in RBL — not adopted here (decided
  2026-09-21).
- Any application behaviour change. Fixing ruff findings must not change what the
  code does; where a fix would (e.g. an unused variable that looks like a bug), leave
  a `# NOTE:` and record it under the ticket's `## Comments` for the rig-architecture
  effort instead.
- PyInstaller builds in CI.

## Further Notes

`AGENTS.md` §6.3 states default gains Kp=1.0, Ki=0.05, Kd=0.05; the code
(`control/temp_ramp_pid.py`) defaults to kp=0.02, ki=0.0013, kd=0.005. The section is
stale. Isaac owns that text; flagged here, not changed.
