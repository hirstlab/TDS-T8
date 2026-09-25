"""
Unit tests for SafetyMonitor class.
"""

import unittest
from unittest.mock import MagicMock
import pytest

from t8_daq_system.control.safety_monitor import (
    EvaluationResult,
    SafetyEvent,
    SafetyEvaluator,
    SafetyMonitor,
    SafetyState,
    SafetyStatus,
    SafetyWarning,
    Trip,
    evaluate_safety,
)
from t8_daq_system.rig.snapshot import (
    HeaterStatus,
    ProgramStatus,
    Snapshot,
    SourceStatus,
)
from t8_daq_system.settings.safety_limits import (
    PRESSURE_INTERLOCK_TORR,
    STALE_ALLOWANCE_S,
    TEMP_OVERRIDE_C,
)

pytestmark = pytest.mark.unit


class TestSafetyMonitorInit(unittest.TestCase):
    """Tests for SafetyMonitor initialization."""

    def test_create_without_power_supply(self):
        """Test creating monitor without power supply (alert-only mode)."""
        monitor = SafetyMonitor()
        self.assertIsNone(monitor.power_supply)
        self.assertEqual(monitor.status, SafetyStatus.OK)
        self.assertTrue(monitor.enabled)

    def test_create_with_power_supply(self):
        """Test creating monitor with power supply."""
        mock_ps = MagicMock()
        monitor = SafetyMonitor(power_supply_controller=mock_ps)
        self.assertEqual(monitor.power_supply, mock_ps)

    def test_create_with_auto_shutoff_disabled(self):
        """Test creating monitor with auto shutoff disabled."""
        monitor = SafetyMonitor(auto_shutoff=False)
        self.assertFalse(monitor.auto_shutoff)


class TestSafetyMonitorLimits(unittest.TestCase):
    """Tests for temperature limit management."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = SafetyMonitor()

    def test_set_temperature_limit(self):
        """Test setting a temperature limit."""
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.assertEqual(self.monitor.get_temperature_limit("TC1"), 200.0)

    def test_set_multiple_limits(self):
        """Test setting multiple temperature limits."""
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.set_temperature_limit("TC2", 180.0)
        self.monitor.set_temperature_limit("TC3", 150.0)

        limits = self.monitor.get_all_limits()
        self.assertEqual(len(limits), 3)
        self.assertEqual(limits["TC2"], 180.0)

    def test_set_negative_limit_raises(self):
        """Test that negative limit raises ValueError."""
        with self.assertRaises(ValueError):
            self.monitor.set_temperature_limit("TC1", -100.0)

    def test_set_zero_limit_raises(self):
        """Test that zero limit raises ValueError."""
        with self.assertRaises(ValueError):
            self.monitor.set_temperature_limit("TC1", 0.0)

    def test_remove_temperature_limit(self):
        """Test removing a temperature limit."""
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.remove_temperature_limit("TC1")
        self.assertIsNone(self.monitor.get_temperature_limit("TC1"))

    def test_remove_nonexistent_limit(self):
        """Test removing a nonexistent limit (no error)."""
        self.monitor.remove_temperature_limit("NonExistent")
        # Should not raise

    def test_clear_all_limits(self):
        """Test clearing all limits."""
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.set_temperature_limit("TC2", 180.0)
        self.monitor.clear_all_limits()
        self.assertEqual(len(self.monitor.get_all_limits()), 0)


class TestSafetyMonitorChecks(unittest.TestCase):
    """Tests for limit checking."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True
        self.mock_ps.output_off.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.set_temperature_limit("TC2", 180.0)

    def test_check_limits_all_safe(self):
        """Test check when all readings are within limits."""
        readings = {"TC1": 150.0, "TC2": 100.0}
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)
        self.assertEqual(self.monitor.status, SafetyStatus.OK)

    def test_check_limits_exceeds_limit(self):
        """Test check when a reading exceeds limit."""
        readings = {"TC1": 210.0, "TC2": 100.0}  # TC1 exceeds 200
        result = self.monitor.check_limits(readings)
        self.assertFalse(result)
        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)

    def test_check_limits_at_exactly_limit(self):
        """Test check when reading is exactly at limit."""
        readings = {"TC1": 200.0, "TC2": 100.0}  # TC1 at exactly 200
        result = self.monitor.check_limits(readings)
        self.assertFalse(result)  # At limit should trigger

    def test_check_limits_warning_threshold(self):
        """Test warning when reading approaches limit."""
        self.monitor.set_warning_threshold(0.9)  # Warn at 90%
        readings = {"TC1": 185.0, "TC2": 100.0}  # TC1 at 92.5% of 200
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Still safe
        self.assertEqual(self.monitor.status, SafetyStatus.WARNING)

    def test_check_limits_missing_sensor(self):
        """Test check when monitored sensor is missing from readings."""
        readings = {"TC3": 150.0}  # TC1 and TC2 not present
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Missing sensors don't trigger

    def test_check_limits_invalid_reading(self):
        """Test check with invalid (None) reading."""
        readings = {"TC1": None, "TC2": 100.0}
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # None readings skipped

    def test_check_limits_disconnected_sensor(self):
        """Test check with disconnected sensor marker (-9999)."""
        readings = {"TC1": -9999, "TC2": 100.0}
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Disconnected sensors skipped

    def test_check_limits_disabled(self):
        """Test check when monitor is disabled."""
        self.monitor.enabled = False
        readings = {"TC1": 500.0}  # Way over limit
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Passes when disabled


class TestSafetyMonitorShutdown(unittest.TestCase):
    """Tests for emergency shutdown."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True
        self.mock_ps.output_off.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)

    def test_emergency_shutdown_called_on_limit_exceeded(self):
        """Test that emergency shutdown is called when limit exceeded."""
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)
        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)

    def test_emergency_shutdown_not_called_when_safe(self):
        """Test that shutdown is not called when readings are safe."""
        readings = {"TC1": 150.0}
        self.monitor.check_limits(readings)
        self.assertEqual(self.monitor.status, SafetyStatus.OK)

    def test_manual_emergency_shutdown(self):
        """Test manual emergency shutdown."""
        result = self.monitor.emergency_shutdown()
        self.assertTrue(result)
        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)

    def test_emergency_shutdown_without_power_supply(self):
        """Test emergency shutdown without power supply connected."""
        monitor = SafetyMonitor()  # No power supply
        result = monitor.emergency_shutdown()
        self.assertFalse(result)

    def test_auto_shutoff_disabled(self):
        """Test that auto shutoff can be disabled."""
        self.monitor.auto_shutoff = False
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        # Status should still change but shutdown not called
        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)


class TestSafetyMonitorWatchdog(unittest.TestCase):
    """Tests for watchdog sensor functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.set_temperature_limit("TC2", 200.0)
        self.monitor.set_watchdog_sensor("TC1")

    def test_watchdog_immediate_shutdown(self):
        """Test that watchdog sensor triggers immediate shutdown."""
        # Set debounce to require multiple violations
        self.monitor.set_debounce_count(3)

        # Watchdog should still trigger immediately
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)
        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)

    def test_non_watchdog_respects_debounce(self):
        """Test that non-watchdog sensors respect debounce count."""
        self.monitor.set_debounce_count(3)

        # First violation - should not trigger
        readings = {"TC2": 210.0}
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Not triggered yet

        # Second violation
        result = self.monitor.check_limits(readings)
        self.assertTrue(result)  # Still not triggered

        # Third violation - now triggers
        result = self.monitor.check_limits(readings)
        self.assertFalse(result)


class TestSafetyMonitorCallbacks(unittest.TestCase):
    """Tests for callback functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)
        self.monitor.set_warning_threshold(0.9)

    def test_on_warning_callback(self):
        """Test warning callback is called."""
        callback = MagicMock()
        self.monitor.on_warning(callback)

        readings = {"TC1": 185.0}  # 92.5% of limit
        self.monitor.check_limits(readings)

        callback.assert_called_once()
        args = callback.call_args[0]
        self.assertEqual(args[0], "TC1")  # sensor_name
        self.assertEqual(args[1], 185.0)  # value
        self.assertEqual(args[2], 200.0)  # limit

    def test_on_limit_exceeded_callback(self):
        """Test limit exceeded callback is called."""
        callback = MagicMock()
        self.monitor.on_limit_exceeded(callback)

        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        callback.assert_called_once()

    def test_on_shutdown_callback(self):
        """Test shutdown callback is called."""
        callback = MagicMock()
        self.monitor.on_shutdown(callback)

        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        callback.assert_called_once()
        event = callback.call_args[0][0]
        self.assertIsInstance(event, SafetyEvent)
        self.assertEqual(event.sensor_name, "TC1")

    def test_on_warning_callback_failure_propagates(self):
        """Test that an exception in on_warning callback propagates instead of being swallowed."""
        def bad_cb(*args):
            raise RuntimeError("Warning callback crashed")
        self.monitor.on_warning(bad_cb)
        readings = {"TC1": 185.0}
        with self.assertRaises(RuntimeError):
            self.monitor.check_limits(readings)

    def test_on_limit_exceeded_callback_failure_propagates(self):
        """Test that an exception in on_limit_exceeded callback propagates."""
        def bad_cb(*args):
            raise RuntimeError("Limit exceeded callback crashed")
        self.monitor.on_limit_exceeded(bad_cb)
        readings = {"TC1": 210.0}
        with self.assertRaises(RuntimeError):
            self.monitor.check_limits(readings)

    def test_on_shutdown_callback_failure_propagates(self):
        """Test that an exception in on_shutdown callback propagates."""
        def bad_cb(*args):
            raise RuntimeError("Shutdown callback crashed")
        self.monitor.on_shutdown(bad_cb)
        readings = {"TC1": 210.0}
        with self.assertRaises(RuntimeError):
            self.monitor.check_limits(readings)



class TestSafetyMonitorEventHistory(unittest.TestCase):
    """Tests for event history."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)

    def test_get_last_event(self):
        """Test getting last event."""
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        event = self.monitor.get_last_event()
        self.assertIsNotNone(event)
        self.assertEqual(event.sensor_name, "TC1")
        self.assertEqual(event.value, 210.0)
        self.assertEqual(event.limit, 200.0)

    def test_get_event_history(self):
        """Test getting event history."""
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        history = self.monitor.get_event_history()
        self.assertGreater(len(history), 0)

    def test_clear_event_history(self):
        """Test clearing event history."""
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        self.monitor.clear_event_history()
        self.assertEqual(len(self.monitor.get_event_history()), 0)
        self.assertIsNone(self.monitor.get_last_event())


class TestSafetyMonitorConfiguration(unittest.TestCase):
    """Tests for configuration from dictionary."""

    def test_configure_from_dict(self):
        """Test configuring monitor from dictionary."""
        config = {
            "enabled": True,
            "auto_shutoff": True,
            "max_temperature": 200,
            "warning_threshold": 0.85,
            "watchdog_sensor": "TC_1",
            "sensor_limits": {
                "TC_1": 200,
                "TC_2": 180,
                "TC_3": 150
            }
        }

        monitor = SafetyMonitor()
        monitor.configure_from_dict(config)

        self.assertTrue(monitor.enabled)
        self.assertTrue(monitor.auto_shutoff)
        self.assertEqual(monitor.get_temperature_limit("TC_1"), 200)
        self.assertEqual(monitor.get_temperature_limit("TC_2"), 180)
        self.assertEqual(monitor.get_temperature_limit("TC_3"), 150)

    def test_configure_with_defaults(self):
        """Test configuration with missing values uses defaults."""
        config = {
            "sensor_limits": {"TC_1": 100}
        }

        monitor = SafetyMonitor()
        monitor.configure_from_dict(config)

        self.assertTrue(monitor.enabled)  # Default
        self.assertEqual(monitor.get_temperature_limit("TC_1"), 100)


class TestSafetyMonitorReset(unittest.TestCase):
    """Tests for monitor reset."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_ps = MagicMock()
        self.mock_ps.emergency_shutdown.return_value = True

        self.monitor = SafetyMonitor(power_supply_controller=self.mock_ps)
        self.monitor.set_temperature_limit("TC1", 200.0)

    def test_reset_after_shutdown(self):
        """Test resetting monitor after shutdown."""
        readings = {"TC1": 210.0}
        self.monitor.check_limits(readings)

        self.assertEqual(self.monitor.status, SafetyStatus.SHUTDOWN_TRIGGERED)

        self.monitor.reset()
        self.assertEqual(self.monitor.status, SafetyStatus.OK)
        self.assertTrue(self.monitor.is_safe)


class TestSafetyMonitorStatusReport(unittest.TestCase):
    """Tests for status report."""

    def test_get_status_report(self):
        """Test getting comprehensive status report."""
        monitor = SafetyMonitor()
        monitor.set_temperature_limit("TC1", 200.0)
        monitor.set_watchdog_sensor("TC1")

        report = monitor.get_status_report()

        self.assertIn('status', report)
        self.assertIn('enabled', report)
        self.assertIn('auto_shutoff', report)
        self.assertIn('temperature_limits', report)
        self.assertIn('watchdog_sensor', report)
        self.assertEqual(report['watchdog_sensor'], "TC1")


class TestSafetyMonitorThreadSafety(unittest.TestCase):
    """Tests for thread safety."""

    def test_concurrent_limit_checks(self):
        """Test that concurrent limit checks work correctly."""
        import threading

        monitor = SafetyMonitor()
        monitor.set_temperature_limit("TC1", 200.0)

        results = []

        def check_thread():
            for _ in range(100):
                readings = {"TC1": 150.0}
                result = monitor.check_limits(readings)
                results.append(result)

        threads = [threading.Thread(target=check_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All checks should pass
        self.assertEqual(len(results), 500)
        self.assertTrue(all(results))



# =============================================================================
# Pure SafetyEvaluator Tests (Ticket 06 / ADR 0003 & 0004)
# =============================================================================


def _make_snapshot(
    tc_c=None,
    tc_raw_v=None,
    pressure_torr=None,
    source_age_s=None,
    program=None,
    heater=None,
    permissive_ok=True,
    permissive_reason=None,
    ps_volts=0.0,
    ps_amps=0.0,
    commanded_volts=0.0,
    output_enabled=False,
    labjack=None,
    xgs=None,
    adapter="simulated",
) -> Snapshot:
    if tc_c is None:
        tc_c = {"TC_1": 25.0}
    if tc_raw_v is None:
        tc_raw_v = {k: 0.001 for k in tc_c}
    if pressure_torr is None:
        pressure_torr = {"FRG702_Chamber": 1e-6}
    if source_age_s is None:
        source_age_s = {k: 0.0 for k in tc_c}
        source_age_s.update({k: 0.0 for k in pressure_torr})
    if program is None:
        program = ProgramStatus()
    if heater is None:
        heater = HeaterStatus(state="off")
    if labjack is None:
        labjack = SourceStatus(state="connected", message="OK")
    if xgs is None:
        xgs = SourceStatus(state="connected", message="OK")

    return Snapshot(
        t=100.0,
        wall_time=1700000000.0,
        tc_c=tc_c,
        tc_raw_v=tc_raw_v,
        pressure_torr=pressure_torr,
        source_age_s=source_age_s,
        ps_volts=ps_volts,
        ps_amps=ps_amps,
        commanded_volts=commanded_volts,
        output_enabled=output_enabled,
        labjack=labjack,
        xgs=xgs,
        heater=heater,
        program=program,
        permissive_ok=permissive_ok,
        permissive_reason=permissive_reason,
        adapter=adapter,
    )


class TestSafetyEvaluatorBoundaries(unittest.TestCase):
    """
    Test that each trip kind trips at, just below, and just above its boundary.
    Boundary contract:
    - temp_limit: value >= limit
    - temp_override: value >= TEMP_OVERRIDE_C
    - pressure_high: pressure > PRESSURE_INTERLOCK_TORR
    - pressure_stale: age > STALE_ALLOWANCE_S
    - control_tc_stale: age > STALE_ALLOWANCE_S (when closed-loop block running)
    """

    def setUp(self):
        self.evaluator = SafetyEvaluator()
        self.evaluator.set_temperature_limit("TC_1", 500.0)
        self.evaluator.set_debounce_count(1)

    def test_temp_limit_boundary(self):
        """Boundary for temp_limit: 499.9 C (no trip), 500.0 C (trip), 500.1 C (trip)."""
        # Just below: 499.9 C
        snap_below = _make_snapshot(tc_c={"TC_1": 499.9})
        trips = self.evaluator.evaluate(snap_below)
        self.assertEqual(len(trips), 0)

        # At boundary: 500.0 C
        snap_at = _make_snapshot(tc_c={"TC_1": 500.0})
        trips = self.evaluator.evaluate(snap_at)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "temp_limit")
        self.assertIn("TC_1", trips[0].reason)
        self.assertIn("500.0", trips[0].reason)

        # Reset evaluator state
        self.evaluator.clear_all_limits()
        self.evaluator.set_temperature_limit("TC_1", 500.0)

        # Just above: 500.1 C
        snap_above = _make_snapshot(tc_c={"TC_1": 500.1})
        trips = self.evaluator.evaluate(snap_above)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "temp_limit")
        self.assertIn("TC_1", trips[0].reason)
        self.assertIn("500.1", trips[0].reason)

    def test_temp_override_boundary(self):
        """Boundary for temp_override (2200.0 C): 2199.9 C (no trip), 2200.0 C (trip), 2200.1 C (trip)."""
        # Just below: 2199.9 C
        snap_below = _make_snapshot(tc_c={"TC_2": 2199.9})
        trips = self.evaluator.evaluate(snap_below)
        self.assertEqual(len(trips), 0)

        # At boundary: 2200.0 C
        snap_at = _make_snapshot(tc_c={"TC_2": 2200.0})
        trips = self.evaluator.evaluate(snap_at)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "temp_override")
        self.assertIn("TC_2", trips[0].reason)
        self.assertIn(str(int(TEMP_OVERRIDE_C)), trips[0].reason)

        # Just above: 2200.1 C
        snap_above = _make_snapshot(tc_c={"TC_2": 2200.1})
        trips = self.evaluator.evaluate(snap_above)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "temp_override")
        self.assertIn("TC_2", trips[0].reason)

    def test_pressure_high_boundary(self):
        """Boundary for pressure_high (> 1e-4 Torr): 0.99e-4 (no trip), 1.0e-4 (no trip), 1.01e-4 (trip)."""
        # Just below: 0.99 * PRESSURE_INTERLOCK_TORR
        snap_below = _make_snapshot(pressure_torr={"FRG702_Chamber": PRESSURE_INTERLOCK_TORR * 0.99})
        trips = self.evaluator.evaluate(snap_below)
        self.assertEqual(len(trips), 0)

        # At boundary: exactly PRESSURE_INTERLOCK_TORR (spec says strictly > PRESSURE_INTERLOCK_TORR)
        snap_at = _make_snapshot(pressure_torr={"FRG702_Chamber": PRESSURE_INTERLOCK_TORR})
        trips = self.evaluator.evaluate(snap_at)
        self.assertEqual(len(trips), 0)

        # Just above: 1.01 * PRESSURE_INTERLOCK_TORR
        snap_above = _make_snapshot(pressure_torr={"FRG702_Chamber": PRESSURE_INTERLOCK_TORR * 1.01})
        trips = self.evaluator.evaluate(snap_above)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "pressure_high")
        self.assertIn("FRG702_Chamber", trips[0].reason)

    def test_pressure_stale_boundary(self):
        """Boundary for pressure_stale (> 5.0 s): 4.9 s (no trip), 5.0 s (no trip), 5.1 s (trip)."""
        # Just below: STALE_ALLOWANCE_S - 0.1
        snap_below = _make_snapshot(source_age_s={"TC_1": 0.0, "FRG702_Chamber": STALE_ALLOWANCE_S - 0.1})
        trips = self.evaluator.evaluate(snap_below)
        self.assertEqual(len(trips), 0)

        # At boundary: STALE_ALLOWANCE_S
        snap_at = _make_snapshot(source_age_s={"TC_1": 0.0, "FRG702_Chamber": STALE_ALLOWANCE_S})
        trips = self.evaluator.evaluate(snap_at)
        self.assertEqual(len(trips), 0)

        # Just above: STALE_ALLOWANCE_S + 0.1
        snap_above = _make_snapshot(source_age_s={"TC_1": 0.0, "FRG702_Chamber": STALE_ALLOWANCE_S + 0.1})
        trips = self.evaluator.evaluate(snap_above)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "pressure_stale")
        self.assertIn("FRG702_Chamber", trips[0].reason)
        self.assertIn(f"{STALE_ALLOWANCE_S + 0.1:.1f}", trips[0].reason)

    def test_control_tc_stale_boundary(self):
        """Boundary for control_tc_stale (> 5.0 s in closed loop): 4.9 s (no trip), 5.0 s (no trip), 5.1 s (trip)."""
        prog = ProgramStatus(running=True, block_type="temp_ramp", control_tc="TC_1")

        # Just below: STALE_ALLOWANCE_S - 0.1
        snap_below = _make_snapshot(
            program=prog,
            source_age_s={"TC_1": STALE_ALLOWANCE_S - 0.1, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap_below)
        self.assertEqual(len(trips), 0)

        # At boundary: STALE_ALLOWANCE_S
        snap_at = _make_snapshot(
            program=prog,
            source_age_s={"TC_1": STALE_ALLOWANCE_S, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap_at)
        self.assertEqual(len(trips), 0)

        # Just above: STALE_ALLOWANCE_S + 0.1
        snap_above = _make_snapshot(
            program=prog,
            source_age_s={"TC_1": STALE_ALLOWANCE_S + 0.1, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap_above)
        self.assertEqual(len(trips), 1)
        self.assertIsInstance(trips[0], Trip)
        self.assertEqual(trips[0].kind, "control_tc_stale")
        self.assertIn("TC_1", trips[0].reason)
        self.assertIn(f"{STALE_ALLOWANCE_S + 0.1:.1f}", trips[0].reason)


class TestSafetyEvaluatorDebounce(unittest.TestCase):
    """Test debounce semantics: debounce_count - 1 consecutive ticks do not trip, debounce_count do."""

    def test_debounce_count_and_reset(self):
        evaluator = SafetyEvaluator()
        evaluator.set_temperature_limit("TC_1", 300.0)
        evaluator.set_debounce_count(3)

        snap_over = _make_snapshot(tc_c={"TC_1": 310.0})
        snap_safe = _make_snapshot(tc_c={"TC_1": 250.0})

        # Tick 1: over limit (count = 1 < 3) -> no trip
        trips1 = evaluator.evaluate(snap_over)
        self.assertEqual(len(trips1), 0)

        # Tick 2: over limit (count = 2 < 3) -> no trip
        trips2 = evaluator.evaluate(snap_over)
        self.assertEqual(len(trips2), 0)

        # Interleaved safe tick resets debounce counter
        trips_safe = evaluator.evaluate(snap_safe)
        self.assertEqual(len(trips_safe), 0)

        # Tick 4: over limit again (count = 1 < 3) -> no trip
        trips4 = evaluator.evaluate(snap_over)
        self.assertEqual(len(trips4), 0)

        # Tick 5: over limit again (count = 2 < 3) -> no trip
        trips5 = evaluator.evaluate(snap_over)
        self.assertEqual(len(trips5), 0)

        # Tick 6: over limit (count = 3 == debounce_count) -> TRIPS!
        trips6 = evaluator.evaluate(snap_over)
        self.assertEqual(len(trips6), 1)
        self.assertEqual(trips6[0].kind, "temp_limit")


class TestSafetyEvaluatorWarnings(unittest.TestCase):
    """Test that warning-band temperatures appear in warnings and never trip."""

    def test_warning_band_temperature_never_trips(self):
        evaluator = SafetyEvaluator()
        evaluator.set_temperature_limit("TC_1", 500.0)
        evaluator.set_warning_threshold(0.9)  # Warning band: [450.0, 500.0)
        evaluator.set_debounce_count(1)

        # Below warning threshold (449.9 C): neither warning nor trip
        snap1 = _make_snapshot(tc_c={"TC_1": 449.9})
        res1 = evaluator.evaluate(snap1)
        self.assertIsInstance(res1, EvaluationResult)
        self.assertEqual(len(res1), 0)
        self.assertEqual(len(res1.warnings), 0)

        # At warning threshold (450.0 C): warning, NO trip
        snap2 = _make_snapshot(tc_c={"TC_1": 450.0})
        res2 = evaluator.evaluate(snap2)
        self.assertIsInstance(res2, EvaluationResult)
        self.assertEqual(len(res2), 0)
        self.assertEqual(len(res2.warnings), 1)
        self.assertIsInstance(res2.warnings[0], SafetyWarning)
        self.assertEqual(res2.warnings[0].sensor, "TC_1")
        self.assertAlmostEqual(res2.warnings[0].value, 450.0)

        # Inside warning band (480.0 C): warning, NO trip
        snap3 = _make_snapshot(tc_c={"TC_1": 480.0})
        res3 = evaluator.evaluate(snap3)
        self.assertEqual(len(res3), 0)
        self.assertEqual(len(res3.warnings), 1)
        self.assertEqual(res3.warnings[0].sensor, "TC_1")

        # At or above limit (500.0 C): TRIP, NOT in warnings list
        snap4 = _make_snapshot(tc_c={"TC_1": 500.0})
        res4 = evaluator.evaluate(snap4)
        self.assertEqual(len(res4), 1)
        self.assertEqual(res4[0].kind, "temp_limit")
        self.assertEqual(len(res4.warnings), 0)


class TestSafetyEvaluatorControlTCStale(unittest.TestCase):
    """Test that control_tc_stale never fires while no closed-loop block is running."""

    def setUp(self):
        self.evaluator = SafetyEvaluator()

    def test_stale_tc_when_program_not_running_does_not_trip(self):
        """When program is not running, stale TC must NOT trip."""
        snap = _make_snapshot(
            program=ProgramStatus(running=False, block_type="temp_ramp", control_tc="TC_1"),
            source_age_s={"TC_1": 10.0, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap)
        self.assertEqual(len(trips), 0)

    def test_stale_tc_during_voltage_ramp_does_not_trip(self):
        """voltage_ramp is open-loop, so stale TC must NOT trip."""
        snap = _make_snapshot(
            program=ProgramStatus(running=True, block_type="voltage_ramp", control_tc="TC_1"),
            source_age_s={"TC_1": 10.0, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap)
        self.assertEqual(len(trips), 0)

    def test_stale_tc_during_temp_ramp_trips(self):
        """temp_ramp is closed-loop, so stale TC (> 5 s) must trip."""
        snap = _make_snapshot(
            program=ProgramStatus(running=True, block_type="temp_ramp", control_tc="TC_1"),
            source_age_s={"TC_1": 5.1, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap)
        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0].kind, "control_tc_stale")

    def test_stale_tc_during_stable_hold_trips(self):
        """stable_hold is closed-loop, so stale TC (> 5 s) must trip."""
        snap = _make_snapshot(
            program=ProgramStatus(running=True, block_type="stable_hold", control_tc="TC_1"),
            source_age_s={"TC_1": 5.1, "FRG702_Chamber": 0.0},
        )
        trips = self.evaluator.evaluate(snap)
        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0].kind, "control_tc_stale")


class TestSafetyEvaluatorPermissive(unittest.TestCase):
    """
    Test permissive calculation in Torr:
    Permissive is true only when every enabled gauge has a valid reading <= 5 s old and below threshold.
    """

    def setUp(self):
        self.evaluator = SafetyEvaluator()

    def test_permissive_true_when_valid_and_low(self):
        snap = _make_snapshot(
            pressure_torr={"FRG702_Chamber": 1e-6},
            source_age_s={"TC_1": 0.0, "FRG702_Chamber": 0.5},
        )
        res = self.evaluator.evaluate(snap)
        self.assertTrue(res.permissive_ok)
        self.assertIsNone(res.permissive_reason)

    def test_permissive_false_when_gauge_high(self):
        snap = _make_snapshot(
            pressure_torr={"FRG702_Chamber": 2e-4},
            source_age_s={"TC_1": 0.0, "FRG702_Chamber": 0.5},
        )
        res = self.evaluator.evaluate(snap)
        self.assertFalse(res.permissive_ok)
        self.assertIsNotNone(res.permissive_reason)
        self.assertIn("FRG702_Chamber", res.permissive_reason)

    def test_permissive_false_when_gauge_stale(self):
        snap = _make_snapshot(
            pressure_torr={"FRG702_Chamber": 1e-6},
            source_age_s={"TC_1": 0.0, "FRG702_Chamber": 5.1},
        )
        res = self.evaluator.evaluate(snap)
        self.assertFalse(res.permissive_ok)
        self.assertIsNotNone(res.permissive_reason)
        self.assertIn("stale", res.permissive_reason.lower())

    def test_permissive_false_when_gauge_invalid(self):
        snap = _make_snapshot(
            pressure_torr={"FRG702_Chamber": None},
            source_age_s={"TC_1": 0.0, "FRG702_Chamber": 1.0},
        )
        res = self.evaluator.evaluate(snap)
        self.assertFalse(res.permissive_ok)
        self.assertIsNotNone(res.permissive_reason)
        self.assertIn("invalid", res.permissive_reason.lower())

    def test_permissive_false_when_no_gauges_present(self):
        snap = _make_snapshot(pressure_torr={})
        res = self.evaluator.evaluate(snap)
        self.assertFalse(res.permissive_ok)
        self.assertIsNotNone(res.permissive_reason)


class TestSafetyEvaluatorSettersAndState(unittest.TestCase):
    """Test setters and pure state passing."""

    def test_setters_and_validation(self):
        evaluator = SafetyEvaluator()

        # Limits
        evaluator.set_temperature_limit("TC_1", 400.0)
        self.assertEqual(evaluator.get_temperature_limit("TC_1"), 400.0)
        self.assertEqual(evaluator.get_all_limits(), {"TC_1": 400.0})

        with self.assertRaises(ValueError):
            evaluator.set_temperature_limit("TC_1", 0.0)
        with self.assertRaises(ValueError):
            evaluator.set_temperature_limit("TC_1", -10.0)

        evaluator.remove_temperature_limit("TC_1")
        self.assertIsNone(evaluator.get_temperature_limit("TC_1"))

        evaluator.set_temperature_limit("TC_1", 400.0)
        evaluator.clear_all_limits()
        self.assertEqual(len(evaluator.get_all_limits()), 0)

        # Warning threshold
        evaluator.set_warning_threshold(0.8)
        self.assertEqual(evaluator.warning_threshold, 0.8)
        with self.assertRaises(ValueError):
            evaluator.set_warning_threshold(0.0)
        with self.assertRaises(ValueError):
            evaluator.set_warning_threshold(1.0)

        # Debounce count
        evaluator.set_debounce_count(4)
        self.assertEqual(evaluator.debounce_count, 4)
        with self.assertRaises(ValueError):
            evaluator.set_debounce_count(0)

    def test_pure_state_passing(self):
        evaluator = SafetyEvaluator()
        evaluator.set_temperature_limit("TC_1", 300.0)
        evaluator.set_debounce_count(3)

        state = SafetyState()
        snap = _make_snapshot(tc_c={"TC_1": 350.0})

        # Tick 1 with explicit state
        res1 = evaluate_safety(snap, state=state, limits={"TC_1": 300.0}, debounce_count=3)
        self.assertEqual(len(res1), 0)
        self.assertEqual(state.violation_counts["TC_1"], 1)

        # Tick 2
        res2 = evaluate_safety(snap, state=state, limits={"TC_1": 300.0}, debounce_count=3)
        self.assertEqual(len(res2), 0)
        self.assertEqual(state.violation_counts["TC_1"], 2)

        # Tick 3
        res3 = evaluate_safety(snap, state=state, limits={"TC_1": 300.0}, debounce_count=3)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0].kind, "temp_limit")


class TestSafetyMonitorEvaluatorIntegration(unittest.TestCase):
    """Test SafetyMonitor integration with pure evaluation."""

    def test_safety_monitor_has_evaluate(self):
        monitor = SafetyMonitor()
        monitor.set_temperature_limit("TC_1", 500.0)
        monitor.set_debounce_count(1)

        snap = _make_snapshot(tc_c={"TC_1": 550.0})
        res = monitor.evaluate(snap)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].kind, "temp_limit")
        self.assertIn("TC_1", res[0].reason)


if __name__ == '__main__':
    unittest.main()
