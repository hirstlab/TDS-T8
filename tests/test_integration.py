import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import os
import tempfile

# conftest.py handles mocking of labjack, pyvisa, serial, tkinter, matplotlib
from t8_daq_system.gui.main_window import MainWindow

class TestIntegration(unittest.TestCase):
    def setUp(self):
        # We no longer need temp config files as MainWindow uses AppSettings (Registry-backed)
        pass

    def tearDown(self):
        pass

    @patch('t8_daq_system.gui.main_window.tk.Tk')
    @patch('t8_daq_system.gui.main_window.LivePlot')
    @patch('t8_daq_system.gui.main_window.SensorPanel')
    @patch('t8_daq_system.gui.main_window.AppSettings')
    def test_main_window_init(self, mock_settings_cls, mock_sensor_panel, mock_plot, mock_tk):
        """Test that MainWindow can be instantiated with all GUI components mocked."""
        # Mock AppSettings to return a default-initialized object
        mock_settings = mock_settings_cls.return_value
        mock_settings.tc_count = 1
        mock_settings.tc_unit = "C"
        mock_settings.frg_count = 1
        mock_settings.p_unit = "mbar"
        mock_settings.sample_rate_ms = 1000
        mock_settings.display_rate_ms = 1000
        mock_settings.use_absolute_scales = True
        mock_settings.temp_range = (0.0, 2500.0)
        mock_settings.press_range = (1e-9, 1e-3)
        mock_settings.ps_v_range = (0.0, 100.0)
        mock_settings.ps_i_range = (0.0, 100.0)
        mock_settings.get_tc_type_list.return_value = ["C"]
        mock_settings.get_frg_pin_list.return_value = ["AIN2"]
        mock_settings.visa_resource = ""
        mock_settings.frg_interface = "XGS600"
        mock_settings.ps_interface = "Analog"
        
        app = MainWindow(settings=mock_settings)
        self.assertEqual(app.config['device']['type'], "T8")
        self.assertFalse(app.is_running)

if __name__ == '__main__':
    unittest.main()
