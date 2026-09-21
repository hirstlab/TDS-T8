# 18: Bench — trip drills on the rig

**What to build:** Isaac proves on hardware that each loss-of-signal case cuts the heater with the right reason and that reset behaves as ADR 0003 specifies.

**Blocked by:** 15

**Status:** ready-for-developer

Agents must not claim this ticket. Run at low temperature. Note: while the T8 USB link is down the T8 holds its last DAC0 value — see the spec's Further Notes on the T8 watchdog before this drill.

- [ ] Control TC lead unplugged mid-ramp → `control_tc_stale` within ~5 s, output off, reason on screen and in CSV
- [ ] XGS cable unplugged → `pressure_stale`, output off, QMS start refused
- [ ] T8 USB cable pulled → `labjack_lost`; on reconnect the supply is forced off first and the program does not resume
- [ ] For each: reset refused while the condition persists, accepted after it clears
- [ ] Findings written under `## Comments`

## Comments
