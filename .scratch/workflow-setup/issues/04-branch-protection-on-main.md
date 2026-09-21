# 04: Branch protection on `main`

**What to build:** A pull request into `main` cannot merge unless both CI jobs pass, so an implementing agent can't land a red build by leaving it out of the PR.

**Blocked by:** 03

**Status:** ready-for-developer

This one is Isaac's: it's a repository setting, and agents do not have admin access to change it.

Steps: GitHub → `hirstlab/TDS-T8` → Settings → Branches (or Rules → Rulesets) → add a rule for `main`:

- Require a pull request before merging.
- Require status checks to pass, and add `lint` and `test` (they show up in the picker only after ticket 03's workflow has run at least once).
- Require branches to be up to date before merging.

- [ ] Rule is active on `main` with `lint` and `test` required
- [ ] Checked: a PR with a failing check shows "Merging is blocked"
- [ ] `Status: done` set here, and the `ACTIVE-PLAN` pointer moved on to `.scratch/rig-architecture/`

## Comments
