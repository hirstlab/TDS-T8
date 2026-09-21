# 03: CI gate on GitHub, green

**What to build:** Every push, and every pull request to `main`, runs the three gates on GitHub (`ruff check .`, `python scripts/check_tests_first.py`, `pytest --tb=short -q`) and shows the result on the commit and the PR. The PR that adds the workflow is itself green.

**Blocked by:** 02

**Status:** in-progress

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

- [ ] `.github/workflows/tests.yml` exists as specified
- [ ] The PR shows both `lint` and `test` green
- [ ] The `test` job is re-run once from the Actions UI (or with `gh run rerun --job`) and is green again. Link both runs under `## Comments`
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass locally

## Comments
