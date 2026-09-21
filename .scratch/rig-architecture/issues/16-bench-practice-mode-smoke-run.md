# 16: Bench — practice-mode smoke run

**What to build:** Isaac runs a real program he would use on the rig (e.g. open-loop voltage ramp to ~200 °C, then a 5 K/min temp ramp, then a hold) in practice mode in the built app, and checks that it behaves like the rig: the plot, the CSV and the heater state agree and Stop ends the run cleanly. (Fault injection is exercised by the automated tests; no developer fault menu is built in this effort.)

**Blocked by:** 13

**Status:** ready-for-developer

Agents must not claim this ticket.

- [ ] Program runs to completion in practice mode without freezing the window
- [ ] CSV has the expected columns, `Heater_State`, `Trip_Reason`, and event rows
- [ ] Pressing Stop mid-run ends the program, output goes off, and a `PROGRAM_STOPPED` event row is written
- [ ] Findings (pass, or what went wrong) written under `## Comments`

## Comments
