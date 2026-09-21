# 04: Branch protection on `main`

**What to build:** A pull request into `main` cannot merge unless both CI jobs pass, so an implementing agent can't land a red build by leaving it out of the PR.

**Blocked by:** 03

**Status:** done

This one is Isaac's: it's a repository setting, and agents do not have admin access to change it.

Steps: GitHub → `hirstlab/TDS-T8` → Settings → Branches (or Rules → Rulesets) → add a rule for `main`:

- Require a pull request before merging.
- Require status checks to pass, and add `lint` and `test` (they show up in the picker only after ticket 03's workflow has run at least once).
- Require branches to be up to date before merging.

- [x] Rule is active on `main` with `lint` and `test` required
- [x] Checked: a PR with a failing check shows "Merging is blocked"
- [x] `Status: done` set here, and the `ACTIVE-PLAN` pointer moved on to `.scratch/rig-architecture/`

## Comments

### 2026-09-21 Isaac Legault & Agent
- Ruleset "CI flow" (id: 23790354) verified active on `~DEFAULT_BRANCH` (`main`).
- Configured rules:
  - Pull request required before merging (`required_approving_review_count: 0`)
  - Strict required status checks: `lint` and `test` (branches must be up to date before merging)
  - Non-fast-forward merges prevented
- Tested with probe PR #56:
  - Feature branch pushes succeed normally.
  - Intentional lint failure in CI failed check `lint` in 50s.
  - GitHub blocked merging on PR #56 with failed checks.
  - Probe PR #56 closed and temporary probe branch cleaned up.
