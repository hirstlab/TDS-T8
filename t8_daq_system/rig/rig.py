"""
Rig module — single owner of hardware communication, timing loop, and Snapshot publication.

WHY THIS EXISTS
---------------
Previously, four separate threads (GUI, DAQ, executor, and safety rampdown) performed
hardware I/O independently with no owner or synchronization. This caused UI lockups
during reconnects, race conditions between PID voltage writes and safety shutdowns,
and discrepancies between on-screen readings and recorded CSV logs.

The Rig module owns the hardware adapter on a single thread running a single loop:
drain commands -> reconnect safely -> read -> publish immutable Snapshot -> safety
-> control step & heater output -> hand Snapshot to Run record (ADRs 0002, 0003).
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Sequence

from t8_daq_system.rig.adapter import AdapterError, RawReadings, RigAdapter
from t8_daq_system.rig.clock import Clock
from t8_daq_system.rig.commands import (
    SelectAdapter,
    UpdateConfig,
)
from t8_daq_system.rig.simulated import SimulatedRig
from t8_daq_system.rig.snapshot import (
    HeaterStatus,
    ProgramStatus,
    Snapshot,
    SourceStatus,
)
from t8_daq_system.settings.safety_limits import (
    CONTROL_PERIOD_S,
    RECONNECT_INTERVAL_S,
)

logger = logging.getLogger(__name__)


class Rig:
    """
    Central Rig orchestrator.

    Owns the active RigAdapter and runs the single hardware I/O loop.
    All external consumers interact via commands (put into the command queue)
    and by reading the latest immutable Snapshot published each tick.
    """

    def __init__(
        self,
        adapter: RigAdapter,
        clock: Clock,
        sample_rate_ms: float = 1000.0,
        snapshot_consumer: queue.Queue[Snapshot] | Callable[[Snapshot], None] | None = None,
        practice_adapter: RigAdapter | None = None,
        hardware_adapter: RigAdapter | None = None,
        tc_names: Sequence[str] | None = None,
        gauge_names: Sequence[str] | None = None,
    ) -> None:
        self._adapter = adapter
        self._clock = clock
        self._sample_rate_ms = float(sample_rate_ms)
        self._snapshot_consumer = snapshot_consumer
        self._practice_adapter = practice_adapter or (
            adapter if isinstance(adapter, SimulatedRig) else None
        )
        self._hardware_adapter = hardware_adapter or (
            adapter if not isinstance(adapter, SimulatedRig) else None
        )
        if tc_names is not None:
            self._tc_names = list(tc_names)
        elif hasattr(adapter, "_tc_names"):
            self._tc_names = list(getattr(adapter, "_tc_names"))
        else:
            self._tc_names = ["TC_1"]

        if gauge_names is not None:
            self._gauge_names = list(gauge_names)
        elif hasattr(adapter, "_gauge_names"):
            self._gauge_names = list(getattr(adapter, "_gauge_names"))
        else:
            self._gauge_names = ["FRG702_Chamber"]

        self._command_queue: queue.Queue[Any] = queue.Queue()
        self._latest: Snapshot | None = None
        self._latest_lock = threading.Lock()

        # Lifecycle & state flags
        self._logging_active: bool = False
        self._program_status = ProgramStatus()
        self._heater_status = HeaterStatus(state="off")
        self._commanded_volts: float = 0.0
        self._output_enabled: bool = False

        self._adapter_connected: bool = adapter.is_connected()
        self._labjack_status = SourceStatus(
            state="connected" if self._adapter_connected else "lost"
        )
        self._xgs_status = SourceStatus(state="connected")

        # Staleness & reconnect timers
        self._start_time: float = clock.now()
        self._last_reconnect_attempt: float = -float("inf")
        self._last_valid_time: dict[str, float] = {}

        self._trip_kind: str | None = None
        self._trip_reason: str | None = None
        self._adapter_refusal_reason: str | None = None

        self._stop_requested: bool = False
        self._thread: threading.Thread | None = None

    # --- Properties & public methods ---

    @property
    def tick_period_s(self) -> float:
        """Tick period in seconds: min(sample_rate_ms / 1000, CONTROL_PERIOD_S)."""
        return min(self._sample_rate_ms / 1000.0, CONTROL_PERIOD_S)

    @property
    def logging_active(self) -> bool:
        """True if CSV logging is currently active."""
        return self._logging_active

    @logging_active.setter
    def logging_active(self, active: bool) -> None:
        self._logging_active = bool(active)

    def set_logging_active(self, active: bool) -> None:
        """Set whether CSV logging is active."""
        self._logging_active = bool(active)

    def submit_command(self, cmd: Any) -> None:
        """Submit a command to the Rig command queue."""
        self._command_queue.put(cmd)

    def submit(self, cmd: Any) -> None:
        """Convenience alias for submit_command."""
        self.submit_command(cmd)

    def latest(self) -> Snapshot | None:
        """Return the most recently published Snapshot (thread-safe)."""
        with self._latest_lock:
            return self._latest

    def start(self) -> None:
        """Start the background Rig loop thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_requested = False
        self._thread = threading.Thread(target=self._loop, name="RigThread", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the Rig loop thread to stop and wait for termination."""
        self._stop_requested = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # --- Single Rig Loop pass ---

    def run_tick(self) -> None:
        """
        Execute a single pass of the Rig loop in spec order.

        Steps:
        1. Drain command queue
        2. Reconnect if disconnected (at most every RECONNECT_INTERVAL_S)
        3. Read from adapter
        4. Calculate staleness and publish Snapshot
        5. Safety evaluation (no-op hook in ticket 03)
        6. Control step & Heater output write (no-op hook in ticket 03)
        7. Hand Snapshot to consumer queue
        """
        now = self._clock.now()

        # ---------------------------------------------------------
        # Step 1: Drain command queue
        # ---------------------------------------------------------
        self._adapter_refusal_reason = None
        while not self._command_queue.empty():
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_command(cmd)

        # ---------------------------------------------------------
        # Step 2: Reconnection
        # ---------------------------------------------------------
        if not self._adapter_connected or not self._adapter.is_connected():
            if self._adapter_connected:
                # Connection loss just noticed
                self._adapter_connected = False
                self._last_reconnect_attempt = now

            self._labjack_status = SourceStatus(state="lost", message="Disconnected")
            self._trip_kind = "labjack_lost"
            self._trip_reason = "LabJack communication lost"

            if (now - self._last_reconnect_attempt) >= RECONNECT_INTERVAL_S:
                self._last_reconnect_attempt = now
                try:
                    connected = self._adapter.connect()
                except AdapterError as err:
                    logger.warning("Adapter reconnection failed: %s", err)
                    connected = False

                if connected:
                    try:
                        # Safety invariant (ADR 0002/0003):
                        # First three calls MUST be: off, 0 V, pin current limit
                        self._adapter.set_output(False)
                        self._adapter.write_voltage(0.0)
                        self._adapter.pin_current_limit()
                        self._adapter_connected = True
                        self._labjack_status = SourceStatus(state="connected", message="OK")
                        self._trip_kind = None
                        self._trip_reason = None
                    except AdapterError as err:
                        logger.error("Failed to initialize adapter after connect: %s", err)
                        self._adapter_connected = False
                        self._labjack_status = SourceStatus(state="lost", message=str(err))
                        self._trip_kind = "labjack_lost"
                        self._trip_reason = f"Reconnection setup failed: {err}"

        # ---------------------------------------------------------
        # Step 3: Read
        # ---------------------------------------------------------
        read_failed = False
        readings: RawReadings | None = None

        if not self._adapter_connected:
            read_failed = True
        else:
            try:
                readings = self._adapter.read()
            except AdapterError as err:
                read_failed = True
                self._adapter_connected = False
                self._last_reconnect_attempt = now
                self._labjack_status = SourceStatus(state="lost", message=str(err))
                self._trip_kind = "labjack_lost"
                self._trip_reason = f"LabJack communication lost: {err}"

        # ---------------------------------------------------------
        # Step 4: Staleness + publish Snapshot
        # ---------------------------------------------------------
        source_age_s: dict[str, float] = {}
        tc_c: dict[str, float | None] = {}
        tc_raw_v: dict[str, float | None] = {}
        pressure_torr: dict[str, float | None] = {}

        if readings is not None:
            # Thermocouple readings & staleness
            for tc in self._tc_names:
                t_val = readings.tc_c.get(tc)
                tc_c[tc] = t_val
                tc_raw_v[tc] = readings.tc_raw_v.get(tc)
                if t_val is not None:
                    self._last_valid_time[tc] = now
                    source_age_s[tc] = 0.0
                else:
                    last_t = self._last_valid_time.get(tc)
                    source_age_s[tc] = (
                        (now - last_t) if last_t is not None else (now - self._start_time)
                    )

            # Gauge readings & staleness
            for g in self._gauge_names:
                p_val = readings.pressure_torr.get(g)
                p_valid = readings.pressure_valid.get(g, False)
                pressure_torr[g] = p_val
                if p_val is not None and p_valid:
                    self._last_valid_time[g] = now
                    source_age_s[g] = 0.0
                else:
                    last_t = self._last_valid_time.get(g)
                    source_age_s[g] = (
                        (now - last_t) if last_t is not None else (now - self._start_time)
                    )

            ps_volts = readings.ps_volts
            ps_amps = readings.ps_amps
            output_enabled = readings.shutoff_readback
        else:
            for tc in self._tc_names:
                tc_c[tc] = None
                tc_raw_v[tc] = None
                last_t = self._last_valid_time.get(tc)
                source_age_s[tc] = (
                    (now - last_t) if last_t is not None else (now - self._start_time)
                )

            for g in self._gauge_names:
                pressure_torr[g] = None
                last_t = self._last_valid_time.get(g)
                source_age_s[g] = (
                    (now - last_t) if last_t is not None else (now - self._start_time)
                )

            ps_volts = 0.0
            ps_amps = 0.0
            output_enabled = False

        adapter_name = "simulated" if isinstance(self._adapter, SimulatedRig) else "t8"
        heater_state = (
            "tripped" if self._trip_kind is not None else ("on" if output_enabled else "off")
        )
        heater_status = HeaterStatus(
            state=heater_state,
            trip_kind=self._trip_kind,
            trip_reason=self._trip_reason,
            shutoff_unverified=False,
        )

        snap = Snapshot(
            t=now,
            wall_time=self._clock.wall_time(),
            tc_c=tc_c,
            tc_raw_v=tc_raw_v,
            pressure_torr=pressure_torr,
            source_age_s=source_age_s,
            ps_volts=ps_volts,
            ps_amps=ps_amps,
            commanded_volts=self._commanded_volts,
            output_enabled=output_enabled,
            labjack=self._labjack_status,
            xgs=self._xgs_status,
            heater=heater_status,
            program=self._program_status,
            permissive_ok=(self._trip_kind is None),
            permissive_reason=self._trip_reason,
            adapter=adapter_name,
            adapter_refusal_reason=self._adapter_refusal_reason,
            command_rejected_reason=self._adapter_refusal_reason,
        )

        with self._latest_lock:
            self._latest = snap

        # ---------------------------------------------------------
        # Steps 5 & 6: Safety evaluation & Control step
        # ---------------------------------------------------------
        if not read_failed:
            # Step 5: Safety evaluation (no-op hook in ticket 03, filled in ticket 08)
            # Step 6: Control step & heater output (no-op hook in ticket 03, filled in ticket 10)
            pass

        # ---------------------------------------------------------
        # Step 7: Hand Snapshot to consumer queue
        # ---------------------------------------------------------
        if self._snapshot_consumer is not None:
            if hasattr(self._snapshot_consumer, "put"):
                self._snapshot_consumer.put(snap)
            elif callable(self._snapshot_consumer):
                self._snapshot_consumer(snap)

    def _handle_command(self, cmd: Any) -> None:
        """Handle a single drained command."""
        if isinstance(cmd, SelectAdapter):
            if self._logging_active or self._program_status.running:
                reason = "Cannot change adapter while " + (
                    "logging is active" if self._logging_active else "program is running"
                )
                self._adapter_refusal_reason = reason
                logger.warning("SelectAdapter refused: %s", reason)
            else:
                if cmd.practice:
                    if self._practice_adapter is not None:
                        self._adapter = self._practice_adapter
                else:
                    if self._hardware_adapter is not None:
                        self._adapter = self._hardware_adapter
                self._adapter_connected = self._adapter.is_connected()
                self._labjack_status = SourceStatus(
                    state="connected" if self._adapter_connected else "lost"
                )
                logger.info("SelectAdapter accepted (practice=%s)", cmd.practice)

        elif isinstance(cmd, UpdateConfig):
            if cmd.sample_rate_ms is not None:
                self._sample_rate_ms = float(cmd.sample_rate_ms)
            if cmd.tc_names is not None:
                self._tc_names = list(cmd.tc_names)
            if cmd.gauge_names is not None:
                self._gauge_names = list(cmd.gauge_names)

    def _loop(self) -> None:
        """Daemon thread loop for Rig execution."""
        while not self._stop_requested:
            next_tick = self._clock.now() + self.tick_period_s
            self.run_tick()
            self._clock.sleep_until(next_tick)
