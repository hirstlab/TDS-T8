# 05: GUI reads the Rig, not the hardware

**What to build:** The app runs on the Rig. `DataAcquisition` stops being the thing that reads hardware; the Rig (with the T8 adapter, or the Simulated rig in practice) does, on its own thread. The window renders from `rig.latest()` and never calls hardware, so an XGS or LabJack reconnect can no longer freeze it. The executor reads the control TC from the latest Snapshot, so the number on screen, the number the PID used and the number logged for an instant are the same number.

**Blocked by:** 03, 04

**Status:** done

**Read** `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`, `AGENTS.md` §12.1 and `.scratch/rig-architecture/spec.md` (The Rig loop; GUI; Ordering constraints) **first.** `docs/adr/0001-tests-first-and-no-muted-failures.md` is binding.

Requirements:

- `MainWindow` constructs one `Rig` at startup and starts its thread. Adapter = `T8Adapter`, or `SimulatedRig` when practice mode is on (practice toggle submits `SelectAdapter`).
- `_update_gui` reads `rig.latest()` and renders. Remove from the Tk thread: `LabJackConnection.connect()` / `_connect_xgs600()` reconnects, idle PS polling, and the `_check_connections` hardware reads. Connection indicators come from the Snapshot's `SourceStatus`.
- `_initialize_hardware_readers` no longer swaps reader objects under a running acquisition thread; reader construction lives in the adapter.
- `ProgramExecutor` keeps running (it is replaced in ticket 10) but its temperature source becomes the latest Snapshot's control TC (converted to K at the one existing conversion point), not its own `ThermocoupleReader.read_single` call. Its voltage writes still go through the power-supply object it holds today — **transitional**, say so in its docstring.
- CSV rows are built from the Snapshot handed on by the Rig (step 7), not from separate reads. Today's row-building closure may remain for now but must read only the Snapshot.
- `DataAcquisition` is no longer started. Leave the module in place (deleted in ticket 14).
- Introduce `tests/unit/test_architecture_rules.py` (walks the package with `ast`) with the two rules this ticket makes true: `labjack`/`serial` imported only under `hardware/`; `t8_daq_system.hardware` imported only under `rig/` **and** the transitional importers that still exist (list them explicitly in the test with a comment naming the ticket that removes each). No `tkinter`/`gui` imports under `control/`, `data/`, `rig/`, `settings/`.
- The pressure interlock check moves off the acquisition thread; until ticket 08 it reads Torr from the Snapshot and keeps today's behaviour (supply off, executor stopped) — but stops the executor **before** turning the supply off, and runs the pyautogui MASsoft abort on the Tk thread, not the Rig thread.

- [x] A test with a Tk-less harness (or `MainWindow` with a stub root as existing GUI tests do) shows `_update_gui` makes no adapter/hardware call
- [x] A test proves the executor's control temperature for a tick equals the Snapshot's value for that tick
- [x] A test proves the pressure-interlock path stops the executor before the supply-off write, and compares in Torr
- [x] `test_architecture_rules.py` exists with the rules above and passes
- [x] `ruff check .`, `python scripts/check_tests_first.py` and `pytest --tb=short -q` all pass

## Comments

- 2026-09-22: Ticket implemented and verified.
  - `MainWindow` constructs and starts a single `Rig` background thread with `T8Adapter` (or `SimulatedRig` in practice mode). `_toggle_practice_mode` dispatches `SelectAdapter`.
  - `_update_gui` decoupled completely from hardware: removed reconnect polling, direct PS polling, and `_check_connections()`. All connection indicators render from `Snapshot.source_status`.
  - Added `_on_snapshot` callback on `MainWindow` (invoked at Rig loop step 7) to append to `DataBuffer`, log CSV rows from the Snapshot, update latest sensor cache, and check pressure interlock in Torr.
  - `ProgramExecutor` updated with `rig` parameter / `set_rig()` to read control thermocouple temperature from latest Snapshot in K (`WHY THIS EXISTS` transitional docstring added).
  - Pressure interlock orders safety actions: stops `ProgramExecutor` before commanding power supply output off, and marshals pyautogui abort to Tk thread via `root.after`.
  - Created `tests/unit/test_architecture_rules.py` enforcing AST boundary rules across modules.
  - Created `tests/unit/test_gui_reads_rig.py` verifying Tk `_update_gui` hardware isolation, `ProgramExecutor` snapshot reading in K, and pressure interlock shutdown sequence in Torr.
  - All gates passed: `ruff check .` (0 errors), `check_tests_first.py` (PASS), `pytest` (303 passed).
