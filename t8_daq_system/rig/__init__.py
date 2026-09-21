"""
Rig module package.

Owns hardware communication, timing loop, Snapshot publication,
and Rig adapters (T8Adapter and SimulatedRig).
"""
from t8_daq_system.rig.adapter import AdapterError, RawReadings, RigAdapter
from t8_daq_system.rig.clock import Clock, ManualClock, RealClock
from t8_daq_system.rig.commands import (
    ConfirmContinue,
    LoadProgram,
    Nudge,
    ResetTrip,
    SelectAdapter,
    SetOutput,
    SetVoltage,
    StartProgram,
    StopProgram,
    UpdateConfig,
)
from t8_daq_system.rig.rig import Rig
from t8_daq_system.rig.simulated import SimulatedRig
from t8_daq_system.rig.t8_adapter import T8Adapter
from t8_daq_system.rig.snapshot import (
    HeaterStatus,
    ProgramStatus,
    Snapshot,
    SourceStatus,
)

__all__ = [
    "AdapterError",
    "Clock",
    "ConfirmContinue",
    "HeaterStatus",
    "LoadProgram",
    "ManualClock",
    "Nudge",
    "ProgramStatus",
    "RawReadings",
    "RealClock",
    "ResetTrip",
    "Rig",
    "RigAdapter",
    "SelectAdapter",
    "SetOutput",
    "SetVoltage",
    "SimulatedRig",
    "Snapshot",
    "SourceStatus",
    "StartProgram",
    "StopProgram",
    "T8Adapter",
    "UpdateConfig",
]
