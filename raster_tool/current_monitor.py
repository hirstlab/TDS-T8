"""
current_monitor.py
Beam current monitor read loop. Pure logic — no GUI imports.
Polls a hardware interface at a fixed interval and stores the latest reading.
The GUI uses a QTimer to sample self.latest_ua at its own display rate.
"""
import threading
import time


class CurrentMonitor:
    DEFAULT_INTERVAL_S = 0.5

    def __init__(self, device=None, interval_s: float = DEFAULT_INTERVAL_S):
        self._device = device
        self._interval_s = interval_s
        self._running = False
        self._thread = None
        self.latest_ua = None   # microamps; None = no reading yet

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                if self._device is not None:
                    self.latest_ua = self._device.read_current_ua()
                else:
                    self.latest_ua = None
            except Exception as exc:
                print(f"[CurrentMonitor] read error: {exc}")
                self.latest_ua = None
            time.sleep(self._interval_s)


if __name__ == "__main__":
    mon = CurrentMonitor()
    mon.start()
    time.sleep(0.1)
    mon.stop()
    print("[OK] current_monitor: CurrentMonitor start/stop OK")
