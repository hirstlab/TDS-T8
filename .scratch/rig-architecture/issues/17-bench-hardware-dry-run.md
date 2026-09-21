# 17: Bench — hardware dry run at ≤ 300 °C

**What to build:** Isaac runs a short low-temperature program on the real rig after the Program run is on the Rig loop and the GUI speaks in commands, and confirms the two symptoms that started this effort are gone.

**Blocked by:** 12

**Status:** ready-for-developer

Agents must not claim this ticket. Follow `AGENTS.md` §2–§3 wiring and CV-only rules.

- [ ] Peak temperature stays ≤ 300 °C
- [ ] For several sampled instants, the value on screen, the control TC in the CSV, and the program's setpoint tracking line up
- [ ] Unplugging and replugging the XGS-600 serial cable mid-run does not freeze the window (a `pressure_stale` trip is expected and correct)
- [ ] Findings written under `## Comments`

## Comments
