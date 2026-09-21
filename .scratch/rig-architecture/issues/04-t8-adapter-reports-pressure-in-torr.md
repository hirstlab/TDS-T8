# 04: T8 adapter reports pressure in Torr

**What to build:** The real-hardware Rig adapter. It wraps today's LabJack, thermocouple, FRG-702, XGS-600 and Keysight classes behind the Rig adapter seam, and every gauge reading leaves it in Torr regardless of the operator's display unit. This is where the pressure-interlock unit bug (trips 25 % early in mbar, immediately in Pa) gets its regression test.

**Blocked by:** 02

**Status:** ready-for-agent

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md`, `AGENTS.md` §2–§3 (CV-only, wiring, XGS `T{2*i+1}` addressing) and `.scratch/rig-architecture/spec.md` (The Rig adapter seam) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `T8Adapter` implements `RigAdapter` and is the **only** place `LabJackConnection`, `ThermocoupleReader`, `FRG702Reader`/`FRG702AnalogReader`, `XGS600Controller` and `KeysightAnalogController` are constructed from new code. (Existing construction in `main_window.py` stays until ticket 05 removes it.)
- `read()` is one call per tick and returns the fields the spec lists. Gauge values are converted to Torr using `FRG702Reader.convert_pressure`; the adapter never returns a display unit.
- The display-unit conversion moves out of the readers: readers return a canonical unit, and display conversion becomes a pure function the GUI (and later the Run record) calls. Update every current caller so today's screen still shows the chosen unit.
- `write_voltage` touches DAC0 only. `pin_current_limit` sets DAC1 to full scale and is the only DAC1 write. `set_output(False)` keeps today's 3-attempt verify.
- Link failures raise `AdapterError`; nothing in the adapter swallows an exception.
- Serial request/response to the XGS-600 is serialised (one lock, or by construction since only the Rig thread calls it) — state which in the module docstring.
- Tests run with the LJM and serial layers mocked as `tests/conftest.py` already does.

- [ ] The same physical pressure configured for mbar, Torr and Pa display reaches `read()` as the same Torr value (the regression test for the unit bug)
- [ ] The screen still shows pressure in the selected display unit (existing GUI/reader tests updated, not weakened)
- [ ] `write_voltage` writes DAC0 only; no call path in the adapter writes DAC1 except `pin_current_limit`
- [ ] A mocked LJM failure in `read()` / `write_voltage` / `set_output` raises `AdapterError`
- [ ] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments
