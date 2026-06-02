"""
Shared MockPowerSupplyController and test utilities used by conftest.py and test modules.
"""
from contextlib import contextmanager
from unittest.mock import patch

_SLEEP_PATCH = 't8_daq_system.control.program_executor.time.sleep'
_TIME_PATCH  = 't8_daq_system.control.program_executor.time.time'


@contextmanager
def fast_executor_time(tick_sec=0.5):
    """
    Patches time.sleep (no-op) and time.time (increments by tick_sec per call)
    in the executor module.  Makes TempRampBlock advance at simulated speed
    instead of real wall-clock speed — without this, a 30 K/s ramp takes
    30 real seconds even with sleep patched out.
    """
    counter = [0.0]

    def fake_time():
        counter[0] += tick_sec
        return counter[0]

    with patch(_SLEEP_PATCH), patch(_TIME_PATCH, side_effect=fake_time):
        yield


class MockPowerSupplyController:
    """Stateful in-memory mock. No LJM calls."""

    def __init__(self):
        self._voltage = 0.0
        self._current = 0.0
        self._output_on = False
        self._fio1 = 1  # 1 = shutoff asserted = output OFF
        self.rated_max_volts = 6.0
        self.rated_max_amps = 180.0
        self.voltage_limit = 6.0
        self.current_limit = 180.0
        self.interlock_active = False
        self._voltage_history = []  # list of all set_voltage calls
        self._current_history = []
        self._fio1_history = []     # list of all FIO1 states written

    def reset(self):
        self._voltage = 0.0
        self._current = 0.0
        self._output_on = False
        self._fio1 = 1
        self.interlock_active = False
        self._voltage_history.clear()
        self._current_history.clear()
        self._fio1_history.clear()

    def set_voltage(self, v):
        self._voltage = float(v)
        self._voltage_history.append(float(v))
        return True

    def set_current(self, a):
        self._current = float(a)
        self._current_history.append(float(a))
        return True

    def get_voltage(self):
        return self._voltage

    def get_current(self):
        return self._current

    def get_voltage_setpoint(self):
        return self._voltage

    def get_current_setpoint(self):
        return self._current

    def output_on(self):
        self._output_on = True
        self._fio1 = 0
        self._fio1_history.append(0)
        return True

    def output_off(self):
        self._output_on = False
        self._fio1 = 1
        self._fio1_history.append(1)
        return True

    def is_output_on(self):
        return self._output_on

    def emergency_shutdown(self):
        self.output_off()
        self._voltage = 0.0
        self._current = 0.0
        return True

    def get_readings(self):
        return {
            'PS_Voltage': self._voltage,
            'PS_Current': self._current,
            'PS_Output_On': self._output_on,
        }

    def get_status(self):
        return {
            'output_on': self._output_on,
            'voltage_setpoint': self._voltage,
            'current_setpoint': self._current,
            'voltage_actual': self._voltage,
            'current_actual': self._current,
            'errors': [],
            'in_current_limit': False,
        }

    def get_errors(self):
        return []

    def fio1_ever_high(self):
        """Returns True if FIO1 was ever asserted HIGH (output killed) after the last reset."""
        return any(v == 1 for v in self._fio1_history)

    def max_voltage_commanded(self):
        return max(self._voltage_history) if self._voltage_history else 0.0
