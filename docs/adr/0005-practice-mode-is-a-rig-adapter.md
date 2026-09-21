# ADR 0005 — Practice mode is a Simulated rig adapter, not flags in control code

- **Status:** Accepted
- **Date:** 2026-09-21

## Context

Practice mode is ~33 `practice_mode` references across `main_window.py`,
`program_executor.py` and `data_acquisition.py`. It is not faithful to live mode:

- In a `temp_ramp` block it **replaces the PID output with a synthetic "demo
  voltage"** (`_sp_fraction * 5.5 + _error_k * 0.008 + noise`), so practice runs never
  exercise the PID or the Feedforward map.
- Its thermal model is a 20 s first-order lag toward the *setpoint*, not a response
  to voltage, and lives inside the executor.
- It skips the cold-tungsten current guard and the interlock check.
- A physical model, `tests/simulation/tungsten_thermal_model.py` (`TungstenSim`),
  already exists but only the tests use it.

A standing lesson for this repository: practice mode must use the same scaling
functions as live mode, and bugs found only on hardware are unacceptably costly.

## Decision

1. **Practice mode = the Rig module running the Simulated rig adapter.** No module
   other than the Rig module knows which adapter is in use. No `practice_mode`
   branch exists in control, safety, Heater output, Program run or Run record code.
2. **The Simulated rig is physical:** commanded voltage → current and temperature
   through `TungstenSim` (moved into the application package), TC readings derived
   from simulated temperature for the primary TC only, gauges reporting a
   configurable pressure. It honours Shut Off and CV-only exactly as the Keysight
   does.
3. **Injectable clock.** In the GUI the clock is real time. In tests it is advanced
   explicitly, so a full multi-hour Program runs in seconds. This is the accelerated
   simulation harness — there is one simulator, not two.
4. **Fault injection** is a Simulated-rig feature: drop a TC, stall or drop a gauge,
   make a DAC write fail, lose the LabJack.
5. **Selection:** the practice toggle stays in the GUI and is **disabled while a run
   or logging is active**. Toggling swaps the adapter while idle.

## Consequences

- Practice runs now show the real controller's behaviour, including its failures.
- Plots in practice mode will look less tidy than the demo voltage made them.
