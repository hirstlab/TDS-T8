"""
frg702_reader.py
PURPOSE: Read Leybold FRG-702 full-range gauge (Pirani + Cold Cathode) via XGS-600 controller
KEY CONCEPT: XGS-600 provides digital pressure readings over RS-232, eliminating
analog voltage conversion. Pressure values are read directly from the controller.
"""


# Unit conversion factors from mbar
UNIT_CONVERSIONS = {
    'mbar': 1.0,
    'Torr': 0.750062,
    'Pa': 100.0,
}


class FRG702Reader:
    def __init__(self, xgs600_controller, frg702_config_list):
        """
        Initialize FRG-702 gauge reader via XGS-600.

        Args:
            xgs600_controller: The XGS600Controller instance
            frg702_config_list: List of FRG-702 gauge configs from JSON
        """
        self.controller = xgs600_controller
        self.gauges = frg702_config_list

    @staticmethod
    def convert_pressure(mbar_value, to_unit):
        """
        Convert pressure from mbar to the specified unit.

        Args:
            mbar_value: Pressure in mbar
            to_unit: Target unit ('mbar', 'Torr', or 'Pa')

        Returns:
            Converted pressure value
        """
        factor = UNIT_CONVERSIONS.get(to_unit, 1.0)
        return mbar_value * factor

    def read_all(self):
        """
        Read all enabled FRG-702 gauges via XGS-600.

        Returns:
            dict like {'FRG702_Chamber': 1.5e-6} or {'FRG702_Chamber': None}
            Values are pressure in mbar, or None for error states.
        """
        readings = {}

        for gauge in self.gauges:
            if not gauge['enabled']:
                continue

            sensor_code = gauge['sensor_code']

            try:
                pressure = self.controller.read_pressure(sensor_code)
                readings[gauge['name']] = pressure
            except Exception as e:
                print(f"Error reading {gauge['name']}: {e}")
                readings[gauge['name']] = None

        return readings

    def read_all_with_status(self):
        """
        Read all enabled FRG-702 gauges, returning pressure and status.

        Returns:
            dict like {'FRG702_Chamber': {'pressure': 1.5e-6, 'status': 'valid'}}
        """
        readings = {}

        for gauge in self.gauges:
            if not gauge['enabled']:
                continue

            sensor_code = gauge['sensor_code']

            try:
                pressure = self.controller.read_pressure(sensor_code)

                if pressure is not None:
                    readings[gauge['name']] = {
                        'pressure': pressure,
                        'status': 'valid',
                    }
                else:
                    readings[gauge['name']] = {
                        'pressure': None,
                        'status': 'error',
                    }

            except Exception as e:
                print(f"Error reading {gauge['name']}: {e}")
                readings[gauge['name']] = {
                    'pressure': None,
                    'status': 'error',
                }

        return readings

    def read_single(self, channel_name):
        """
        Read just one FRG-702 gauge by name.

        Args:
            channel_name: Name of the gauge to read

        Returns:
            Pressure in mbar, or None if not found/error
        """
        for gauge in self.gauges:
            if gauge['name'] == channel_name and gauge['enabled']:
                try:
                    return self.controller.read_pressure(gauge['sensor_code'])
                except Exception as e:
                    print(f"Error reading {channel_name}: {e}")
                    return None
        return None

    def get_enabled_channels(self):
        """Get list of enabled FRG-702 gauge names."""
        return [g['name'] for g in self.gauges if g['enabled']]
