"""
Unit tests for Clock protocols and implementations.
"""
from t8_daq_system.rig.clock import Clock, ManualClock, RealClock


def test_real_clock_protocol():
    clock = RealClock()
    assert isinstance(clock, Clock)
    t1 = clock.now()
    wt = clock.wall_time()
    assert isinstance(t1, float)
    assert isinstance(wt, float)
    assert wt > 0.0


def test_manual_clock_advance():
    clock = ManualClock(start_time=100.0, start_wall_time=1000.0)
    assert isinstance(clock, Clock)
    assert clock.now() == 100.0
    assert clock.wall_time() == 1000.0

    clock.advance(2.5)
    assert clock.now() == 102.5
    assert clock.wall_time() == 1002.5


def test_manual_clock_sleep_until_never_blocks():
    clock = ManualClock(start_time=0.0, start_wall_time=1000.0)
    # Calling sleep_until with a future time must return immediately without advancing
    clock.sleep_until(100.0)
    assert clock.now() == 0.0
    assert clock.wall_time() == 1000.0
