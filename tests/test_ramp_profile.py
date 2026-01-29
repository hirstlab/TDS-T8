"""
Unit tests for RampProfile and RampStep classes.
"""

import unittest
import json
import tempfile
import os

from t8_daq_system.control.ramp_profile import RampProfile, RampStep, StepType


class TestRampStep(unittest.TestCase):
    """Tests for RampStep dataclass."""

    def test_create_ramp_step(self):
        """Test creating a ramp step."""
        step = RampStep(
            step_type="ramp",
            duration_sec=60.0,
            target_voltage=5.0
        )
        self.assertEqual(step.step_type, "ramp")
        self.assertEqual(step.duration_sec, 60.0)
        self.assertEqual(step.target_voltage, 5.0)

    def test_create_hold_step(self):
        """Test creating a hold step."""
        step = RampStep(
            step_type="hold",
            duration_sec=120.0
        )
        self.assertEqual(step.step_type, "hold")
        self.assertEqual(step.duration_sec, 120.0)
        self.assertIsNone(step.target_voltage)

    def test_invalid_step_type(self):
        """Test that invalid step type raises error."""
        with self.assertRaises(ValueError):
            RampStep(step_type="invalid", duration_sec=60.0)

    def test_negative_duration(self):
        """Test that negative duration raises error."""
        with self.assertRaises(ValueError):
            RampStep(step_type="hold", duration_sec=-10.0)

    def test_zero_duration(self):
        """Test that zero duration raises error."""
        with self.assertRaises(ValueError):
            RampStep(step_type="hold", duration_sec=0.0)

    def test_ramp_missing_target_voltage(self):
        """Test that ramp step without target voltage raises error."""
        with self.assertRaises(ValueError):
            RampStep(step_type="ramp", duration_sec=60.0)

    def test_negative_target_voltage(self):
        """Test that negative target voltage raises error."""
        with self.assertRaises(ValueError):
            RampStep(step_type="ramp", duration_sec=60.0, target_voltage=-5.0)

    def test_to_dict_ramp(self):
        """Test converting ramp step to dictionary."""
        step = RampStep(step_type="ramp", duration_sec=60.0, target_voltage=5.0)
        d = step.to_dict()
        self.assertEqual(d["type"], "ramp")
        self.assertEqual(d["duration_sec"], 60.0)
        self.assertEqual(d["target_voltage"], 5.0)

    def test_to_dict_hold(self):
        """Test converting hold step to dictionary."""
        step = RampStep(step_type="hold", duration_sec=120.0)
        d = step.to_dict()
        self.assertEqual(d["type"], "hold")
        self.assertEqual(d["duration_sec"], 120.0)
        self.assertNotIn("target_voltage", d)

    def test_from_dict(self):
        """Test creating step from dictionary."""
        data = {"type": "ramp", "duration_sec": 60.0, "target_voltage": 5.0}
        step = RampStep.from_dict(data)
        self.assertEqual(step.step_type, "ramp")
        self.assertEqual(step.duration_sec, 60.0)
        self.assertEqual(step.target_voltage, 5.0)


class TestRampProfile(unittest.TestCase):
    """Tests for RampProfile class."""

    def setUp(self):
        """Set up test fixtures."""
        self.profile = RampProfile(
            name="Test Profile",
            description="A test profile",
            start_voltage=0.0,
            current_limit=50.0
        )

    def test_create_empty_profile(self):
        """Test creating an empty profile."""
        self.assertEqual(self.profile.name, "Test Profile")
        self.assertEqual(self.profile.start_voltage, 0.0)
        self.assertEqual(self.profile.current_limit, 50.0)
        self.assertEqual(len(self.profile.steps), 0)

    def test_add_step(self):
        """Test adding a step to profile."""
        step = RampStep(step_type="ramp", duration_sec=60.0, target_voltage=5.0)
        self.profile.add_step(step)
        self.assertEqual(len(self.profile.steps), 1)

    def test_add_ramp(self):
        """Test convenience method to add ramp step."""
        self.profile.add_ramp(target_voltage=5.0, duration_sec=60.0)
        self.assertEqual(len(self.profile.steps), 1)
        self.assertEqual(self.profile.steps[0].step_type, "ramp")
        self.assertEqual(self.profile.steps[0].target_voltage, 5.0)

    def test_add_hold(self):
        """Test convenience method to add hold step."""
        self.profile.add_hold(duration_sec=120.0)
        self.assertEqual(len(self.profile.steps), 1)
        self.assertEqual(self.profile.steps[0].step_type, "hold")

    def test_clear(self):
        """Test clearing profile steps."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)
        self.profile.clear()
        self.assertEqual(len(self.profile.steps), 0)

    def test_get_total_duration(self):
        """Test calculating total duration."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)
        self.profile.add_ramp(0.0, 60.0)
        self.assertEqual(self.profile.get_total_duration(), 240.0)

    def test_get_total_duration_empty(self):
        """Test total duration of empty profile."""
        self.assertEqual(self.profile.get_total_duration(), 0.0)

    def test_get_step_count(self):
        """Test getting step count."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)
        self.assertEqual(self.profile.get_step_count(), 2)

    def test_get_step_at_time_first_step(self):
        """Test getting step at time during first step."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        idx, step, time_into = self.profile.get_step_at_time(30.0)
        self.assertEqual(idx, 0)
        self.assertEqual(step.step_type, "ramp")
        self.assertEqual(time_into, 30.0)

    def test_get_step_at_time_second_step(self):
        """Test getting step at time during second step."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        idx, step, time_into = self.profile.get_step_at_time(90.0)
        self.assertEqual(idx, 1)
        self.assertEqual(step.step_type, "hold")
        self.assertEqual(time_into, 30.0)

    def test_get_step_at_time_completed(self):
        """Test getting step when profile is complete."""
        self.profile.add_ramp(5.0, 60.0)

        idx, step, time_into = self.profile.get_step_at_time(100.0)
        self.assertIsNone(idx)
        self.assertIsNone(step)

    def test_get_setpoint_at_time_start(self):
        """Test setpoint at time 0."""
        self.profile.add_ramp(5.0, 60.0)
        self.assertEqual(self.profile.get_setpoint_at_time(0.0), 0.0)

    def test_get_setpoint_at_time_negative(self):
        """Test setpoint at negative time returns start voltage."""
        self.profile.add_ramp(5.0, 60.0)
        self.assertEqual(self.profile.get_setpoint_at_time(-10.0), 0.0)

    def test_get_setpoint_during_ramp(self):
        """Test setpoint interpolation during ramp."""
        self.profile.add_ramp(10.0, 100.0)

        # At 50% through ramp (50 seconds into 100 second ramp)
        setpoint = self.profile.get_setpoint_at_time(50.0)
        self.assertAlmostEqual(setpoint, 5.0, places=2)

    def test_get_setpoint_during_hold(self):
        """Test setpoint during hold step."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        # During hold, should stay at 5V
        setpoint = self.profile.get_setpoint_at_time(90.0)
        self.assertAlmostEqual(setpoint, 5.0, places=2)

    def test_get_setpoint_after_profile(self):
        """Test setpoint after profile complete."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        # After profile ends, should be at final voltage
        setpoint = self.profile.get_setpoint_at_time(500.0)
        self.assertAlmostEqual(setpoint, 5.0, places=2)

    def test_get_setpoint_complex_profile(self):
        """Test setpoint calculation for complex profile."""
        # Ramp 0->5V over 60s, hold 120s, ramp 5->10V over 60s, ramp 10->0V over 100s
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)
        self.profile.add_ramp(10.0, 60.0)
        self.profile.add_ramp(0.0, 100.0)

        # Check at various points
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(0.0), 0.0, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(30.0), 2.5, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(60.0), 5.0, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(120.0), 5.0, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(210.0), 7.5, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(240.0), 10.0, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(290.0), 5.0, places=2)
        self.assertAlmostEqual(self.profile.get_setpoint_at_time(340.0), 0.0, places=2)

    def test_get_final_voltage(self):
        """Test getting final voltage of profile."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_ramp(0.0, 60.0)
        self.assertAlmostEqual(self.profile.get_final_voltage(), 0.0, places=2)

    def test_validate_valid_profile(self):
        """Test validation of valid profile."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        is_valid, errors = self.profile.validate()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_empty_profile(self):
        """Test validation of empty profile."""
        is_valid, errors = self.profile.validate()
        self.assertFalse(is_valid)
        self.assertIn("Profile has no steps", errors)

    def test_to_dict(self):
        """Test converting profile to dictionary."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        d = self.profile.to_dict()
        self.assertEqual(d["name"], "Test Profile")
        self.assertEqual(d["start_voltage"], 0.0)
        self.assertEqual(len(d["steps"]), 2)

    def test_from_dict(self):
        """Test creating profile from dictionary."""
        data = {
            "name": "Loaded Profile",
            "description": "From dict",
            "start_voltage": 1.0,
            "current_limit": 25.0,
            "steps": [
                {"type": "ramp", "duration_sec": 60.0, "target_voltage": 5.0},
                {"type": "hold", "duration_sec": 120.0}
            ]
        }

        profile = RampProfile.from_dict(data)
        self.assertEqual(profile.name, "Loaded Profile")
        self.assertEqual(profile.start_voltage, 1.0)
        self.assertEqual(profile.current_limit, 25.0)
        self.assertEqual(len(profile.steps), 2)

    def test_save_and_load(self):
        """Test saving and loading profile to/from file."""
        self.profile.add_ramp(5.0, 60.0)
        self.profile.add_hold(120.0)

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name

        try:
            success = self.profile.save(filepath)
            self.assertTrue(success)

            # Load back
            loaded = RampProfile.load(filepath)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "Test Profile")
            self.assertEqual(len(loaded.steps), 2)
            self.assertEqual(loaded.steps[0].target_voltage, 5.0)
        finally:
            os.unlink(filepath)

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file."""
        profile = RampProfile.load("/nonexistent/path/profile.json")
        self.assertIsNone(profile)

    def test_load_invalid_json(self):
        """Test loading from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json {{{")
            filepath = f.name

        try:
            profile = RampProfile.load(filepath)
            self.assertIsNone(profile)
        finally:
            os.unlink(filepath)

    def test_repr(self):
        """Test string representation."""
        self.profile.add_ramp(5.0, 60.0)
        repr_str = repr(self.profile)
        self.assertIn("Test Profile", repr_str)
        self.assertIn("steps=1", repr_str)


class TestRampProfileEdgeCases(unittest.TestCase):
    """Test edge cases for RampProfile."""

    def test_instant_ramp(self):
        """Test profile with very short ramp duration."""
        profile = RampProfile(start_voltage=0.0)
        profile.add_ramp(10.0, 0.001)  # 1ms ramp

        # Should handle without error
        setpoint = profile.get_setpoint_at_time(0.0005)
        self.assertIsInstance(setpoint, float)

    def test_start_from_nonzero_voltage(self):
        """Test profile starting from non-zero voltage."""
        profile = RampProfile(start_voltage=5.0)
        profile.add_ramp(10.0, 100.0)

        # At start
        self.assertAlmostEqual(profile.get_setpoint_at_time(0.0), 5.0)
        # At 50%
        self.assertAlmostEqual(profile.get_setpoint_at_time(50.0), 7.5)
        # At end
        self.assertAlmostEqual(profile.get_setpoint_at_time(100.0), 10.0)

    def test_ramp_down_from_start(self):
        """Test ramping down from start voltage."""
        profile = RampProfile(start_voltage=10.0)
        profile.add_ramp(0.0, 100.0)

        # At 50%
        self.assertAlmostEqual(profile.get_setpoint_at_time(50.0), 5.0)

    def test_hold_only_profile(self):
        """Test profile with only hold steps."""
        profile = RampProfile(start_voltage=5.0)
        profile.add_hold(60.0)
        profile.add_hold(60.0)

        # Should maintain start voltage throughout
        self.assertAlmostEqual(profile.get_setpoint_at_time(0.0), 5.0)
        self.assertAlmostEqual(profile.get_setpoint_at_time(60.0), 5.0)
        self.assertAlmostEqual(profile.get_setpoint_at_time(120.0), 5.0)


if __name__ == '__main__':
    unittest.main()
