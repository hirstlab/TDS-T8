"""Test Keysight power supply ethernet connection"""
import pyvisa

# Create resource manager
try:
    rm = pyvisa.ResourceManager('@py')
    print("Using pyvisa-py backend")
except:
    rm = pyvisa.ResourceManager()
    print("Using NI-VISA backend")

print("\n" + "=" * 60)
print("AVAILABLE VISA RESOURCES:")
print("=" * 60)
resources = rm.list_resources()
if resources:
    for r in resources:
        print(f"  {r}")
else:
    print("  No resources found")

# Try to connect to the Keysight power supply
resource_string = "TCPIP0::169.254.57.0::inst0::INSTR"
print("\n" + "=" * 60)
print(f"CONNECTING TO: {resource_string}")
print("=" * 60)

try:
    instr = rm.open_resource(resource_string, open_timeout=5000)
    instr.timeout = 5000
    instr.read_termination = '\n'
    instr.write_termination = '\n'

    print("✓ Connection opened successfully")

    # Query identity
    print("\nQuerying device identity (*IDN?)...")
    idn = instr.query("*IDN?")
    print(f"✓ Device responded: {idn.strip()}")

    # Try reading voltage
    print("\nReading measured voltage (MEAS:VOLT?)...")
    voltage = instr.query("MEAS:VOLT?")
    print(f"✓ Voltage: {voltage.strip()} V")

    # Try reading current
    print("\nReading measured current (MEAS:CURR?)...")
    current = instr.query("MEAS:CURR?")
    print(f"✓ Current: {current.strip()} A")

    # Check output state
    print("\nChecking output state (OUTP?)...")
    output_state = instr.query("OUTP?")
    print(f"✓ Output is: {'ON' if output_state.strip() == '1' else 'OFF'}")

    instr.close()
    print("\n" + "=" * 60)
    print("✓✓✓ CONNECTION TEST PASSED! ✓✓✓")
    print("=" * 60)
    print("\nYour configuration is correct. The main application should work.")

except pyvisa.errors.VisaIOError as e:
    print(f"\n✗ VISA Error: {e}")
    print("\n" + "=" * 60)
    print("TROUBLESHOOTING STEPS:")
    print("=" * 60)
    print("1. Ping test already passed (169.254.57.0 responds)")
    print("2. Try alternate resource string format:")
    print("   TCPIP0::169.254.57.0::5025::SOCKET")
    print("3. Check if Windows Firewall is blocking Python")
    print("4. Make sure pyvisa-py is installed:")
    print("   pip install pyvisa-py")
    print("5. Try rebooting the Keysight power supply")

except Exception as e:
    print(f"\n✗ Unexpected error: {e}")
    print("\nFull error details:")
    import traceback

    traceback.print_exc()