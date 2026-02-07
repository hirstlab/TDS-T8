"""
xgs600_controller.py
PURPOSE: Communicate with Agilent/Varian XGS-600 gauge controller via RS-232
KEY CONCEPT: Send text commands over serial, receive digital pressure readings directly.
Protocol: #{address}{command}{data}\r -> >{data}\r or ?FF for error
"""

import serial
import time


class XGS600Controller:
    """Serial communication interface for the XGS-600 gauge controller."""

    # Default serial settings per XGS-600 manual
    DEFAULT_BAUDRATE = 9600
    DEFAULT_TIMEOUT = 1.0
    DEFAULT_ADDRESS = "00"

    def __init__(self, port, baudrate=DEFAULT_BAUDRATE, timeout=DEFAULT_TIMEOUT,
                 address=DEFAULT_ADDRESS):
        """
        Initialize XGS-600 controller connection parameters.

        Args:
            port: Serial port (e.g., 'COM3', '/dev/ttyUSB0')
            baudrate: Baud rate (9600 or 19200)
            timeout: Read timeout in seconds
            address: Controller address ('00' for RS-232)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.address = address
        self._serial = None

    def connect(self):
        """
        Open serial port and verify connection to XGS-600.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )

            # Flush any stale data
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            # Verify connection by requesting software version
            response = self.send_command("05")
            if response is None:
                print("XGS-600: No response to version query")
                self.disconnect()
                return False

            print(f"XGS-600 connected on {self.port}, version: {response}")
            return True

        except serial.SerialException as e:
            print(f"XGS-600 connection failed on {self.port}: {e}")
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._serial = None
            return False

    def disconnect(self):
        """Close serial port."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except serial.SerialException:
                pass
        self._serial = None

    def send_command(self, command):
        """
        Send a command to the XGS-600 and return the response.

        Args:
            command: Command string without address prefix or terminator
                     (e.g., '05' for version, '02T1' for read sensor T1)

        Returns:
            Response string (without '>' prefix and '\\r' terminator),
            or None if error/timeout
        """
        if not self._serial or not self._serial.is_open:
            return None

        # Build full command: #{address}{command}\r
        full_command = f"#{self.address}{command}\r"

        try:
            # Clear input buffer before sending
            self._serial.reset_input_buffer()

            # Send command
            self._serial.write(full_command.encode('ascii'))

            # Read response until \r
            response = self._serial.read_until(b'\r', size=256)

            if not response:
                return None

            response_str = response.decode('ascii').strip('\r\n')

            # Check for error response
            if response_str.startswith('?'):
                print(f"XGS-600 error response: {response_str} for command: {command}")
                return None

            # Strip leading '>' from successful response
            if response_str.startswith('>'):
                return response_str[1:]

            return response_str

        except (serial.SerialException, serial.SerialTimeoutException) as e:
            print(f"XGS-600 serial error: {e}")
            return None

    def read_pressure(self, sensor_code):
        """
        Read pressure from a single gauge by sensor code.

        Args:
            sensor_code: Sensor identifier (e.g., 'T1' for first convection gauge,
                         'I1' for first ion gauge, or user label like 'UCHAMBER')

        Returns:
            Pressure as float (in gauge units, typically mbar), or None on error
        """
        response = self.send_command(f"02{sensor_code}")
        if response is None:
            return None

        try:
            pressure = float(response)
            return pressure
        except ValueError:
            print(f"XGS-600: Could not parse pressure '{response}' for sensor {sensor_code}")
            return None

    def read_all_pressures(self):
        """
        Read all gauges using pressure dump command (#000F).

        Returns:
            List of pressure floats (None for unparseable values),
            ordered left to right by board slot. Returns None if command fails.
        """
        response = self.send_command("0F")
        if response is None:
            return None

        pressures = []
        for value_str in response.split(','):
            value_str = value_str.strip()
            try:
                pressures.append(float(value_str))
            except ValueError:
                pressures.append(None)

        return pressures

    def read_controller_info(self):
        """
        Read installed board configuration (#0001).

        Returns:
            Response string with board codes (e.g., '10' = HFIG, '40' = CNV,
            'FE' = empty), or None on error
        """
        return self.send_command("01")

    def read_software_version(self):
        """
        Read controller software version (#0005).

        Returns:
            Version string, or None on error
        """
        return self.send_command("05")

    def is_connected(self):
        """
        Check if the controller is responsive.

        Returns:
            True if serial port is open and controller responds, False otherwise
        """
        if not self._serial or not self._serial.is_open:
            return False

        try:
            response = self.send_command("05")
            return response is not None
        except Exception:
            return False
