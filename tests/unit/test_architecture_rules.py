"""
Architecture rules test suite.

Enforces package boundary invariants using AST scanning.

WHY THIS EXISTS
---------------
ADR 0002 mandates that only the Rig module owns hardware I/O and communicates
with labjack / serial devices. Leaking hardware calls or UI imports into
pure logic packages degrades testability, causes race conditions, and violates
the target single-thread single-loop architecture.
"""
from __future__ import annotations

import ast
from pathlib import Path
import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "t8_daq_system"


def _iter_python_files(base_dir: Path):
    """Yield all .py files under base_dir."""
    for p in base_dir.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p


def _get_imports(file_path: Path) -> list[tuple[int, str]]:
    """Parse a python file and return list of (lineno, imported_module_name)."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.lineno, node.module))
    return imports


def test_labjack_and_serial_only_under_hardware():
    """
    Rule 1: `labjack` and `serial` can be imported ONLY under `t8_daq_system/hardware/`.
    No other package in t8_daq_system may import them.
    """
    forbidden_modules = ("labjack", "serial")
    violations = []

    for py_file in _iter_python_files(PACKAGE_ROOT):
        rel_parts = py_file.relative_to(PACKAGE_ROOT).parts
        if rel_parts[0] == "hardware":
            continue

        for lineno, mod_name in _get_imports(py_file):
            root_mod = mod_name.split(".")[0]
            if root_mod in forbidden_modules:
                violations.append(f"{py_file.relative_to(REPO_ROOT)}:{lineno} imports {mod_name}")

    assert not violations, "Forbidden hardware library imports outside hardware/:\n" + "\n".join(violations)


def test_hardware_imported_only_under_rig_and_transitional_list():
    """
    Rule 2: `t8_daq_system.hardware` is imported only under `rig/` and allowed transitional files.
    """
    # Explicit list of transitional importers outside rig/ that still exist today.
    # Each entry includes a comment naming the ticket that removes it.
    TRANSITIONAL_ALLOWED = {
        # Ticket 14: DataAcquisition deletion
        Path("t8_daq_system/core/data_acquisition.py"),
        # Ticket 05/10: MainWindow transitional PS access / reader references
        Path("t8_daq_system/gui/main_window.py"),
        # Ticket 12: live_plot pressure conversion cleanup
        Path("t8_daq_system/gui/live_plot.py"),
        # Ticket 12: sensor_panel status codes cleanup
        Path("t8_daq_system/gui/sensor_panel.py"),
    }

    violations = []

    for py_file in _iter_python_files(PACKAGE_ROOT):
        rel_parts = py_file.relative_to(PACKAGE_ROOT).parts
        rel_path = py_file.relative_to(REPO_ROOT)

        if rel_parts[0] in ("hardware", "rig"):
            continue

        if rel_path in TRANSITIONAL_ALLOWED:
            continue

        for lineno, mod_name in _get_imports(py_file):
            if mod_name.startswith("t8_daq_system.hardware") or mod_name.startswith("hardware"):
                violations.append(f"{rel_path}:{lineno} imports {mod_name}")

    assert not violations, "Forbidden t8_daq_system.hardware imports outside rig/ and transitional allowlist:\n" + "\n".join(violations)


def test_no_tkinter_or_gui_under_control_data_rig_settings():
    """
    Rule 3: No tkinter or gui imports under control/, data/, rig/, settings/.
    """
    forbidden_roots = ("tkinter", "t8_daq_system.gui", "gui")
    pure_subpackages = ("control", "data", "rig", "settings")
    violations = []

    for subpkg in pure_subpackages:
        subpkg_dir = PACKAGE_ROOT / subpkg
        if not subpkg_dir.exists():
            continue
        for py_file in _iter_python_files(subpkg_dir):
            rel_path = py_file.relative_to(REPO_ROOT)
            for lineno, mod_name in _get_imports(py_file):
                for f_root in forbidden_roots:
                    if mod_name == f_root or mod_name.startswith(f"{f_root}."):
                        violations.append(f"{rel_path}:{lineno} imports {mod_name}")

    assert not violations, "Forbidden GUI imports in pure logic packages:\n" + "\n".join(violations)
