"""
T8 hardware adapter implementing RigAdapter for live LabJack, Keysight, and XGS-600 hardware.

WHY THIS EXISTS
---------------
Previously, four separate threads (GUI, DAQ, executor, and safety rampdown) performed
hardware I/O independently with no owner or synchronization. Gauge readings were converted
to display units (mbar or Pa) at the reader level, causing the pressure interlock to compare
different physical pressures against the 1e-4 threshold depending on the operator's display
selection (ADR 0004).

T8Adapter wraps LabJackConnection, ThermocoupleReader, FRG702Reader/FRG702AnalogReader,
XGS600Controller, and KeysightAnalogController behind the RigAdapter seam.
- All gauge readings leave read() in canonical Torr.
- CV-only is strictly enforced: write_voltage commands DAC0 only; DAC1 is pinned to full scale
  (180 A) via pin_current_limit() on connect/reconnect and never ramped.
- set_output(False) keeps the 3-attempt verify on the FIO1 Shut Off pin.
- Link and hardware errors raise AdapterError; no exceptions are swallowed.
- Serial request/response communication to the XGS-600 is serialized by construction
  because only the single Rig loop thread calls the adapter (ADR 0002).
"""
from __future__ import annotations

import logging
from typing import Any

from t8_daq_system.hardware.frg702_reader import (
    STATUS_VALID,
    FRG702AnalogReader,
    FRG702Reader,
)
from t8_daq_system.hardware.keysight_analog_controller import KeysightAnalogController
from t8_daq_system.hardware.labjack_connection import LabJackConnection
from t8_daq_system.hardware.thermocouple_reader import ThermocoupleReader
from t8_daq_system.hardware.xgs600_controller import XGS600Controller
from t8_daq_system.rig.adapter import AdapterError, RawReadings, RigAdapter
from t8_daq_system.settings.safety_limits import DAC0_MAX_V

logger = logging.getLogger(__name__)


class T8Adapter(RigAdapter):
    """
    Live hardware adapter for LabJack T8, Keysight N5700 power supply, and FRG-702 gauges.

    Implements the RigAdapter protocol for execution within the single-threaded Rig loop.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        connection: LabJackConnection | None = None,
        tc_reader: ThermocoupleReader | None = None,
        frg_reader: FRG702Reader | FRG702AnalogReader | None = None,
        ps_controller: KeysightAnalogController | None = None,
        xgs_controller: XGS600Controller | None = None,
    ) -> None:
        self._config = config or {}
        self._connection = connection if connection is not None else LabJackConnection()
        self._tc_reader = tc_reader
        self._frg_reader = frg_reader
        self._ps_controller = ps_controller
        self._xgs_controller = xgs_controller

        self._connected = False
        self._voltage_setpoint = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # RigAdapter protocol implementation
    # ──────────────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Connect to LabJack T8 and XGS-600 controller, and initialize hardware readers.

        Returns True on success, False if connection failed.
        """
        try:
            if not self._connection.is_connected():
                if not self._connection.connect():
                    logger.error("Failed to connect to LabJack T8")
                    self._connected = False
                    return False

            handle = self._connection.get_handle()
            tc_configs = self._config.get("thermocouples", [])
            if self._tc_reader is None:
                self._tc_reader = ThermocoupleReader(handle, tc_configs)

            # Initialize FRG-702 gauge reader (XGS-600 serial or T8 analog)
            frg_configs = self._config.get("frg702_gauges", [])
            frg_interface = self._config.get("frg_interface", "XGS600")

            if frg_interface == "Analog":
                if self._frg_reader is None and frg_configs:
                    self._frg_reader = FRG702AnalogReader(handle, frg_configs)
            else:
                xgs_config = self._config.get("xgs600", {})
                if xgs_config.get("enabled", True):
                    if self._xgs_controller is None:
                        self._xgs_controller = XGS600Controller(
                            port=xgs_config.get("port", "COM4"),
                            baudrate=xgs_config.get("baudrate", 9600),
                            timeout=xgs_config.get("timeout", 1.0),
                            address=xgs_config.get("address", "00"),
                            debug=False,
                        )
                    if not self._xgs_controller.is_connected():
                        self._xgs_controller.connect(silent=True)

                    if self._frg_reader is None and frg_configs:
                        self._frg_reader = FRG702Reader(self._xgs_controller, frg_configs)

            # Initialize Keysight power supply controller
            ps_config = self._config.get("power_supply", {})
            if self._ps_controller is None and ps_config.get("enabled", True):
                self._ps_controller = KeysightAnalogController(
                    handle,
                    rated_max_volts=ps_config.get("rated_max_volts", 6.0),
                    rated_max_amps=ps_config.get("rated_max_amps", 180.0),
                    voltage_limit=ps_config.get("default_voltage_limit", 6.0),
                    current_limit=ps_config.get("default_current_limit", 180.0),
                    voltage_pin=ps_config.get("voltage_pin", "DAC0"),
                    current_pin=ps_config.get("current_pin", "DAC1"),
                    voltage_monitor_pin=ps_config.get("voltage_monitor_pin", "AIN4"),
                    current_monitor_pin=ps_config.get("current_monitor_pin", "AIN5"),
                    switch_4_position="down",
                    debug=False,
                )

            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Error during T8Adapter connect: {e}", exc_info=True)
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect LabJack and XGS-600 controllers."""
        self._connected = False
        try:
            if self._xgs_controller is not None and self._xgs_controller.is_connected():
                self._xgs_controller.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting XGS-600: {e}")

        try:
            if self._connection is not None and self._connection.is_connected():
                self._connection.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting LabJack: {e}")

    def is_connected(self) -> bool:
        """Return True if LabJack connection is active."""
        return self._connected and self._connection.is_connected()

    def read(self) -> RawReadings:
        """
        Read all inputs for one tick.

        Returns RawReadings. Raises AdapterError on link failure.
        """
        if not self.is_connected():
            raise AdapterError("T8Adapter is not connected to LabJack T8")

        tc_c: dict[str, float | None] = {}
        tc_raw_v: dict[str, float | None] = {}

        if self._tc_reader is not None:
            try:
                tc_c = self._tc_reader.read_all()
                raw_diff = self._tc_reader.read_raw_voltages()
                # Map raw voltages back to standard sensor names
                for name in tc_c:
                    tc_raw_v[name] = raw_diff.get(f"{name}_rawV")
            except Exception as e:
                logger.error(f"Failed to read thermocouples: {e}")
                raise AdapterError(f"Failed to read thermocouples from LabJack T8: {e}") from e

        pressure_torr: dict[str, float | None] = {}
        pressure_valid: dict[str, bool] = {}

        if self._frg_reader is not None:
            try:
                details = self._frg_reader.read_all_with_status()
                for name, info in details.items():
                    p = info.get("pressure")
                    status = info.get("status")
                    pressure_torr[name] = p
                    pressure_valid[name] = (status == STATUS_VALID and p is not None)
            except Exception as e:
                logger.error(f"Failed to read pressure gauges: {e}")
                raise AdapterError(f"Failed to read pressure gauges: {e}") from e

        ps_volts = 0.0
        ps_amps = 0.0
        shutoff_readback = False

        if self._ps_controller is not None:
            try:
                v = self._ps_controller.get_voltage()
                a = self._ps_controller.get_current()
                if v is None or a is None:
                    raise AdapterError("Failed to read power supply monitor voltages from LabJack T8")
                ps_volts = v
                ps_amps = a
                shutoff_readback = self._ps_controller.is_output_on()
            except Exception as e:
                if isinstance(e, AdapterError):
                    raise
                logger.error(f"Failed to read power supply monitors: {e}")
                raise AdapterError(f"Failed to read power supply monitors from LabJack T8: {e}") from e

        return RawReadings(
            tc_c=tc_c,
            tc_raw_v=tc_raw_v,
            pressure_torr=pressure_torr,
            pressure_valid=pressure_valid,
            ps_volts=ps_volts,
            ps_amps=ps_amps,
            shutoff_readback=shutoff_readback,
        )

    def write_voltage(self, volts: float) -> None:
        """
        Write voltage setpoint to DAC0 only (CV-only control).

        Raises AdapterError on hardware failure.
        """
        if not self.is_connected() or self._ps_controller is None:
            raise AdapterError("Cannot write voltage: T8Adapter is not connected")

        clamped = max(0.0, min(float(volts), DAC0_MAX_V))
        try:
            success = self._ps_controller.set_voltage(clamped)
            if not success:
                raise AdapterError(f"Failed to write voltage {clamped:.3f} V to DAC0 on LabJack T8")
            self._voltage_setpoint = clamped
        except Exception as e:
            if isinstance(e, AdapterError):
                raise
            raise AdapterError(f"Error writing voltage {clamped:.3f} V to DAC0: {e}") from e

    def set_output(self, enabled: bool) -> None:
        """
        Set Shut-Off pin state (enabled=True de-asserts Shut Off, False asserts).

        set_output(False) keeps the 3-attempt verify loop in KeysightAnalogController.output_off().
        Raises AdapterError on hardware failure.
        """
        if not self.is_connected() or self._ps_controller is None:
            raise AdapterError("Cannot set output: T8Adapter is not connected")

        try:
            if enabled:
                success = self._ps_controller.output_on()
            else:
                success = self._ps_controller.output_off()

            if not success:
                raise AdapterError(f"Failed to set output enabled={enabled} on LabJack T8")
        except Exception as e:
            if isinstance(e, AdapterError):
                raise
            raise AdapterError(f"Error setting output enabled={enabled} on LabJack T8: {e}") from e

    def pin_current_limit(self) -> None:
        """
        Pin DAC1 (current limit) to full scale (180 A / 5.0 V).

        Called on connect/reconnect only to enforce CV-only operation.
        This is the ONLY DAC1 write in the entire adapter.
        Raises AdapterError on hardware failure.
        """
        if not self.is_connected() or self._ps_controller is None:
            raise AdapterError("Cannot pin current limit: T8Adapter is not connected")

        try:
            success = self._ps_controller.set_current(self._ps_controller.rated_max_amps)
            if not success:
                raise AdapterError("Failed to pin current limit (DAC1) on LabJack T8")
        except Exception as e:
            if isinstance(e, AdapterError):
                raise
            raise AdapterError(f"Error pinning current limit (DAC1) on LabJack T8: {e}") from e
