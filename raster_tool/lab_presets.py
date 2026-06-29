"""
lab_presets.py
Named lab presets stored in raster_config.json under the "presets" section.
Reuses SlitConfig for the backing store.
"""
from slit_config import SlitConfig


class LabPresets:
    """Manage named configuration presets within the shared SlitConfig."""

    SECTION = "lab_presets"

    def __init__(self, config: SlitConfig):
        self._cfg = config

    def list_presets(self) -> list:
        return list(self._cfg.get_section(self.SECTION).keys())

    def save_preset(self, name: str, data: dict):
        section = self._cfg.get_section(self.SECTION)
        section[name] = data
        self._cfg.set_section(self.SECTION, section)

    def load_preset(self, name: str) -> dict:
        return self._cfg.get_section(self.SECTION).get(name, {})

    def delete_preset(self, name: str):
        section = self._cfg.get_section(self.SECTION)
        section.pop(name, None)
        self._cfg.set_section(self.SECTION, section)


if __name__ == "__main__":
    import tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), "raster_presets_test.json")
    cfg = SlitConfig(path=tmp)
    presets = LabPresets(cfg)
    presets.save_preset("test", {"x": 1, "y": 2})
    assert presets.load_preset("test") == {"x": 1, "y": 2}
    assert "test" in presets.list_presets()
    presets.delete_preset("test")
    assert "test" not in presets.list_presets()
    os.unlink(tmp)
    print("[OK] lab_presets: LabPresets save/load/delete OK")
