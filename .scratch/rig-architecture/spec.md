# Spec: Rig architecture — one owner of hardware, one writer of the heater, a faithful simulator

Status: ready-for-agent
Date: 2026-09-21
Blocked by: `.scratch/workflow-setup/` (CI green on `main`)
Related: `docs/adr/0002-one-rig-module-owns-hardware-single-loop.md`,
`docs/adr/0003-heater-output-arbitration-and-trips.md`,
`docs/adr/0004-pressure-interlock-is-a-permissive.md`,
`docs/adr/0005-practice-mode-is-a-rig-adapter.md`,
`docs/adr/0001-tests-first-and-no-muted-failures.md`,
`CONTEXT.md` (Acquisition; Control; Heater output and safety; Records and modes)

> Read ADRs 0002–0005 before any ticket in this effort. They record the decisions
> made in grilling on 2026-09-21 and are not open for re-litigation inside a ticket.
> ADR 0001 is binding on all test work: a failing test is fixed or escalated, never
> muted.

## Problem Statement

The application glitches during runs: the window freezes, readings on screen and in
the CSV do not line up, and things break after settings are applied or a device
reconnects. An architecture review on 2026-09-20 traced this to structure, not to
individual bugs.

**No module owns the hardware.** Four threads perform hardware I/O: the Tk thread
(`MainWindow._update_gui` — reconnects via `LabJackConnection.connect()` and
`_connect_xgs600()`, idle PS polling, and `_check_connections` reading every TC and
gauge each tick), the acquisition thread (`DataAcquisition.start_fast_acquisition`),
the executor thread (`ProgramExecutor._run_loop`, which reads the control TC through
its own `ThermocoupleReader.read_single` call and reads PS current), and the safety
rampdown thread (`SafetyMonitor._rampdown_loop`). A serial timeout on reconnect
freezes the window. The PID and the CSV see different temperatures for the same
instant. `_initialize_hardware_readers` replaces reader objects on the Tk thread
while the acquisition thread still holds the old ones. The XGS-600's
request/response serial link has no lock.

**No module owns the heater.** Five paths call `set_voltage` with no priority: the
executor, the rampdown thread, `_handle_safety_shutdown`, `_on_pressure_interlock`,
and `_nudge_voltage`. The over-temperature rampdown competes with an executor that
is stopped only when the Tk thread reaches an `after(0)` callback.
`_handle_safety_shutdown` calls `emergency_shutdown()` and cuts off the rampdown the
monitor just started. `_on_pressure_interlock` runs on the acquisition thread, turns
the supply off *before* stopping the executor (one more tick can write voltage
back), and runs pyautogui with `sleep` there, pausing acquisition.

**A lost thermocouple leaves the heater on.** If the control TC returns `None`
mid-ramp, `_execute_block` raises inside `self._pid.compute`, `_run_loop` catches it
and ends the thread, and DAC0 stays at its last value with nothing regulating it.

**The pressure interlock depends on a display setting.** `DataAcquisition`
compares against a literal `1e-4` labelled Torr, but receives pressure in each
gauge's display unit (default mbar): it trips 25 % early in mbar and immediately in
Pa.

**Practice mode does not test the controller.** In a `temp_ramp` block it replaces
the PID output with a synthetic demo voltage; its thermal model lags toward the
setpoint rather than responding to voltage; it skips the current guard and the
interlock check; ~33 `practice_mode` references thread through three files. A
physical model (`tests/simulation/tungsten_thermal_model.py`, `TungstenSim`) exists
but only tests use it.

**Failures are silent.** 62 exception handlers whose entire body is `pass`, including the
executor's current-guard read, the DAC-write failure path, and the supply shutdown
in both safety handlers. A failed `set_voltage` prints and the loop carries on.

**The hot spots cannot be tested faster than real time.** `_execute_block` is a
~220-line loop mixing PID, feedforward, practice simulation, the current guard,
hardware writes, scheduler logging state, per-tick `print`, and `time.sleep(0.5)`.
`main_window.py` is 3 088 lines and builds every CSV row inside a closure running on
the acquisition thread, computing `Block_Index` in three places.

## Solution

Five deep modules replace the shared-everything structure.

1. **Rig module** — owns the LabJack handle and XGS-600 port on one thread. Each Rig
   tick reads every input and publishes an immutable **Snapshot**; on control steps
   (every 0.5 s) it steps the Program and applies the Heater output, then writes.
   Reconnection lives inside it. The Tk thread only reads the latest Snapshot and
   submits commands.
2. **Heater output** — the only writer of DAC0 and Shut Off. Arbitrates heater
   requests Safety > Operator > Program; every trip is an instant, latched cutoff
   with a recorded, displayed reason; enforces CV-only.
3. **Simulated rig** — the second Rig adapter. Practice mode and the test harness are
   the same simulator: voltage → current → temperature through `TungstenSim`, with
   an injectable clock and fault injection.
4. **Program run** — advances blocks on control steps using pure **block steps**
   that take a Snapshot and elapsed time and return a voltage request. No clock, no
   sleep, no hardware inside a step.
5. **Run record** — turns Snapshots and events into CSV rows and event rows; owns
   the column schema; writes on its own thread from a queue.

`main_window.py` keeps widgets and wiring.

## User Stories

1. As the operator, I want the window to stay responsive while a device reconnects,
   so that I can always see the rig and press Stop.
2. As the operator, I want the number on screen, the number the PID used, and the
   number in the CSV for a given instant to be the same number.
3. As the operator, I want any trip to cut the heater in the same tick it is
   detected, so that nothing else can write voltage after a safety decision.
4. As the operator, I want every trip's reason shown on screen until I reset and
   written in the log, so that I know exactly what happened and when.
5. As the operator, I want reset refused while the tripping condition is still
   present, so that I cannot re-energise into the same fault.
6. As the operator, I want the heater cut if the control thermocouple stops reading
   for 5 s, so that an unattended ramp never runs open-loop.
7. As the operator, I want the heater and the QMS locked out unless the chamber
   pressure is valid, fresh, and below 1e-4 Torr, whatever unit I display pressure
   in.
8. As the operator, I want a gauge that stops reporting for 5 s treated as a trip,
   because missing data is not safe data.
9. As the operator, I want a LabJack dropout to trip and latch, and on reconnect the
   supply forced off before anything else, so that a program never resumes by
   itself.
10. As the operator, I want a manual nudge during a program to take over from the
    program cleanly, and never to enable a disabled output.
11. As the operator, I want practice mode to run the real PID, feedforward, safety
    and logging code against a physical simulation, so that practice predicts the
    rig.
12. As the operator, I want the practice toggle disabled while running or logging,
    so that the hardware underneath a run cannot change.
13. As the experimenter, I want CSV logs to keep their existing columns and names,
    so that the feedforward map keeps ingesting old and new runs alike.
14. As the experimenter, I want `Heater_State` and `Trip_Reason` on every row and an
    event row for every trip, reset, block start and program end.
15. As a developer, I want a full multi-hour program to run in a test in seconds,
    against the same code paths the rig runs.
16. As a developer, I want to inject a TC dropout, a stale gauge, a failed DAC write,
    or a LabJack loss into that run.
17. As a developer, I want architecture rules — who may import hardware, who may
    write the heater, where `practice_mode` may appear, no swallowed exceptions —
    each stated once as a test over the whole package.
18. As a developer, I want the feedforward and PID behaviour that exists today
    preserved exactly through the refactor, pinned by tests before anything moves.

## Implementation Decisions

### Package layout

New package `t8_daq_system/rig/`:

- `clock.py` — `Clock` protocol with `now() -> float` and
  `sleep_until(t: float) -> None`; `RealClock` (wraps `time.monotonic` /
  `time.sleep`); `ManualClock` (tests; `advance(seconds)`; `sleep_until` returns
  immediately). Wall-clock
  timestamps for the CSV come from a separate `wall_time()` on the clock so tests
  control both.
- `snapshot.py` — frozen dataclasses: `Snapshot`, `SourceStatus`
  (`connected` / `reconnecting` / `lost`), `ProgramStatus`, `HeaterStatus`.
- `adapter.py` — `RigAdapter` protocol (below).
- `t8_adapter.py` — `T8Adapter`: wraps the existing `LabJackConnection`,
  `ThermocoupleReader`, `FRG702Reader`/`FRG702AnalogReader`, `XGS600Controller`,
  `KeysightAnalogController`. The only place those classes are constructed.
- `simulated.py` — `SimulatedRig`.
- `tungsten_model.py` — `TungstenSim`, moved from
  `tests/simulation/tungsten_thermal_model.py`; the test module re-imports from here.
- `rig.py` — `Rig`: the thread, the loop, the command queue, reconnection, adapter
  selection.

Also new: `t8_daq_system/control/heater_output.py`, `t8_daq_system/control/block_steps.py`,
`t8_daq_system/control/program_run.py`, `t8_daq_system/data/run_record.py`,
`t8_daq_system/settings/safety_limits.py`.

Retired by the end of the effort: `core/data_acquisition.py`,
`control/program_executor.py` (replaced by `program_run.py` + `block_steps.py`),
the rampdown code in `control/safety_monitor.py`, `MockPowerSupply` in
`gui/main_window.py`, and every `practice_mode` branch outside `rig/`.

**Import rule** (enforced by a test): `t8_daq_system.hardware` is imported only by
`t8_daq_system.rig`. `labjack` and `serial` are imported only by
`t8_daq_system.hardware`. `control/`, `data/`, `rig/` never import `tkinter` or
`gui/`.

### Every number has one home

`t8_daq_system/settings/safety_limits.py` holds, as named module constants:

| Name | Value | Why |
|---|---|---|
| `CONTROL_PERIOD_S` | `0.5` | PID gains tuned at 0.5 s (ADR 0002) |
| `STALE_ALLOWANCE_S` | `5.0` | control TC and pressure (ADR 0003, 0004) |
| `PRESSURE_INTERLOCK_TORR` | `1e-4` | ADR 0004 |
| `TEMP_OVERRIDE_C` | `2200.0` | existing `SafetyMonitor.TEMP_OVERRIDE_LIMIT` |
| `TEMP_OVERRIDE_RESET_C` | `2150.0` | existing `TEMP_RESTART_THRESHOLD`; reset hysteresis |
| `DAC0_MAX_V` | `6.0` | CV-only clamp |
| `COLD_CURRENT_LIMIT_A` | `180.0` | existing cold-tungsten guard |
| `RECONNECT_INTERVAL_S` | `30.0` | existing `_reconnect_interval` |

Per-sensor temperature limits, warning threshold and debounce count stay
operator-configurable where they are today (`SafetyMonitor.set_temperature_limit`,
`set_warning_threshold`, `set_debounce_count`).

### The Rig adapter seam

`RigAdapter` is a `typing.Protocol` with exactly these operations:

- `connect() -> bool`, `disconnect() -> None`, `is_connected() -> bool`
- `read() -> RawReadings` — one call per tick; returns TC °C by name (None for
  invalid/open), raw TC voltages by name, gauge pressures **in Torr** by name with a
  per-gauge valid flag, PS measured volts and amps, Shut Off readback. Raises
  `AdapterError` on link failure.
- `write_voltage(volts: float) -> None` — DAC0 only. Raises `AdapterError`.
- `set_output(enabled: bool) -> None` — Shut Off pin (enabled = de-asserted).
  Raises `AdapterError`; `set_output(False)` keeps the existing 3-attempt verify.
- `pin_current_limit() -> None` — DAC1 to full scale. Called on connect and
  reconnect only.

No other method. The adapter does not know about Programs, trips or units other than
°C and Torr. `T8Adapter` converts gauge readings to Torr using the existing
`FRG702Reader.convert_pressure`; display-unit conversion moves out of the readers.

### The Rig loop

`Rig` runs one daemon thread whose body is a loop over `Rig.run_tick()` followed by
`clock.sleep_until(next_tick)`. Tests call `run_tick()` directly and never start the
thread. Tick period = `min(sample_rate_ms / 1000,
CONTROL_PERIOD_S)` — the default `sample_rate_ms` is 1000, so the loop ticks at
0.5 s and the control TC is fresh on every control step. Each tick, in this order:

1. Drain the command queue (thread-safe `queue.Queue`). Commands are frozen
   dataclasses: `LoadProgram`, `StartProgram`, `StopProgram`, `ConfirmContinue`,
   `Nudge(direction)`, `SetVoltage(volts)`, `SetOutput(enabled)`, `ResetTrip`,
   `SelectAdapter(practice: bool)`, `UpdateConfig(...)`.
2. If disconnected: attempt reconnect at most every `RECONNECT_INTERVAL_S`. On
   success the **first** writes are `set_output(False)`, `write_voltage(0.0)`,
   `pin_current_limit()`, before any read is trusted.
3. `adapter.read()`. On `AdapterError`: mark LabJack `lost`, raise a
   `labjack_lost` trip, skip to step 7.
4. Update per-source last-valid times; build and publish the `Snapshot`
   (stored as `self._latest` behind a lock; `Rig.latest()` returns it).
5. Safety evaluation → trips (pure function, below).
6. If ≥ `CONTROL_PERIOD_S` since the last control step: step the Program run →
   Program heater request; resolve the Heater output → commanded state; write it
   via the adapter. A write failure raises a trip of the matching kind
   (`labjack_lost` for link errors); a failed `set_output(False)` sets
   `HeaterStatus.shutoff_unverified = True`, the most severe state the GUI shows.
7. Hand the Snapshot to the Run record's queue.

The Tk thread never calls the adapter. `SelectAdapter` is rejected (with a reason
in the next Snapshot) while a Program runs or logging is active.

### The Snapshot

Fields, at minimum: `t` (clock), `wall_time`, `tc_c: Mapping[str, float | None]`,
`tc_raw_v`, `pressure_torr: Mapping[str, float | None]`, `source_age_s` per TC and
gauge, `ps_volts`, `ps_amps`, `commanded_volts`, `output_enabled`,
`labjack: SourceStatus`, `xgs: SourceStatus`, `heater: HeaterStatus` (state
`off` / `on` / `tripped`, active trip kind and reason, `shutoff_unverified`),
`program: ProgramStatus` (running, block index, block type, waiting for
confirmation, elapsed in block, setpoint K, and the scheduler values
`sched_kp`, `sched_ki`, `sched_kd`, `sched_zone`, `ff_voltage`, `pid_correction`),
`permissive_ok: bool`, `permissive_reason: str | None`, `adapter: "t8" | "simulated"`.

Temperature is °C in the Snapshot (the T8 EF register output). The Program run
converts to K at exactly one point, `control/block_steps.py:c_to_k`, replacing the
conversion now inside `DataAcquisition.get_tc_kelvin_by_name`.

### Safety evaluation

`SafetyMonitor` becomes a pure evaluator: `evaluate(snapshot, state) -> list[Trip]`
with no thread, no power-supply reference, no callbacks. It keeps per-sensor limits,
warning threshold and debounce semantics. Trip kinds and conditions:

- `temp_limit` — a TC ≥ its configured limit for `debounce_count` consecutive ticks
- `temp_override` — any TC ≥ `TEMP_OVERRIDE_C`
- `pressure_high` — any enabled gauge > `PRESSURE_INTERLOCK_TORR`
- `pressure_stale` — any enabled gauge with no valid reading for > `STALE_ALLOWANCE_S`
- `control_tc_stale` — while a closed-loop block runs, its control TC invalid for
  > `STALE_ALLOWANCE_S`
- `labjack_lost` — raised by the Rig loop, not the evaluator
- `program_error` — raised by the Program run when a block step raises

Warnings (below limit, above warning threshold) appear in the Snapshot and never
trip. The permissive (`permissive_ok`) is true only when every enabled gauge has a
valid reading ≤ `STALE_ALLOWANCE_S` old and below threshold.

### The Heater output

`HeaterOutput.resolve(requests, snapshot) -> HeaterCommand` where `HeaterCommand`
is `(output_enabled: bool, volts: float)`. It holds the latch. Rules, all tested
directly:

1. Any trip → `(False, 0.0)` this tick, latch set, trip kind + reason recorded.
   While latched, Operator and Program requests are ignored.
2. `ResetTrip` clears the latch only if the tripping condition is absent now
   (`temp_override` needs every TC < `TEMP_OVERRIDE_RESET_C`; staleness needs a
   fresh valid reading; `labjack_lost` needs a connected adapter). Otherwise the
   refusal reason is published.
3. Output may be enabled only by `StartProgram` or an explicit `SetOutput(True)`,
   and only when `permissive_ok` and not latched. **A nudge never enables output**
   (preserves FIX-3).
4. An Operator request (`Nudge`, `SetVoltage`) while a Program runs **stops the
   Program run first**, then applies. Operator outranks Program; there is no
   blending.
5. Every non-safety request passes the cold-tungsten guard: if
   `snapshot.ps_amps > COLD_CURRENT_LIMIT_A`, volts may not rise above the
   previous command.
6. Volts are clamped to `[0.0, DAC0_MAX_V]`. DAC1 is never commanded here.

There is no ramp-down. `SafetyMonitor._rampdown_loop`,
`_trigger_controlled_rampdown`, `RAMPDOWN_DURATION_SEC` and every GUI path that
reads rampdown progress are removed.

### Block steps and the Program run

`control/block_steps.py` defines one step function per block type:
`step_voltage_ramp`, `step_temp_ramp`, `step_stable_hold`. Each takes
`(block, temp_k, elapsed_s, now_s, ctx)` and returns
`StepResult(volts: float, finished: bool, sched: SchedValues)`, where `ctx` carries
the `PIDController`, the `FeedforwardMap`, the block's start temperature and rate.
A step performs no I/O, reads no clock, does not print, and never catches its own
exceptions.

`control/program_run.py` `ProgramRun` owns: the block list, current index,
block-start time and temperature, per-block gain resolution (today's
`_resolve_block_control`), bumpless transfer (`PIDController.reset_bumpless` with
the current commanded voltage), the FIX-2 two-second completion guard, run-history
saving (`_save_run_to_history`), and the QMS confirmation pause (a `ConfirmContinue`
command releases it). `ProgramRun.step(snapshot, now_s) -> heater request | None`
is called by the Rig loop on control steps. An exception from a block step becomes
a `program_error` trip with the exception type and message as its reason, and the
run ends.

The practice-mode demo voltage and the in-executor thermal lag are deleted, not
moved.

### Run record

`data/run_record.py` `RunRecord` owns a writer thread fed by a queue of Snapshots
and events, and wraps the existing `DataLogger` (header metadata and flushing stay
there). A pure function `build_row(snapshot, t_unit, p_unit) -> dict` produces each
row. A row is written every `sample_rate_ms`, not every tick.

Column contract: for a given configuration, the header is exactly the one today's
logging path produces (the sensor-name list built in `MainWindow` where logging
starts, ~line 2240: `Timestamp`, TC names, gauge names, `PS_Voltage`, `PS_Current`,
`PS_Voltage_Setpoint`, `PS_CC_Limit`, `Block_Index`, raw-voltage `_rawV` columns,
`Sched_Kp`, `Sched_Ki`, `Sched_Kd`, `Sched_Zone`, `FF_Voltage`, `PID_Correction`),
same names, same order — pinned by a characterisation test before `RunRecord`
replaces it.
Two columns are appended at the end: `Heater_State`, `Trip_Reason`.
`FeedforwardMap`'s CSV ingest (`_resolve_temp_col`, the `PS_Voltage_Setpoint` /
`PS_Voltage` resolution) must read new logs unchanged.

Event rows via `DataLogger.log_event`: `TRIP <kind>` (detail = reason), `RESET`,
`RESET_REFUSED`, `BLOCK_START <n> <type>`, `PROGRAM_COMPLETE`, `PROGRAM_STOPPED`,
`RAMP_START` (existing), `ADAPTER <t8|simulated>`.

### The Simulated rig

`SimulatedRig` implements `RigAdapter` over `TungstenSim` and the injected clock:
`write_voltage` sets the model's voltage; each `read()` advances the model to
`clock.now()`; current = V / R(T); the primary TC (config's first enabled TC)
reports model temperature; other TCs report room temperature; gauges report a
configurable pressure (default 1e-7 Torr). It honours `set_output(False)` (zero
current) and CV-only.

Fault injection methods (tests and a hidden developer menu only):
`drop_tc(name)`, `restore_tc(name)`, `set_pressure(name, torr)`,
`stall_gauge(name)`, `fail_next_write()`, `disconnect()`, `reconnect()`.

### GUI

- `_update_gui` reads `rig.latest()` and renders. No hardware call, no reconnect,
  no `_check_connections` hardware read remains in `main_window.py`.
- Trip: a non-modal banner showing kind and reason, and the Reset button, until
  reset succeeds. `messagebox` is never called from any thread but Tk's.
- The QMS start button asks `snapshot.permissive_ok`; `_poll_qms_gate`'s own
  pressure check is removed. On a `pressure_high` or `pressure_stale` trip, the Tk
  thread runs the existing MASsoft abort after the heater is already off; its
  failure is shown, not swallowed.
- The practice toggle submits `SelectAdapter` and is disabled while a Program runs
  or logging is active.
- Nudge, start, stop, confirm and reset submit commands.

### Ordering constraints for ticket-writing

- Characterisation tests of today's control math land **first**, against
  `ProgramExecutor`, before any control code moves.
- `Snapshot`, `Clock`, `RigAdapter`, `SimulatedRig` before the `Rig` loop.
- The `Rig` loop with `T8Adapter` replaces `DataAcquisition` before the Program run
  moves onto it.
- `HeaterOutput` and the pure safety evaluator can be built in parallel with the
  Rig loop; both must exist before the Program run moves onto the loop.
- Run record after the Rig loop publishes Snapshots.
- GUI rewiring after the modules it reads exist; dead-code removal last.
- Bench tickets (`ready-for-developer`) last.

## Testing Decisions

ADR 0001 is binding. Tests are written first and observed failing. A failing test
is fixed or escalated, never muted. **No test in this effort sleeps**: every
time-dependent module takes a `Clock`.

Tests assert on external behaviour: Snapshot contents, the voltage and output state
the adapter received, CSV rows and event rows, what the GUI renders. Not on private
attributes, and not on whether an internal method was called.

### 1. Characterisation first (before anything moves)

Pin today's behaviour so the refactor can be proven harmless (decided 2026-09-21:
the refactor preserves current PID + feedforward behaviour exactly):

- For `temp_ramp`, `stable_hold` and `voltage_ramp`, drive `ProgramExecutor` with a
  scripted temperature sequence and a patched clock (non-practice path, fake PS) and
  record the voltage written each tick, including across a block boundary
  (bumpless transfer) and the FIX-2 guard window. Store the expected sequences in the
  test file as literals. After the move, the same inputs through `ProgramRun` +
  block steps must produce the same sequence to within 1e-9 V.
- The CSV header for a representative configuration, written by today's path,
  stored as a literal.

These characterisation tests are the only tests in the effort allowed to reference
`ProgramExecutor`, and they are deleted together with it — after their assertions
have been re-pointed at `ProgramRun` and pass.

### 2. The integration seam: Rig + Simulated rig + ManualClock

A fixture builds a real `Rig` with a `SimulatedRig`, a `ManualClock`, a real
`HeaterOutput`, `SafetyMonitor`, `ProgramRun`, and a `RunRecord` writing to
`tmp_path`, and exposes `tick(n)` that advances the clock and calls `Rig.run_tick()` synchronously
(the thread is never started in tests). Everything above the adapter is real. Scenarios, each its own test:

- A three-block program (voltage ramp → temp ramp → stable hold) runs to completion
  in simulated hours; the CSV has one row per `sample_rate_ms` and the expected
  event rows.
- `drop_tc` on the control TC mid-ramp: no trip at 4.9 s, `control_tc_stale` trip at
  5.1 s; adapter sees `set_output(False)` and 0 V on that tick; program run ended;
  reason in Snapshot and in the CSV.
- `stall_gauge` → `pressure_stale` at 5.1 s; `set_pressure` above threshold →
  `pressure_high` on the next tick.
- `disconnect` → `labjack_lost`; `reconnect` → the first adapter calls are
  `set_output(False)`, `write_voltage(0.0)`, `pin_current_limit()`; program does not
  resume; reset accepted afterwards.
- `fail_next_write` on `set_output(False)` → `shutoff_unverified` in the Snapshot.
- Nudge during a running program → program stopped, operator voltage applied; nudge
  with output disabled → output stays disabled.
- Reset while the condition persists → refused with reason; after it clears →
  accepted.
- A block step that raises → `program_error` trip with the exception text.

### 3. Direct unit tests, no thread, no Tk, no hardware

- `HeaterOutput`: one test per rule 1–6 above; a property-style test over random
  request sequences asserting volts ∈ [0, 6] always and no request path exists that
  commands DAC1.
- Safety evaluator: each trip kind at, just below and just above its boundary;
  debounce; warnings never trip.
- **Pressure units:** the same physical pressure expressed in mbar, Torr and Pa
  display settings trips at the same Torr value — the regression test for the bug
  this effort found.
- Block steps: fed explicit (temp, elapsed) series, no clock.
- `build_row`: exact header and a row for a known Snapshot; `FeedforwardMap` ingests
  a CSV written by `RunRecord` (round trip).
- `SimulatedRig`: steady state for a fixed voltage matches
  `TungstenSim.steady_state_temp`; output disabled → zero current.

### 4. Architecture rules, each stated once over the whole package

The user asked for rules stated once across the app rather than repeated per
module. One test file, `tests/unit/test_architecture_rules.py`, walks the package
with `ast`:

- `labjack` and `serial` imported only under `t8_daq_system/hardware/`.
- `t8_daq_system.hardware` imported only under `t8_daq_system/rig/`.
- `tkinter` and `t8_daq_system.gui` never imported under `control/`, `data/`, `rig/`,
  `settings/`.
- The identifier `practice_mode` appears only under `rig/` and in
  `gui/main_window.py`'s toggle handler.
- Calls named `write_voltage`, `set_output`, `set_voltage`, `output_on`,
  `output_off`, `emergency_shutdown` appear only under `rig/` and `hardware/`.
- No `except` handler whose body is only `pass` (or `...`) anywhere under
  `t8_daq_system/`.
- The only `time.sleep` under `control/`, `data/run_record.py` and `rig/` is inside
  `RealClock.sleep_until`. Everything else waits through the `Clock`.

These rules are introduced in the ticket that first makes each one true, not
before, so the suite is never red on `main`.

## Out of Scope

- Changing PID gains, the feedforward algorithm, gain scheduling, or the itinerary
  system. Behaviour is pinned and preserved; tuning is separate work.
- The feedforward confidence indicator (FF-10) and camera panel changes.
- QMS data synchronisation or post-run RGA merge.
- Replacing Tkinter or matplotlib.
- The T8 hardware watchdog (see Further Notes).
- Changing the hardware wiring, SW1 switches, or pin assignments in `AGENTS.md` §3.
- Rewriting `AGENTS.md` §1–11; each ticket updates only the sections its change
  makes false, as §12.1 requires.

## Further Notes

**Bench verification is required and is Isaac's** (`ready-for-developer`):
1. Practice-mode smoke run of a real program after the Simulated rig lands.
2. Hardware dry run at low temperature (≤ 300 °C) after the Program run moves onto
   the Rig loop: confirm the CSV lines up with the screen and the window stays
   responsive during an XGS reconnect.
3. Trip drills on the rig: unplug the control TC lead, unplug the XGS cable, pull the
   T8 USB cable — each must cut output with the right reason, and reset must behave
   as specified.

**T8 watchdog.** While the USB link is down the T8 holds its last DAC0 value and the
software cannot command anything. The LabJack hardware watchdog can set outputs to a
safe state on communication timeout without software. Whether the T8 supports the
watchdog registers used on the T7 must be checked against LabJack's T8
documentation before any design; if it does, it is the only protection for this
case that does not depend on the software, and deserves its own ADR.

**AGENTS.md §6.3 is stale** (states Kp=1.0, Ki=0.05, Kd=0.05; code defaults are
0.02 / 0.0013 / 0.005). Flagged for Isaac; not changed here.

**Dead references.** `DataAcquisition.get_tc_kelvin_by_name` refers to a
`temp_ramp_executor` whose module no longer exists (only a stale `.pyc` remains).
It goes with `DataAcquisition`.
