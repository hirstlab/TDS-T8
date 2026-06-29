"""
funcgen_driver.py
Pure driver for RIGOL DG1022Z dual-channel function generators via USB-TMC/VISA.
No GUI imports.

ES5 plate rating = 5 kV/plate; EEL5000 gain = 1000x, range ±5 kV.
Cap generator output below the 5 V (=5 kV/plate) hardware ceiling to leave margin.
4.0 V -> 4 kV/plate, 1 kV margin below the 5 kV plate rating. Adjust here only.
"""

MAX_GEN_VOLTS = 4.0   # V — safety cap; never exceed at the generator output

import pyvisa


def discover() -> list:
    """
    Discover all RIGOL instruments (vendor 0x1AB1) on USB-TMC.
    Returns [{"resource": str, "idn": str, "serial": str}, ...].
    Never raises; returns [] on error or when no hardware is found.
    """
    results = []
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
    except Exception as exc:
        print(f"[funcgen_driver.discover] VISA error: {exc}")
        return []

    for resource in resources:
        if "0x1AB1" not in resource:
            continue
        try:
            inst = rm.open_resource(resource)
            inst.timeout = 3000
            inst.read_termination = "\n"
            inst.write_termination = "\n"
            idn = inst.query("*IDN?").strip()
            inst.close()
            # Serial is the token before ::INSTR in the resource string.
            # e.g. USB0::0x1AB1::0x0642::DG1ZA12345678::INSTR -> "DG1ZA12345678"
            parts = resource.split("::")
            serial = parts[-2] if len(parts) >= 2 and parts[-1] == "INSTR" else ""
            results.append({"resource": resource, "idn": idn, "serial": serial})
        except Exception as exc:
            print(f"[funcgen_driver.discover] skipping {resource}: {exc}")

    return results


class DG1022Z:
    """
    Driver for a single RIGOL DG1022Z function generator (2 channels).

    Constructor opens the VISA session and queries *IDN?.
    close() closes the VISA session ONLY — does not send *RST and does not
    disable outputs; instrument retains its state after the app exits.
    """

    def __init__(self, resource: str):
        self._resource = resource
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(resource)
        self._inst.timeout = 5000
        self._inst.read_termination = "\n"
        self._inst.write_termination = "\n"
        self._idn_str = self._inst.query("*IDN?").strip()

    # ── Generic passthroughs ────────────────────────────────────────────────

    def write(self, cmd: str):
        """Send a raw SCPI command."""
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        """Send a SCPI query and return the response."""
        return self._inst.query(cmd).strip()

    def idn(self) -> str:
        """Return the *IDN? string captured at construction time."""
        return self._idn_str

    def close(self):
        """
        Close the VISA session only.
        Does not send *RST and does not disable outputs;
        instrument retains its state after the app exits.
        """
        self._inst.close()

    # ── Per-channel waveform ─────────────────────────────────────────────────

    def set_waveform(self, channel: int, shape: str, freq_hz: float,
                     amp_vpp: float, offset_v: float, phase_deg: float) -> str:
        """
        Program a channel's waveform. Clamps amp_vpp and offset_v to
        ±MAX_GEN_VOLTS before sending. Returns a warning string if any value
        was clamped, otherwise "".

        Shape → SCPI mapping:
          Sine     → :SOURce{ch}:APPLy:SINusoid
          Triangle → :SOURce{ch}:APPLy:RAMP then 50% symmetry
                     (RIGOL has no TRIANGLE keyword; 50%-symmetry RAMP = triangle)
          Square   → :SOURce{ch}:APPLy:SQUare
          Pulse    → :SOURce{ch}:APPLy:PULSe
          DC       → :SOURce{ch}:APPLy:DC 1,1,{offset_v}
                     (DC = flat held voltage. First two args are required-by-syntax
                      placeholders the instrument ignores; the THIRD arg is the
                      held voltage. In DC mode offset_v IS the hold voltage;
                      freq and amp are irrelevant.)
        """
        warnings = []

        orig_amp = amp_vpp
        amp_vpp = max(-MAX_GEN_VOLTS, min(MAX_GEN_VOLTS, amp_vpp))
        if amp_vpp != orig_amp:
            warnings.append(f"clamped amplitude {orig_amp}->{amp_vpp} V")

        orig_off = offset_v
        offset_v = max(-MAX_GEN_VOLTS, min(MAX_GEN_VOLTS, offset_v))
        if offset_v != orig_off:
            warnings.append(f"clamped offset {orig_off}->{offset_v} V")

        ch = channel

        if shape == "Sine":
            self._inst.write(
                f":SOURce{ch}:APPLy:SINusoid {freq_hz},{amp_vpp},{offset_v},{phase_deg}"
            )
        elif shape == "Triangle":
            # RIGOL has no TRIANGLE keyword. A 50%-symmetry RAMP is a triangle.
            self._inst.write(
                f":SOURce{ch}:APPLy:RAMP {freq_hz},{amp_vpp},{offset_v},{phase_deg}"
            )
            self._inst.write(f":SOURce{ch}:FUNCtion:RAMP:SYMMetry 50")
        elif shape == "Square":
            self._inst.write(
                f":SOURce{ch}:APPLy:SQUare {freq_hz},{amp_vpp},{offset_v},{phase_deg}"
            )
        elif shape == "Pulse":
            self._inst.write(
                f":SOURce{ch}:APPLy:PULSe {freq_hz},{amp_vpp},{offset_v},{phase_deg}"
            )
        elif shape == "DC":
            # DC mode: flat held voltage. The command format requires three args:
            # :SOURce{ch}:APPLy:DC 1,1,<hold_voltage>
            # The first two are required-by-syntax placeholders the instrument ignores;
            # the THIRD argument is the held voltage. freq and amp are irrelevant in DC mode.
            self._inst.write(f":SOURce{ch}:APPLy:DC 1,1,{offset_v}")
        else:
            raise ValueError(f"Unknown shape: {shape!r}")

        return "; ".join(warnings)

    # ── Output control ───────────────────────────────────────────────────────

    def output_on(self, channel: int):
        self._inst.write(f":OUTPut{channel} ON")

    def output_off(self, channel: int):
        self._inst.write(f":OUTPut{channel} OFF")

    def set_output_load(self, channel: int, value="INFinity"):
        """
        Set the output load impedance.
        EEL5000 input is DC-coupled high-Z BNC; wrong load (e.g. 50 Ω)
        silently halves the real delivered voltage. Always use INFinity.
        value: numeric Ohms or the string "INFinity".
        """
        self._inst.write(f":OUTPut{channel}:LOAD {value}")

    # ── State readback ────────────────────────────────────────────────────────

    def get_state(self, channel: int) -> dict:
        """
        Query the current channel state. Returns:
          {"shape", "freq", "amp", "offset", "phase", "output_on", "load"}
        """
        apply_str = self.query(f":SOURce{channel}:APPLy?").strip('"')
        output_str = self.query(f":OUTPut{channel}?").strip()
        load_str = self.query(f":OUTPut{channel}:LOAD?").strip()

        # :SOURce{ch}:APPLy? returns e.g. "SIN,1000.000000,1.000000,0.000000,0.000000"
        parts = apply_str.split(",")
        shape_raw = parts[0].strip().upper() if parts else "?"
        shape_map = {
            "SIN": "Sine", "SINUSOID": "Sine",
            "RAMP": "Triangle",
            "SQU": "Square", "SQUARE": "Square",
            "PULS": "Pulse", "PULSE": "Pulse",
            "DC": "DC",
        }
        shape = shape_map.get(shape_raw, shape_raw)

        def _f(s, default=0.0):
            try:
                return float(s)
            except (ValueError, TypeError):
                return default

        freq   = _f(parts[1]) if len(parts) > 1 else 0.0
        amp    = _f(parts[2]) if len(parts) > 2 else 0.0
        offset = _f(parts[3]) if len(parts) > 3 else 0.0
        phase  = _f(parts[4]) if len(parts) > 4 else 0.0

        return {
            "shape":     shape,
            "freq":      freq,
            "amp":       amp,
            "offset":    offset,
            "phase":     phase,
            "output_on": output_str.upper() in ("ON", "1"),
            "load":      load_str,
        }

    # ── Thin utility methods ─────────────────────────────────────────────────

    def set_phase(self, channel: int, deg: float):
        self._inst.write(f":SOURce{channel}:PHASe {deg}")

    def set_duty(self, channel: int, pct: float):
        self._inst.write(f":SOURce{channel}:FUNCtion:SQUare:DCYCle {pct}")

    def set_ramp_symmetry(self, channel: int, pct: float):
        self._inst.write(f":SOURce{channel}:FUNCtion:RAMP:SYMMetry {pct}")

    # ── Sweep ────────────────────────────────────────────────────────────────

    def sweep_on(self, channel: int):
        self._inst.write(f":SOURce{channel}:SWEep:STATe ON")

    def sweep_off(self, channel: int):
        self._inst.write(f":SOURce{channel}:SWEep:STATe OFF")

    def set_sweep(self, channel: int, start_hz: float, stop_hz: float, time_s: float):
        self._inst.write(f":SOURce{channel}:SWEep:FSTart {start_hz}")
        self._inst.write(f":SOURce{channel}:SWEep:FSTOp {stop_hz}")
        self._inst.write(f":SOURce{channel}:SWEep:TIME {time_s}")

    # ── Burst ─────────────────────────────────────────────────────────────────

    def burst_on(self, channel: int):
        self._inst.write(f":SOURce{channel}:BURSt:STATe ON")

    def burst_off(self, channel: int):
        self._inst.write(f":SOURce{channel}:BURSt:STATe OFF")

    def set_burst(self, channel: int, ncycles: int, period_s: float):
        self._inst.write(f":SOURce{channel}:BURSt:NCYCles {ncycles}")
        self._inst.write(f":SOURce{channel}:BURSt:INTernal:PERiod {period_s}")

    # ── Phase alignment ───────────────────────────────────────────────────────

    def align_phase(self, channel: int):
        # Aligns the two channels of ONE instrument box, not across two boxes.
        self._inst.write(f":SOURce{channel}:PHASe:SYNChronize")

    # ── Utility ───────────────────────────────────────────────────────────────

    def beep(self):
        self._inst.write(":SYSTem:BEEPer:IMMediate")

    def get_error(self) -> str:
        """Query the error queue. Call repeatedly until "+0" to drain it."""
        return self.query(":SYSTem:ERRor?")


if __name__ == "__main__":
    instruments = discover()
    for inst in instruments:
        print(f"  Found: {inst['idn']}  serial={inst['serial']}  resource={inst['resource']}")
    print(f"[OK] funcgen_driver: discovered {len(instruments)} instrument(s)")
