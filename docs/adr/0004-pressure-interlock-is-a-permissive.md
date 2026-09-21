# ADR 0004 — The pressure interlock is a permissive for heater and QMS

- **Status:** Accepted
- **Date:** 2026-09-21

## Context

`DataAcquisition` compares every gauge reading against a literal `1e-4` labelled
Torr. The readings it compares are in the operator's **display unit**
(`FRG702Reader.read_all_with_status` converts to each gauge's `units`, default
`mbar`). In mbar the interlock trips at 7.5e-5 Torr, 25 % early; with Pa selected it
trips at once. A display setting silently moves a safety threshold. The QMS start
gate (`MainWindow._poll_qms_gate`) re-implements a pressure check separately.

## Decision

1. **Threshold: 1e-4 Torr**, a named constant in one config module, compared against
   pressure in Torr. Gauge readings are converted to Torr at the Rig module.
2. **Permissive, not just a trip.** The heater may not be energised, and a QMS scan
   may not be started, unless every enabled gauge has a valid reading below the
   threshold that is no older than 5 s.
3. **Trip on high** (`pressure_high`): any enabled gauge above threshold → instant
   cutoff (ADR 0003) and a QMS abort.
4. **Trip on stale** (`pressure_stale`): no valid reading from an enabled gauge for
   > **5 s** → same as high. Missing data is not safe data.
5. **The QMS abort runs on the GUI thread**, after the heater is already off. It is
   best-effort (it drives MASsoft by keypress) and its failure is reported, never
   swallowed.
6. **One gate.** The QMS start button and the heater both ask the same permissive.

## Consequences

- Changing the pressure display unit cannot change interlock behaviour; a test pins
  this for every unit.
- A disconnected gauge now stops a run within 5 s. That is intended.
