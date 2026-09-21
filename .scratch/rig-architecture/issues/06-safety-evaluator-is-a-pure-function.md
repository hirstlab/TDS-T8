# 06: Safety evaluator is a pure function

**What to build:** Safety decisions become a pure function of a Snapshot: `evaluate(snapshot, state) -> list[Trip]`. Every trip threshold can be tested at, just below and just above its boundary without a thread, a power supply or a clock. Warnings are reported but never trip. The pressure permissive is computed here, in Torr.

**Blocked by:** 02

**Status:** ready-for-agent

**Read** `docs/adr/0003-heater-output-arbitration-and-trips.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md` and `.scratch/rig-architecture/spec.md` (Safety evaluation) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- Add the pure evaluator to `SafetyMonitor` (or beside it) with no thread, no power-supply reference and no callbacks. Keep per-sensor limits, warning threshold and debounce semantics, and keep `set_temperature_limit`, `set_warning_threshold`, `set_debounce_count` as the operator-facing setters.
- Trip kinds and conditions exactly as the spec lists: `temp_limit` (debounced), `temp_override` (`TEMP_OVERRIDE_C`), `pressure_high` (> `PRESSURE_INTERLOCK_TORR`), `pressure_stale` (> `STALE_ALLOWANCE_S`), `control_tc_stale` (only while a closed-loop block runs, from `snapshot.program`). `labjack_lost` and `program_error` are **not** raised here.
- Each `Trip` carries its kind and a human-readable reason naming the sensor and value.
- `permissive_ok` / `permissive_reason`: true only when every enabled gauge has a valid reading ≤ `STALE_ALLOWANCE_S` old and below threshold.
- Numbers come from `settings/safety_limits.py`; no literal thresholds in the evaluator.
- The existing threaded/rampdown code is left untouched in this ticket (removed in 08). `tests/unit/test_safety_monitor.py` gains the new tests; existing tests still pass.

- [ ] Each trip kind has tests at, just below and just above its boundary (stale: 4.9 s no trip, 5.1 s trip)
- [ ] Debounce: `debounce_count - 1` consecutive over-limit ticks do not trip; `debounce_count` do
- [ ] A warning-band temperature appears as a warning and never as a trip
- [ ] `control_tc_stale` never fires while no closed-loop block is running
- [ ] Permissive is false for a stale, invalid or high gauge and true otherwise
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
