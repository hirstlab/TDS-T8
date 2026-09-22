# 07: Heater output arbitrates and latches

**What to build:** The single arbiter of what the heater does. Given this tick's trips and requests, `HeaterOutput.resolve(requests, snapshot)` returns `(output_enabled, volts)` and holds the latch. Every rule in ADR 0003 is proven by a direct test, plus a property test that no request sequence can command more than 6 V or touch DAC1.

**Blocked by:** 02

**Status:** in-progress

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `AGENTS.md` §2 (CV-only) and `.scratch/rig-architecture/spec.md` (The Heater output) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- New pure module; no I/O, no clock, no thread. Priority Safety > Operator > Program.
- Rules 1–6 exactly as the spec states them: trip → `(False, 0.0)` same tick + latch + kind/reason recorded; `ResetTrip` accepted only if the tripping condition is absent now (override needs every TC < `TEMP_OVERRIDE_RESET_C`; stale needs a fresh valid reading; `labjack_lost` needs a connected adapter), otherwise a published refusal reason; output enabled only by `StartProgram` or `SetOutput(True)`, only when `permissive_ok` and not latched — **a nudge never enables output** (preserves FIX-3); an Operator request while a Program runs stops the Program first (return that as part of the result so the Rig can act on it); cold-tungsten guard (`ps_amps > COLD_CURRENT_LIMIT_A` → volts may not rise above the previous command); clamp to `[0.0, DAC0_MAX_V]`.
- The result type has no field that could command DAC1.
- No ramp-down anywhere in this module.
- Uses the Hypothesis library if it is already a dev dependency; otherwise a seeded `random` loop of at least 1 000 sequences. Do not add a dependency without saying so in the PR.

- [ ] One test per rule 1–6, each with the case that must pass and the case that must be refused
- [ ] Property test: over random request/trip/snapshot sequences, volts ∈ [0, 6] always, output never enabled while latched, a nudge never flips output from off to on
- [ ] Reset refusal reason is present and names the persisting condition
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
