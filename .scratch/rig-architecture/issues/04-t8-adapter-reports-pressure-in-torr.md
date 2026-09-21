# 04: T8 adapter reports pressure in Torr

**What to build:** The real-hardware Rig adapter. It wraps today's LabJack, thermocouple, FRG-702, XGS-600 and Keysight classes behind the Rig adapter seam, and every gauge reading leaves it in Torr regardless of the operator's display unit. This is where the pressure-interlock unit bug (trips 25 % early in mbar, immediately in Pa) gets its regression test.

**Blocked by:** 02

**Status:** done

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `docs/adr/0004-pressure-interlock-is-a-permissive.md`, `AGENTS.md` §2–§3 (CV-only, wiring, XGS `T{2*i+1}` addressing) and `.scratch/rig-architecture/spec.md` (The Rig adapter seam) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `T8Adapter` implements `RigAdapter` and is the **only** place `LabJackConnection`, `ThermocoupleReader`, `FRG702Reader`/`FRG702AnalogReader`, `XGS600Controller` and `KeysightAnalogController` are constructed from new code. (Existing construction in `main_window.py` stays until ticket 05 removes it.)
- `read()` is one call per tick and returns the fields the spec lists. Gauge values are converted to Torr using `FRG702Reader.convert_pressure`; the adapter never returns a display unit.
- The display-unit conversion moves out of the readers: readers return a canonical unit, and display conversion becomes a pure function the GUI (and later the Run record) calls. Update every current caller so today's screen still shows the chosen unit.
- `write_voltage` touches DAC0 only. `pin_current_limit` sets DAC1 to full scale and is the only DAC1 write. `set_output(False)` keeps today's 3-attempt verify.
- Link failures raise `AdapterError`; nothing in the adapter swallows an exception.
- Serial request/response to the XGS-600 is serialised (one lock, or by construction since only the Rig thread calls it) — state which in the module docstring.
- Tests run with the LJM and serial layers mocked as `tests/conftest.py` already does.

- [x] The same physical pressure configured for mbar, Torr and Pa display reaches `read()` as the same Torr value (the regression test for the unit bug)
- [x] The screen still shows pressure in the selected display unit (existing GUI/reader tests updated, not weakened)
- [x] `write_voltage` writes DAC0 only; no call path in the adapter writes DAC1 except `pin_current_limit`
- [x] A mocked LJM failure in `read()` / `write_voltage` / `set_output` raises `AdapterError`
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

### 2026-09-21: Implemented T8Adapter and pressure canonicalisation in Torr

1. **Pure pressure conversion function in helpers:**
   Added `convert_pressure(value, from_unit, to_unit)` to `t8_daq_system.utils.helpers` per `AGENTS.md` spec. Added unit tests in `tests/unit/test_helpers.py`.

2. **Canonical pressure units in readers:**
   Updated `FRG702Reader` and `FRG702AnalogReader` in `t8_daq_system/hardware/frg702_reader.py` so readings are returned in canonical Torr. Display unit conversion moved out of readers to pure callers.

3. **GUI and caller updates:**
   Updated `main_window.py` and `data_acquisition.py` so on-screen displays and logged values convert from canonical Torr to the operator's chosen display unit (`p_unit`). Buffer data units passed to `LivePlot` specify canonical `'Torr'`.

4. **T8Adapter implementation (`t8_daq_system/rig/t8_adapter.py`):**
   - Implements `RigAdapter` interface.
   - Enforces CV-only: `write_voltage` commands DAC0 only; `pin_current_limit` pins DAC1 to full scale (180 A) and is the only DAC1 write.
   - Keeps 3-attempt verify on `set_output(False)`.
   - Raises `AdapterError` on hardware/link failures without swallowing exceptions.
   - Serial communication to XGS-600 serialized by construction on the Rig loop thread.

5. **Unit test suite (`tests/unit/test_t8_adapter.py`):**
   - 10 unit tests covering unit bug regression (mbar, Torr, Pa configurations yield identical Torr readings), screen display unit conversion, CV-only DAC0/DAC1 enforcement, 3-attempt verify on shutdown, LJM fault injection raising `AdapterError`, and Rig loop tick execution.
   - All tests passing with 0 failures. Local gate: `ruff`, `check_tests_first`, and `pytest` all green.
