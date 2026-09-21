"""
Injectable time and clock abstraction for the Rig loop and tests.

WHY THIS EXISTS
---------------
Previously, control loops used time.sleep(0.5) directly. This meant multi-hour
programs could only be tested in real time, making full program verification in
automated tests impractical or impossible.

By abstracting time through a Clock protocol, production code uses RealClock
(wrapping monotonic time and sleep), while tests use ManualClock to advance
simulated time instantly, running hours of program execution in fractions of a
second without any thread sleep.
"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol for time measurement and sleeping in the Rig module."""

    def now(self) -> float:
        """Return monotonic time in seconds."""
        ...

    def sleep_until(self, t: float) -> None:
        """Sleep until monotonic target time t (seconds)."""
        ...

    def wall_time(self) -> float:
        """Return wall-clock UNIX timestamp in seconds (for logging)."""
        ...


class RealClock:
    """Production clock using Python's time.monotonic, time.sleep, and time.time."""

    def now(self) -> float:
        return time.monotonic()

    def sleep_until(self, t: float) -> None:
        delay = t - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def wall_time(self) -> float:
        return time.time()


class ManualClock:
    """
    Test clock advanced manually via advance().

    sleep_until returns immediately so test loops never block.
    """

    def __init__(self, start_time: float = 0.0, start_wall_time: float = 1774000000.0) -> None:
        self._now = float(start_time)
        self._wall_time = float(start_wall_time)

    def now(self) -> float:
        return self._now

    def sleep_until(self, t: float) -> None:
        # Never blocks or sleeps; test advances time explicitly via advance()
        pass

    def wall_time(self) -> float:
        return self._wall_time

    def advance(self, seconds: float) -> None:
        """Advance monotonic and wall-clock time by seconds."""
        delta = float(seconds)
        self._now += delta
        self._wall_time += delta
