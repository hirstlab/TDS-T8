# ADR 0002 — One Rig module owns all hardware I/O, in a single loop

- **Status:** Accepted
- **Date:** 2026-09-21
- **Context source:** architecture review 2026-09-20; grilling 2026-09-21

## Context

Four threads perform hardware I/O today, with no owner:

- The **GUI thread** (`MainWindow._update_gui`, every `display_rate_ms`) runs
  blocking reconnects (`LabJackConnection.connect`, `_connect_xgs600`, whose serial
  timeout can stall for seconds), reads PS V/I while idle, and in
  `_check_connections` reads every TC and the XGS-600 on every idle tick.
- The **DAQ thread** (`DataAcquisition.start_fast_acquisition`) reads TCs, gauges and
  the PS every `sample_rate_ms`.
- The **executor thread** (`ProgramExecutor._run_loop`) reads the control TC with a
  *separate* hardware read (`DataAcquisition.get_tc_kelvin_by_name` →
  `ThermocoupleReader.read_single`), reads PS current, and writes DAC0 every 0.5 s.
- The **safety rampdown thread** (`SafetyMonitor._rampdown_loop`) writes DAC0.

Consequences observed or latent: UI freezes during reconnects; the PID and the CSV
see different temperatures for the same instant; reader objects replaced on the GUI
thread while the DAQ thread holds the old ones (the "gauge disconnects after
settings applied" family); interleaved request/response on the XGS-600 serial port,
which has no lock.

## Decision

1. **One Rig module owns the LabJack handle and the XGS-600 port.** It runs one
   thread. No other module imports `labjack.ljm` or `serial`, holds a handle, or
   calls a reader.
2. **Single loop.** Each Rig tick, in order: read all inputs → publish an immutable
   Snapshot → evaluate safety → on control ticks, step the Program → resolve the
   Heater output → write DAC0 / Shut Off. Control runs in lockstep with the data it
   logs; there is no separate program thread and no separate safety thread.
3. **Control step fixed at 0.5 s.** The Rig ticks at `sample_rate_ms`; the Program is
   stepped on the first tick at or after 0.5 s since the previous control step. PID
   gains were tuned at 0.5 s and stay valid when the sample rate changes.
4. **Everyone else reads Snapshots.** The GUI polls the latest Snapshot on its own
   timer and never blocks on hardware. The Run record consumes every Snapshot.
5. **Reconnection lives inside the Rig module** and is reported as state
   (`connected` / `reconnecting` / `lost` per source). The GUI never calls
   `connect()`.
6. **Hardware behind an adapter seam** with two adapters — the T8 adapter and the
   Simulated rig (ADR 0005) — so the seam is real, not hypothetical.

## Consequences

- The GUI thread can no longer freeze on hardware.
- The PID, the safety check and the CSV row for a tick all use one Snapshot.
- A Program step that is slow delays the next sample. Block steps must be pure and
  fast; nothing in a step may do I/O.
- LJM is thread-safe at the library level, so this ADR is about logical ownership,
  ordering and staleness, not about preventing handle corruption. Do not
  "simplify" it back to a shared handle with a lock.
