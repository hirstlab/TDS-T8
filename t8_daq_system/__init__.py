"""
LabJack T8 Data Acquisition System.

Subpackages are imported lazily to avoid pulling in heavy dependencies
(tkinter, serial, pyvisa, labjack-ljm) when only a subset of the
system is needed -- for example, during unit testing.
"""
