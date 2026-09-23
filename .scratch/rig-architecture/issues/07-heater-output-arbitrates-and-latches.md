# 07: Heater output arbitrates and latches

**What to build:** The single arbiter of what the heater does. Given this tick's trips and requests, `HeaterOutput.resolve(requests, snapshot)` returns `(output_enabled, volts)` and holds the latch. Every rule in ADR 0003 is proven by a direct test, plus a property test that no request sequence can command more than 6 V or touch DAC1.

**Blocked by:** 02

**Status:** done

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `AGENTS.md` §2 (CV-only) and `.scratch/rig-architecture/spec.md` (The Heater output) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- New pure module; no I/O, no clock, no thread. Priority Safety > Operator > Program.
- Rules 1–6 exactly as the spec states them: trip → `(False, 0.0)` same tick + latch + kind/reason recorded; `ResetTrip` accepted only if the tripping condition is absent now (override needs every TC < `TEMP_OVERRIDE_RESET_C`; stale needs a fresh valid reading; `labjack_lost` needs a connected adapter), otherwise a published refusal reason; output enabled only by `StartProgram` or `SetOutput(True)`, only when `permissive_ok` and not latched — **a nudge never enables output** (preserves FIX-3); an Operator request while a Program runs stops the Program first (return that as part of the result so the Rig can act on it); cold-tungsten guard (`ps_amps > COLD_CURRENT_LIMIT_A` → volts may not rise above the previous command); clamp to `[0.0, DAC0_MAX_V]`.
- The result type has no field that could command DAC1.
- No ramp-down anywhere in this module.
- Uses the Hypothesis library if it is already a dev dependency; otherwise a seeded `random` loop of at least 1 000 sequences. Do not add a dependency without saying so in the PR.

- [x] One test per rule 1–6, each with the case that must pass and the case that must be refused
- [x] Property test: over random request/trip/snapshot sequences, volts ∈ [0, 6] always, output never enabled while latched, a nudge never flips output from off to on
- [x] Reset refusal reason is present and names the persisting condition
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### 2026-09-22: Ticket 07 implementation complete
- Built `t8_daq_system.control.heater_output`:
  - `HeaterOutput`: pure arbiter with no I/O, no thread, no clock.
  - Priority: Safety > Operator > Program.
  - Rules 1–6 implemented:
    - Rule 1: Instant cutoff `(False, 0.0)` on trip, latches, records kind/reason. While latched, Operator and Program requests are ignored.
    - Rule 2: `ResetTrip` accepted only when tripping condition is absent now (`temp_override` < `TEMP_OVERRIDE_RESET_C`, stale sources have fresh valid readings, `labjack_lost` has connected adapter); publishes explicit refusal reason naming the persisting condition otherwise.
    - Rule 3: Output enabled only by `StartProgram` or `SetOutput(True)` when `permissive_ok` and not latched. Nudge never enables output (FIX-3).
    - Rule 4: Operator request while a Program runs stops the Program first (`stop_program=True`) and applies without blending.
    - Rule 5: Cold-tungsten guard (`ps_amps > COLD_CURRENT_LIMIT_A` prevents voltage rise above previous command).
    - Rule 6: DAC0 voltage clamped to `[0.0, DAC0_MAX_V]` (0–6 V). `HeaterCommand` result type unpacks as `(output_enabled, volts)` and exposes no fields that could touch DAC1.
- Built tests in `tests/unit/test_heater_output.py`:
  - Direct tests for Rules 1–6 with both passing and refused cases.
  - Dedicated tests for ResetTrip refusal reasons for persisting conditions (temp override, pressure stale, labjack lost, active trips).
  - Seeded random property test over 1,200 sequences (10 steps each) validating voltage range `[0, 6]`, output never enabled while latched, nudge never flipping output on, and latch persisting without ResetTrip.
  - Verified test-first (saw failure on missing module), and verified mutation failure (breaking DAC0 clamp).
- Full local gate passed: `ruff check .` (0 errors), `python scripts/check_tests_first.py` (passed), `pytest --tb=short -q` (348 passed, 0 failures).
