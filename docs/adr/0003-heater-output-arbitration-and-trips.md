# ADR 0003 — One Heater output arbitrates voltage; every trip is an instant, latched cutoff

- **Status:** Accepted
- **Date:** 2026-09-21
- **Supersedes:** the 5-minute controlled ramp-down in `SafetyMonitor`
  (`RAMPDOWN_DURATION_SEC`, `_rampdown_loop`).

## Context

Five paths call `set_voltage` today with no priority between them: the program
executor, the safety rampdown thread, `MainWindow._handle_safety_shutdown`
(→ `emergency_shutdown`), `MainWindow._on_pressure_interlock` (runs on the DAQ
thread), and the manual nudge. Each safety path has an ordering defect:

- Over-temperature: the rampdown thread starts, but the executor is stopped only
  when the GUI thread reaches its `after(0)` handler; until then the executor keeps
  writing its PID voltage every 0.5 s.
- `_handle_safety_shutdown` calls `emergency_shutdown()` directly, cutting off the
  rampdown `SafetyMonitor` just started.
- The pressure interlock turns the supply off and *then* stops the executor, so one
  more executor tick can write voltage back; it also runs pyautogui with `sleep` on
  the acquisition thread.
- If the control TC read returns `None` mid-ramp, `ProgramExecutor._execute_block`
  raises, `_run_loop` catches it, the thread ends — and DAC0 stays at its last value.

Separately, the operator asked that every trip's reason be well documented in the
logs and presented on screen.

## Decision

1. **The Heater output is the only writer of DAC0 and the Shut Off pin.** It
   receives heater requests tagged **Safety > Operator > Program** and emits one
   commanded state per control step to the Rig module.
2. **Every trip is an instant cutoff:** Shut Off asserted and DAC0 = 0 V, in the same
   Rig tick the trip is detected. No ramp-down exists.
3. **DAC1 is not touched by a trip.** It stays pinned at full scale (CV-only). A trip
   removes power via Shut Off and DAC0; zeroing the current limit adds nothing and
   violates the invariant.
4. **Trips latch.** After a trip, Operator and Program requests are ignored until the
   operator resets. Reset is refused while the tripping condition is still present.
   A trip always stops the Program run; it never resumes.
5. **Trip kinds** (each with exactly one reason string naming sensor, value, limit
   and time):
   - `temp_limit` — a TC at or above its configured per-sensor limit
   - `temp_override` — any TC at or above 2200 °C
   - `pressure_high` — ADR 0004
   - `pressure_stale` — ADR 0004
   - `control_tc_stale` — the running block's control TC invalid for > **5 s**
   - `labjack_lost` — the Rig adapter reports the T8 unreachable. The DAC cannot be
     commanded while the link is down, so the Rig keeps reconnecting and its **first
     action on reconnect is Shut Off asserted + DAC0 = 0**
   - `program_error` — any exception raised by a block step
6. **A failed hardware write is a fault, not a print.** A failed Shut Off assertion
   is reported as the most severe state the operator can see.
7. **Trip reason is recorded and shown.** The Run record writes an event row and
   carries `Heater_State` and `Trip_Reason` on every data row. The GUI shows a
   non-modal banner with the reason until reset. No `messagebox` is ever raised from
   a non-GUI thread.
8. **Limits are compared in canonical units** (°C for temperature, Torr for
   pressure), never in display units.

## Consequences

- One small module holds the rule "what happens when two things want the heater",
  and it is testable without hardware or Tk.
- Losing the ramp-down means a trip at high temperature drops power abruptly. The
  operator chose this: tungsten cools itself, and a cutoff is easier to reason about
  than a ramp that competes with other writers.
