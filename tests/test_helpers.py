import unittest
from datetime import datetime
from t8_daq_system.utils.helpers import (
    format_timestamp,
    format_timestamp_filename,
    convert_temperature,
    convert_pressure,
    linear_scale,
    clamp
)

class TestHelpers(unittest.TestCase):
    def test_format_timestamp(self):
        dt = datetime(2023, 12, 15, 14, 30, 22)
        self.assertEqual(format_timestamp(dt), "2023-12-15 14:30:22")
        self.assertEqual(format_timestamp(dt, "%Y%m%d"), "20231215")

    def test_format_timestamp_filename(self):
        dt = datetime(2023, 12, 15, 14, 30, 22)
        self.assertEqual(format_timestamp_filename(dt), "20231215_143022")

    def test_convert_temperature(self):
        # C to F
        self.assertAlmostEqual(convert_temperature(0, 'C', 'F'), 32)
        self.assertAlmostEqual(convert_temperature(100, 'C', 'F'), 212)
        # F to C
        self.assertAlmostEqual(convert_temperature(32, 'F', 'C'), 0)
        self.assertAlmostEqual(convert_temperature(212, 'F', 'C'), 100)
        # C to K
        self.assertAlmostEqual(convert_temperature(0, 'C', 'K'), 273.15)
        # K to C
        self.assertAlmostEqual(convert_temperature(273.15, 'K', 'C'), 0)
        # Same unit
        self.assertEqual(convert_temperature(25, 'C', 'C'), 25)

    def test_convert_pressure(self):
        # PSI to BAR
        self.assertAlmostEqual(convert_pressure(14.5038, 'PSI', 'BAR'), 1, places=4)
        # BAR to PSI
        self.assertAlmostEqual(convert_pressure(1, 'BAR', 'PSI'), 14.5038)
        # PSI to KPA
        self.assertAlmostEqual(convert_pressure(1, 'PSI', 'KPA'), 1/0.145038)
        # Same unit
        self.assertEqual(convert_pressure(100, 'PSI', 'PSI'), 100)

    def test_linear_scale(self):
        self.assertEqual(linear_scale(0.5, 0.5, 4.5, 0, 100), 0)
        self.assertEqual(linear_scale(4.5, 0.5, 4.5, 0, 100), 100)
        self.assertEqual(linear_scale(2.5, 0.5, 4.5, 0, 100), 50)

    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(11, 0, 10), 10)

if __name__ == '__main__':
    unittest.main()
