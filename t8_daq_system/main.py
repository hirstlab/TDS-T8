"""
main.py
PURPOSE: Application entry point for the T8 DAQ System
"""

import sys
import os
import shutil

def get_base_dir():
    """Get the base directory for the application (where the EXE or Project Root is)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_bundle_dir():
    """Get the directory where bundled files are extracted (PyInstaller _MEIPASS)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def setup_external_config(base_dir):
    """Copy bundled config and profiles to the external folder if they don't exist."""
    external_config = os.path.join(base_dir, "config")
    bundle_config = os.path.join(get_bundle_dir(), "config")
    
    # If the external config folder doesn't exist, copy the entire bundled config
    if not os.path.exists(external_config) and os.path.exists(bundle_config):
        try:
            shutil.copytree(bundle_config, external_config)
        except Exception:
            pass # Silently fail if we can't create it (e.g. permissions)

# Add the project root directory to the path for imports
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t8_daq_system.gui.main_window import MainWindow

def main():
    """Launch the T8 DAQ System application."""
    base_dir = get_base_dir()
    
    # Create the external config folder and copy defaults if missing
    setup_external_config(base_dir)
    
    # Ensure logs folder exists in the base directory
    logs_dir = os.path.join(base_dir, "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)
        
    config_path = os.path.join(base_dir, "config", "sensor_config.json")
    
    app = MainWindow(config_path=config_path if os.path.exists(config_path) else None)
    app.run()


if __name__ == "__main__":
    main()
