"""
slit_config.py
Persistent JSON-backed configuration for the raster_tool app.
All settings are stored in raster_config.json in the same directory.
"""
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raster_config.json")


class SlitConfig:
    """JSON-backed key-value store shared across all tabs."""

    def __init__(self, path: str = _CONFIG_PATH):
        self._path = path
        self._data: dict = {}
        self.load()

    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r") as fh:
                    self._data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self):
        try:
            with open(self._path, "w") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError as exc:
            print(f"[SlitConfig] save failed: {exc}")

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()

    def get_section(self, section: str) -> dict:
        return dict(self._data.get(section, {}))

    def set_section(self, section: str, mapping: dict):
        self._data[section] = dict(mapping)
        self.save()


if __name__ == "__main__":
    import tempfile
    import os
    tmp = os.path.join(tempfile.gettempdir(), "raster_test.json")
    cfg = SlitConfig(path=tmp)
    cfg.set("test_key", "test_value")
    cfg.set_section("sec", {"a": 1})
    cfg2 = SlitConfig(path=tmp)
    assert cfg2.get("test_key") == "test_value"
    assert cfg2.get_section("sec") == {"a": 1}
    os.unlink(tmp)
    print("[OK] slit_config: SlitConfig read/write OK")
