---
name: tds-ticket
description: Implement one ticket from a TDS-T8 ticket set end to end — orientation, the split decision, test-first implementation, the full local gate, adversarial self-review, the PR, and watching CI. Use whenever asked to implement, work, pick up or continue a ticket, work the frontier, or act on the ACTIVE-PLAN block in AGENTS.md.
---

# Implementing one TDS-T8 ticket

This repository heats a tungsten specimen to ~1450 °C through a 6 V / 180 A supply,
unattended, for hours. A bug found on the rig costs an eight-hour run and risks the
hardware. That is why the conventions are strict, and why a green build made green
by editing a test is worse than a red one.

Work **one ticket**. Not two, not a ticket and a half. If you finish early, stop and
report; do not wander into the next ticket.

## 1. Orient before touching anything

### Repository and branch housekeeping

```powershell
git checkout main
git pull origin main
git fetch --prune
git branch --merged main | Where-Object { $_ -notmatch '^\*|\bmain\b' } | ForEach-Object { git branch -d $_.Trim() }
```

If `git pull` says `main has no tracked branch`, fix it once:
`git branch --set-upstream-to=origin/main main`.

### Read, in this order

1. **`AGENTS.md`** — the whole file: the hardware safety rules, the invariants in
   §12, the implementation protocol, and the `ACTIVE-PLAN` block at the bottom
   naming the current ticket set and what is unblocked.
2. **The ticket file** `.scratch/<effort>/issues/NN-*.md`. Its `Blocked by:` line
   and acceptance criteria are the contract. Then the effort's `spec.md`.
3. **Every ADR the ticket references**, in `docs/adr/`. Binding, not background.
4. **`CONTEXT.md`** — use its words. If a term is missing or the code contradicts
   it, say so; do not silently pick a side.
5. **The module docstring of every file you are about to edit.**

**Work the frontier.** Never start a ticket whose `Blocked by:` names one that is
not `done`. If the only unblocked ticket is `ready-for-developer` (a bench task),
say so and stop — do not claim it, simulate it, or build around it.

**Claim it:** set the ticket's `Status:` line to `in-progress` and commit that on
the ticket branch (`ticket/<effort>-NN-<slug>`).

## 2. Decide whether to split into parallel agents

Judge by the seam, not by size. State the decision and reason in one line.

- **Split — implementation and tests written independently.** One agent implements
  from the ticket; a second writes tests from the acceptance criteria and spec
  **without reading the implementation**; then reconcile. The cheapest defence
  against tests shaped to pass.
- **Split — independent tickets** touching unrelated files, one agent per branch.
- **Do not split** a vertical slice by layer, pieces that share a test seam (the
  Simulated rig, shared fixtures), or anything small.

## 3. Implement, test first

Write the test, run it, **watch it fail**, then write the code. Rules broken most
often here:

- **CV-only.** DAC1 pinned at full scale; only DAC0 commanded, clamped 0–6 V. No
  code path may change this, including shutdown paths.
- **One owner of hardware** (ADR 0002). Only the Rig module imports `labjack.ljm` or
  `serial`, holds a handle, or calls a reader. The GUI never blocks on hardware.
- **One writer of the heater** (ADR 0003). Only the Heater output writes DAC0 or the
  Shut Off pin. Everything else sends a heater request.
- **No `practice_mode` branches** outside the Rig module's adapter selection
  (ADR 0005).
- **Canonical units in logic** — °C / K for temperature as documented per module,
  Torr for pressure. Display units only at the GUI and in written CSV values.
- **Never swallow an exception.** No `except Exception: pass`. A failure is logged
  with context and surfaced as state; a failed hardware write is a fault.
- **No Tk calls from a non-GUI thread**, including `messagebox`.
- **Every number has one home** — new tunables go in config/AppSettings, never as
  literals in a widget or loop.
- **Docstrings explain WHY**, with a `WHY THIS EXISTS` section recording the bug or
  physical fact that forced the design. Update the reasoning when behaviour changes.
- `logging.getLogger(__name__)` in new code, not `print`.
- Tests do not sleep. Time comes from an injectable clock.

## 4. Run the full gate locally, before the PR

```
ruff check .
python scripts/check_tests_first.py
pytest --tb=short -q
```

All three must pass with **0 failures** before you push. CI runs the same three on
a Windows runner. If a test fails: read the output, find the root cause (threading,
timing, a fake that doesn't behave like the hardware, or a real defect), fix the
cause. Never weaken an assertion, loosen a tolerance, narrow an input, `skip` or
`xfail` (ADR 0001).

## 5. Review your own diff, adversarially

Review as if looking for the reason it will be reverted. A fresh sub-agent that did
not write the code is a good reviewer here.

- Tick **every acceptance criterion** individually. One unticked = not done.
- Does it break an invariant in §3 or `AGENTS.md` §2–3 and §12?
- **Do the tests fail when the behaviour is wrong?** Break the implementation on
  purpose and confirm red. A test never seen failing is not known to work.
- Do tests assert behaviour (Snapshot contents, CSV rows, voltage at the adapter,
  what the operator sees) rather than private attributes or call counts?
- Stale docstrings? Line endings — if `git status` shows far more files than you
  touched, stop and investigate (`.gitattributes` normalises to LF).

## 6. Land it, or escalate

### Landing

1. In the ticket file: `Status: done`, tick the criteria `- [x]`, and append a dated
   summary under `## Comments` (what changed, which tests, what was verified how).
2. Commit code, tests, docstrings and the ticket file on the ticket branch. Never
   commit to `main`.
3. `git push -u origin <branch>` and open the PR:
   `gh pr create --base main --head <branch> --title "<ticket title>" --body "<summary, criteria, gate results>"`.
   Without `gh`, give `https://github.com/hirstlab/TDS-T8/pull/new/<branch>` and the
   PR body.
4. **Watch CI:** `gh pr checks --watch --fail-fast`. Not done until you saw it green.
   If you cannot reach `gh`, say plainly that CI was not observed.

### When CI goes red

Read only the failed steps: `gh run view <run-id> --log-failed`. Never pull the full
log. Then fix under a budget of **two fix-and-push cycles**; a third attempt means
the diagnosis is wrong. Classify each failure in the commit message:

- **Real defect** — test right, code wrong. Fix the code.
- **Harness defect** — the test asserts something never promised or models the
  hardware wrong. Fix the test only if you can state what it should assert instead
  and it still fails when the behaviour is wrong. This category is the one abused
  under pressure.
- **Environment difference** — Windows paths, CRLF, a timing assumption, a missing
  dev dependency. Fix the cause; never condition a test on CI.

A red check you did not cause (main already red) is reported, not fixed inside your
branch.

### Escalating (never mute)

When you cannot fix it: commit the finished work; set `Status: blocked`; append
under `## Comments` what CI said (quoted), what each attempt concluded and changed,
and what decision you need; convert the PR to draft (`gh pr ready --undo`). The
report lives in the ticket file under `.scratch/`, which is pushed — never only in
your reply.

Guessing at a physics or safety decision is not an alternative to escalating. A
plausible-looking number on this rig is worse than no number.
