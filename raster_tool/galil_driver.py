"""
galil_driver.py
Pure driver for Galil DMC motion controllers. No GUI imports.
"""


class GalilController:
    def __init__(self, address="192.168.1.12", timeout=5.0):
        self._address = address
        self._timeout = timeout
        self._connected = False

    def connect(self) -> bool:
        try:
            # Real: import gclib; self._g = gclib.py()
            # self._g.GOpen(f"--address {self._address} --port 60007 --subscribe ALL")
            self._connected = True
            return True
        except Exception as exc:
            print(f"[GalilController] connect failed: {exc}")
            return False

    def disconnect(self):
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def move_to(self, axis: str, position: float):
        if not self._connected:
            return
        # Real: self._g.GCommand(f"PA{axis}={position}; BG{axis}")
        print(f"[GalilController] move {axis} to {position}")

    def get_position(self, axis: str) -> float:
        if not self._connected:
            return 0.0
        # Real: return float(self._g.GCommand(f"TP{axis}"))
        return 0.0

    def stop(self, axis: str):
        if not self._connected:
            return
        # Real: self._g.GCommand(f"ST{axis}")
        print(f"[GalilController] stop {axis}")


if __name__ == "__main__":
    g = GalilController()
    print(f"[OK] galil_driver: GalilController instantiated, connected={g.is_connected()}")
