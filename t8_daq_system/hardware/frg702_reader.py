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

# Status constants
STATUS_VALID = 'valid'
STATUS_UNDERRANGE = 'underrange'
STATUS_OVERRANGE = 'overrange'
STATUS_SENSOR_ERROR_NO_SUPPLY = 'sensor_error_no_supply'
STATUS_SENSOR_ERROR_PIRANI_DEFECTIVE = 'sensor_error_pirani_defective'

# Operating mode constants
MODE_PIRANI_ONLY = 'Pirani'
MODE_COMBINED = 'Combined'
MODE_UNKNOWN = 'Unknown'


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

    @staticmethod
    def voltage_to_pressure_mbar(voltage):
        """
        DEPRECATED: Used for analog readings. Convert voltage to pressure in mbar.
        Formula from Leybold FRG-702 manual: p = 10^(1.667*U - 11.33) [mbar]

        Returns:
            (pressure, status) - pressure is None if status is not valid
        """
        if voltage is None:
            return None, STATUS_VALID  # Or some other default

        if voltage < 0.5:
            return None, STATUS_SENSOR_ERROR_NO_SUPPLY
        if voltage < 1.82:
            return None, STATUS_UNDERRANGE
        if voltage > 9.5:
            return None, STATUS_SENSOR_ERROR_PIRANI_DEFECTIVE
        if voltage > 8.6:
            return None, STATUS_OVERRANGE

        # Valid range: 1.82V to 8.6V (5e-9 to 1000 mbar)
        pressure = 10 ** (1.667 * voltage - 11.33)
        return pressure, STATUS_VALID

    @staticmethod
    def read_operating_mode(status_voltage):
        """
        DEPRECATED: Used for analog readings. Determine mode from Pin 6 voltage.
        < 5V: Pirani only
        > 5V: Combined (Pirani + Cold Cathode)
        """
        if status_voltage is None:
            return MODE_UNKNOWN
        if status_voltage >= 5.0:
            return MODE_COMBINED
        return MODE_PIRANI_ONLY

    def read_all(self):
        """
        Read all enabled FRG-702 gauges via XGS-600.

        Returns:
            dict like {'FRG702_Chamber': 1.5e-6} or {'FRG702_Chamber': None}
            Values are pressure in mbar, or None for error states.
        """
        readings = {}

        # Fail fast if controller not connected
        if not self.controller.is_connected():
            return {g['name']: None for g in self.gauges if g['enabled']}

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

        # Fail fast if controller not connected
        if not self.controller.is_connected():
            return {
                g['name']: {
                    'pressure': None,
                    'status': 'error',
                    'mode': MODE_UNKNOWN
                } for g in self.gauges if g['enabled']
            }

        for gauge in self.gauges:
            if not gauge['enabled']:
                continue

            sensor_code = gauge['sensor_code']

            try:
                pressure = self.controller.read_pressure(sensor_code)

                if pressure is not None:
                    readings[gauge['name']] = {
                        'pressure': pressure,
                        'status': STATUS_VALID,
                        'mode': MODE_UNKNOWN,
                    }
                else:
                    readings[gauge['name']] = {
                        'pressure': None,
                        'status': 'error',
                        'mode': MODE_UNKNOWN,
                    }

            except Exception as e:
                print(f"Error reading {gauge['name']}: {e}")
                readings[gauge['name']] = {
                    'pressure': None,
                    'status': 'error',
                    'mode': MODE_UNKNOWN,
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
