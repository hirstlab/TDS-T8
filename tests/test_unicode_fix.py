import pytest
from t8_daq_system.core.data_acquisition import DataAcquisition

def test_acquisition_print_strings_encodable():
    """
    Test that the strings used in data_acquisition.py print calls 
    are encodable in common terminal encodings like cp1252.
    """
    # Specifically check the arrow character replacement
    # Setpoints -> Monitor
    test_str = "Setpoint -> V=0.0000V  A=10.0000A  |  DAC_V=0.0000V  DAC_A=0.0000V  |  Monitor -> V=0.0000V"
    
    # This should not raise UnicodeEncodeError in cp1252
    try:
        test_str.encode('cp1252')
    except UnicodeEncodeError:
        pytest.fail("Fix failed: string still contains non-cp1252 characters")

def test_timing_report_encodable():
    """Test that timing report strings are encodable."""
    report = "Avg acquisition time: 10.5ms, Max: 20.0ms (target: 200ms)"
    try:
        report.encode('cp1252')
    except UnicodeEncodeError:
        pytest.fail("Timing report contains non-cp1252 characters")
