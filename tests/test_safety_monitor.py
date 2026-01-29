"""
Unit tests for SafetyMonitor class.
"""

import unittest
from unittest.mock import MagicMock

from t8_daq_system.control.safety_monitor import SafetyMonitor, SafetyStatus, SafetyEvent


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
        self.mock_ps.emergency_shutdown.assert_called_once()

    def test_emergency_shutdown_not_called_when_safe(self):
        """Test that shutdown is not called when readings are safe."""
        readings = {"TC1": 150.0}
        self.monitor.check_limits(readings)
        self.mock_ps.emergency_shutdown.assert_not_called()

    def test_manual_emergency_shutdown(self):
        """Test manual emergency shutdown."""
        result = self.monitor.emergency_shutdown()
        self.assertTrue(result)
        self.mock_ps.emergency_shutdown.assert_called_once()

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
        self.mock_ps.emergency_shutdown.assert_not_called()


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
        result = self.monitor.check_limits(readings)
        self.assertFalse(result)
        self.mock_ps.emergency_shutdown.assert_called_once()

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


if __name__ == '__main__':
    unittest.main()
