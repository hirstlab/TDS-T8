# 03: CI gate on GitHub, green

**What to build:** Every push, and every pull request to `main`, runs the three gates on GitHub (`ruff check .`, `python scripts/check_tests_first.py`, `pytest --tb=short -q`) and shows the result on the commit and the PR. The PR that adds the workflow is itself green.

**Blocked by:** 02

**Status:** done

**Read** `.scratch/workflow-setup/spec.md`, `docs/agents/multi-tool-setup.md` and `docs/adr/0001-tests-first-and-no-muted-failures.md` **first.** ADR 0001 is binding.

Requirements. New file `.github/workflows/tests.yml`:

- `name: tests`
- Triggers: `push` on all branches, and `pull_request` with `branches: [main]`.
- `concurrency`: `group: ${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true`.
- Every job uses `runs-on: windows-latest` and `actions/setup-python@v5` with `python-version: "3.14"` (pinned: it's the development machine's version), `cache: pip` and `cache-dependency-path` listing both `requirements.txt` and `requirements-dev.txt`. Install with `python -m pip install -r requirements-dev.txt`.
- Two jobs, with exactly these ids (Isaac makes them required status checks in ticket 04, and the names must match):
  - `lint`: `actions/checkout@v4` with `fetch-depth: 0` (the tests-first script diffs against the base branch and needs its history). Then `ruff check .`, then `python scripts/check_tests_first.py`, as separate steps in that order.
  - `test`: `actions/checkout@v4`, then `pytest --tb=short -q`.
- No `continue-on-error`, no `|| true`, no step that can pass while a gate fails (ADR 0001).
- Hardware libraries stay mocked by `tests/conftest.py`. `labjack-ljm` installs from PyPI without the native driver, and nothing in CI may load it for real.
- If any package in `requirements.txt` will not install on Python 3.14 on `windows-latest`, **escalate** (AGENTS.md §12, step 8), quoting the pip error. Do not loosen or change version pins, and do not drop the Python version.

- [x] `.github/workflows/tests.yml` exists as specified
- [x] The PR shows both `lint` and `test` green
- [x] The `test` job is re-run once from the Actions UI (or with `gh run rerun --job`) and is green again. Link both runs under `## Comments`
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass locally

## Comments

### 2026-09-21: Ticket Resolution Summary

**Workflow Implementation:**
- Added `.github/workflows/tests.yml` with triggers `push` and `pull_request` (branches: `[main]`), concurrency group `${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`.
- Configured runner `windows-latest` with Python 3.14 via `actions/setup-python@v5`, `cache: pip`, and `cache-dependency-path` listing `requirements.txt` and `requirements-dev.txt`.
- Defined job `lint` running checkout (`fetch-depth: 0`), dependency install, `ruff check .`, and `python scripts/check_tests_first.py`.
- Defined job `test` running checkout, dependency install, and `pytest --tb=short -q`.

**GitHub Actions Verification:**
- PR: https://github.com/hirstlab/TDS-T8/pull/55
- Push workflow run: https://github.com/hirstlab/TDS-T8/actions/runs/35651996520
  - `lint` job: https://github.com/hirstlab/TDS-T8/actions/runs/35651996520/job/106506356941 (passed in 56s)
  - `test` job: https://github.com/hirstlab/TDS-T8/actions/runs/35651996520/job/106506357379 (passed in 1m5s)
- PR workflow run: https://github.com/hirstlab/TDS-T8/actions/runs/35651997213
  - Initial `lint` job: https://github.com/hirstlab/TDS-T8/actions/runs/35651997213/job/106506357206 (passed in 1m3s)
  - Initial `test` job: https://github.com/hirstlab/TDS-T8/actions/runs/35651997213/job/106506357619 (passed in 1m14s)
  - Rerun of `test` job (ID 106506899591): https://github.com/hirstlab/TDS-T8/actions/runs/35651997213/job/106506899591 (passed in 48s)

**Local Gate Verification:**
- `ruff check .`: All checks passed!
- `python scripts/check_tests_first.py`: OK (0 application source files modified)
- `pytest --tb=short -q`: 254 passed in 2.19s
