"""
Rig adapter interface and data types.

WHY THIS EXISTS
---------------
Previously, hardware controllers and readers were instantiated directly in the GUI
and DAQ threads, tightly coupling the application to specific LabJack and serial
hardware. Practice mode introduced ad-hoc branching throughout control logic.

By defining a minimal, explicit RigAdapter protocol with exactly seven operations,
the rest of the application can run identically against live hardware (T8Adapter)
or a faithful physics simulation (SimulatedRig) without any practice_mode branches
in control or safety code (ADRs 0002, 0005).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


class AdapterError(Exception):
    """Raised when an adapter operation fails (e.g. link loss or hardware fault)."""
    pass


@dataclass(frozen=True)
class RawReadings:
    """
    Raw sensor and power supply readings from one read tick.

    tc_c: TC °C by name (None for invalid/open channel)
    tc_raw_v: raw TC voltages by name
    pressure_torr: gauge pressures in Torr by name
    pressure_valid: per-gauge boolean validity flag
    ps_volts: measured power supply output voltage
    ps_amps: measured power supply output current
    shutoff_readback: Shut Off pin readback (True = enabled / de-asserted, False = shut off)
    """

    tc_c: Mapping[str, float | None]
    tc_raw_v: Mapping[str, float | None]
    pressure_torr: Mapping[str, float | None]
    pressure_valid: Mapping[str, bool]
    ps_volts: float
    ps_amps: float
    shutoff_readback: bool


@runtime_checkable
class RigAdapter(Protocol):
    """
    Interface for hardware I/O and simulated rigs.

    Defines exactly the operations needed by the Rig loop.
    """

    def connect(self) -> bool:
        """Establish connection to the hardware or simulator. Returns True on success."""
        ...

    def disconnect(self) -> None:
        """Close connection to the hardware or simulator."""
        ...

    def is_connected(self) -> bool:
        """Return True if connection is currently active."""
        ...

    def read(self) -> RawReadings:
        """
        Read all inputs for one tick.

        Returns RawReadings. Raises AdapterError on link failure.
        """
        ...

    def write_voltage(self, volts: float) -> None:
        """
        Write voltage setpoint to DAC0 only (CV-only control).

        Raises AdapterError on hardware failure.
        """
        ...

    def set_output(self, enabled: bool) -> None:
        """
        Set Shut-Off pin state (enabled=True de-asserts Shut Off, False asserts).

        Raises AdapterError on hardware failure.
        """
        ...

    def pin_current_limit(self) -> None:
        """
        Pin DAC1 (current limit) to full scale.

        Called on connect/reconnect only to enforce CV-only operation.
        Raises AdapterError on hardware failure.
        """
        ...
