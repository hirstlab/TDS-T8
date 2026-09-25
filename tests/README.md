# TDS-T8 Test Suite

## Quick start

```bash
pytest                          # Runs all tests (integration + fault + unit)
pytest -m simulation            # Layer 2: accelerated thermal sim (slower)
pytest -m "not slow"            # Skip very slow tests
```

## Test layers

| Layer | Location | Marker | What it covers |
|-------|----------|--------|----------------|
| 1 -- Block transitions | `tests/integration/` | `integration` | Every 2/3-block combo, regression bugs |
| 2 -- Thermal sim | `tests/simulation/` | `simulation` | Accelerated 8-hour profile, PID tracking |
| 3 -- Fault injection | `tests/fault_injection/` | `fault` | SO latch, OVP, comms timeout, output-off mid-run |
| 4 -- Invariants | `tests/integration/test_state_invariants.py` | `integration` | Per-tick safety property checks |

## Pre-deployment gate

Before any hardware run longer than 1 hour:

```powershell
.\scripts\test_predeploy.ps1
```

Or manually:

```bash
pytest tests/integration/ tests/fault_injection/ -v   # ~2 min
pytest tests/simulation/ -m simulation -v              # ~1 min
```

## What each layer catches

- **Layer 1**: Block-transition bugs (missing ramp-down after hold, on_complete firing too early)
- **Layer 2**: PID windup, overshoot, ramp tracking accuracy over a full profile
- **Layer 3**: PS fault recovery, GUI state desync after SO latch
- **Layer 4**: block_index going backwards, voltage commanded while PS is off

## Adding new tests

- New hardware mock methods: add to `SimulatedRig` in `t8_daq_system/rig/simulated.py`
