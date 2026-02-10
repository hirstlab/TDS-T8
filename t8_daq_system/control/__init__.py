"""
Control module for the T8 DAQ System.

This module provides control logic for:
- Ramp profiles: Define heating/cooling sequences
- Ramp executor: Execute profiles in a background thread
- Safety monitor: Temperature limits and emergency shutoff
"""
