"""
feedforward_map.py
PURPOSE: Rate-indexed feedforward voltage map for the temperature ramp PID.

Replaces the fictional single voltage->temperature table with a self-building
map keyed by ramp rate (K/min). For unseen rates it interpolates between the
two nearest stored rates. Ingests historical CSVs at startup and appends live
run data after every ramp to improve coverage over time.

FF-5
"""

import csv
import json
import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(__file__)
_MAP_PATH      = os.path.normpath(os.path.join(_HERE, '..', 'config', 'feedforward_map.json'))
_MANIFEST_PATH = os.path.normpath(os.path.join(_HERE, '..', 'config', 'feedforward_ingest_manifest.json'))

_V_MAX             = 6.0
_TEMP_BIN_SIZE     = 50    # °C bin width for ingest / append
_RATE_SNAP_THRESH  = 5.0   # K/min: snap to nearest known rate within this tolerance
_MIN_BIN_SAMPLES   = 3     # min voltage readings per bin before updating the map
_DERIV_HALF_WIN    = 5     # half-window (samples) for dT/dt estimation
_SLOPE_JUMP_FACTOR = 1.5   # zone-boundary: slope increases by this ratio


# ── Public data types ──────────────────────────────────────────────────────────

@dataclass
class Zone:
    """One gain-scheduling zone within a block."""
    t_lo: float        # lower temperature boundary °C
    t_hi: float        # upper temperature boundary °C
    mean_slope: float  # mean dV/dT (V/°C) across this zone


# ── Map class ──────────────────────────────────────────────────────────────────

class FeedforwardMap:
    """
    Rate-indexed feedforward voltage map.

    Internal structure:
        _data: dict[str, list[list[float]]]
        Keys are rate strings in K/min (e.g. "5", "10", "25").
        Values are [[temp_C, voltage_V], ...] sorted ascending by temperature.

    Thread-safety: load() and save() should be called from a single thread.
    voltage_for() and zones_for() are read-only and safe to call from any thread
    once the map is loaded.
    """

    def __init__(self, map_path: str = None, manifest_path: str = None):
        self._map_path      = map_path      or _MAP_PATH
        self._manifest_path = manifest_path or _MANIFEST_PATH
        self._data: dict    = {}
        self._unseen_warned = set()   # rates already logged as out-of-range

    # ── Public API ─────────────────────────────────────────────────────────────

    def load(self):
        """Load the map from disk. Safe to call multiple times."""
        # FF-5 START — load
        try:
            with open(self._map_path, 'r') as f:
                raw = json.load(f)
            self._data = {
                k: [[float(p[0]), float(p[1])] for p in v]
                for k, v in raw.items()
                if not k.startswith('_') and isinstance(v, list)
            }
            logger.info("[FeedforwardMap] Loaded %d rate curves", len(self._data))
        except FileNotFoundError:
            logger.warning("[FeedforwardMap] Map file not found at %s — starting empty", self._map_path)
        except Exception as exc:
            logger.error("[FeedforwardMap] Load error: %s", exc)
        # FF-5 END

    def voltage_for(self, rate_k_per_min: float, temp_c: float) -> float:
        """
        Return feedforward voltage for the given rate and temperature.

        - Exact rate: interpolates within that curve.
        - Between two stored rates: blends linearly between them.
        - Outside stored range: extrapolates from nearest curve (clamped, no runaway).
        - Output always clamped to [0.0, 6.0].
        """
        # FF-5 START — voltage_for
        if not self._data:
            return 0.0

        rates = sorted(float(k) for k in self._data)

        if rate_k_per_min <= rates[0]:
            if rate_k_per_min < rates[0] and rate_k_per_min not in self._unseen_warned:
                logger.info("[FeedforwardMap] Rate %.1f K/min below stored range — using %.1f", rate_k_per_min, rates[0])
                self._unseen_warned.add(rate_k_per_min)
            return max(0.0, min(_V_MAX, self._interp_curve(_rkey(rates[0]), temp_c)))

        if rate_k_per_min >= rates[-1]:
            if rate_k_per_min > rates[-1] and rate_k_per_min not in self._unseen_warned:
                logger.info("[FeedforwardMap] Rate %.1f K/min above stored range — using %.1f", rate_k_per_min, rates[-1])
                self._unseen_warned.add(rate_k_per_min)
            return max(0.0, min(_V_MAX, self._interp_curve(_rkey(rates[-1]), temp_c)))

        lo = max(r for r in rates if r <= rate_k_per_min)
        hi = min(r for r in rates if r >= rate_k_per_min)
        if lo == hi:
            return max(0.0, min(_V_MAX, self._interp_curve(_rkey(lo), temp_c)))

        v_lo = self._interp_curve(_rkey(lo), temp_c)
        v_hi = self._interp_curve(_rkey(hi), temp_c)
        t    = (rate_k_per_min - lo) / (hi - lo)
        return max(0.0, min(_V_MAX, v_lo + t * (v_hi - v_lo)))
        # FF-5 END

    def zones_for(self, rate_k_per_min: float,
                  t_start_c: float, t_end_c: float) -> List[Zone]:
        """
        Auto-detect gain-scheduling zones from slope changes in the rate curve.

        Walks the stored curve for the nearest rate, finds knees where dV/dT
        increases by > 1.5×, and returns up to 4 Zone objects.
        """
        # FF-5 START — zones_for
        if not self._data:
            return [Zone(t_start_c, t_end_c, 0.0)]

        rates  = sorted(float(k) for k in self._data)
        nearest = min(rates, key=lambda r: abs(r - rate_k_per_min))
        curve   = [
            (float(t), float(v))
            for t, v in self._data[_rkey(nearest)]
            if t_start_c - 1 <= float(t) <= t_end_c + 1
        ]
        if len(curve) < 2:
            return [Zone(t_start_c, t_end_c, 0.0)]

        slopes = []
        for i in range(len(curve) - 1):
            t0, v0 = curve[i]
            t1, v1 = curve[i + 1]
            dt = t1 - t0
            if dt > 0:
                slopes.append((t0, t1, (v1 - v0) / dt))
        if not slopes:
            return [Zone(t_start_c, t_end_c, 0.0)]

        mean_slope  = sum(s for _, _, s in slopes) / len(slopes)
        boundaries  = [t_start_c]

        for i in range(1, len(slopes)):
            _, _, s_prev = slopes[i - 1]
            t_cur, _, s_cur = slopes[i]
            if s_prev > 1e-6 and s_cur / s_prev > _SLOPE_JUMP_FACTOR:
                boundaries.append(t_cur)

        boundaries.append(t_end_c)
        while len(boundaries) > 5:   # cap at 4 zones
            boundaries.pop(-2)

        zones = []
        for i in range(len(boundaries) - 1):
            t_lo = boundaries[i]
            t_hi = boundaries[i + 1]
            seg  = [s for t0, t1, s in slopes if t0 >= t_lo - 1 and t1 <= t_hi + 1]
            ms   = sum(seg) / len(seg) if seg else mean_slope
            zones.append(Zone(t_lo, t_hi, ms))

        return zones or [Zone(t_start_c, t_end_c, mean_slope)]
        # FF-5 END

    def ingest_csv(self, path: str):
        """
        Parse one data-log CSV and merge temp/voltage data into the map.

        Accepts any CSV produced by DataLogger: finds the first TC_ column for
        temperature, and PS_Voltage_Setpoint (or PS_Voltage) for voltage.
        Derives ramp rate from numerical dT/dt and snaps to the nearest stored rate.
        Saves the map to disk only when new data is actually added.
        """
        # FF-5 START — ingest_csv
        try:
            timestamps, temps, volts = _parse_csv(path)
        except Exception as exc:
            logger.debug("[FeedforwardMap] ingest_csv %s: %s", os.path.basename(path), exc)
            return

        n = len(timestamps)
        if n < _DERIV_HALF_WIN * 2 + 1:
            return

        known_rates = [float(k) for k in self._data]
        if not known_rates:
            return

        # Compute per-sample dT/dt (K/min) with a symmetric sliding window
        derived_rates = [None] * n
        for i in range(_DERIV_HALF_WIN, n - _DERIV_HALF_WIN):
            t0, t1   = timestamps[i - _DERIV_HALF_WIN], timestamps[i + _DERIV_HALF_WIN]
            tc0, tc1 = temps[i - _DERIV_HALF_WIN],      temps[i + _DERIV_HALF_WIN]
            if None in (t0, t1, tc0, tc1):
                continue
            dt_sec = t1 - t0
            if dt_sec > 0:
                derived_rates[i] = (tc1 - tc0) / dt_sec * 60.0

        accumulated = {}   # rate_key -> {temp_bin -> [voltages]}
        for rate, temp, volt in zip(derived_rates, temps, volts):
            if rate is None or rate < 0.5:
                continue
            if temp is None or temp < 50:
                continue
            if volt is None or volt < 0.05:
                continue
            nearest = min(known_rates, key=lambda r: abs(r - rate))
            if abs(nearest - rate) > _RATE_SNAP_THRESH:
                continue
            rk = _rkey(nearest)
            tb = round(temp / _TEMP_BIN_SIZE) * _TEMP_BIN_SIZE
            accumulated.setdefault(rk, {}).setdefault(tb, []).append(volt)

        changed = False
        for rk, bins in accumulated.items():
            existing = {int(t): v for t, v in self._data.get(rk, [])}
            for tb, vlist in bins.items():
                if len(vlist) < _MIN_BIN_SAMPLES:
                    continue
                existing[tb] = sorted(vlist)[len(vlist) // 2]  # median
                changed = True
            if existing:
                curve = _enforce_monotonicity(sorted(existing.items()))
                self._data[rk] = [[t, v] for t, v in curve]

        if changed:
            self._save()
        # FF-5 END

    def append_run(self, run_log: list, rate_k_per_min: float):
        """
        Merge the in-memory tick log from a completed run into the map.

        run_log: list of (elapsed_sec, setpoint_k, actual_k, voltage_v).
        Saves the map to disk when new data is added.
        """
        # FF-5 START — append_run
        known_rates = [float(k) for k in self._data]
        if not known_rates or not run_log:
            return

        nearest = min(known_rates, key=lambda r: abs(r - rate_k_per_min))
        if abs(nearest - rate_k_per_min) > _RATE_SNAP_THRESH:
            logger.info("[FeedforwardMap] append_run: %.1f K/min not near any stored rate — skipping", rate_k_per_min)
            return

        rk   = _rkey(nearest)
        bins: dict = {}
        for _elapsed, _sp_k, actual_k, voltage_v in run_log:
            temp_c = actual_k - 273.15
            if temp_c < 50 or voltage_v < 0.05:
                continue
            tb = round(temp_c / _TEMP_BIN_SIZE) * _TEMP_BIN_SIZE
            bins.setdefault(tb, []).append(voltage_v)

        existing = {int(t): v for t, v in self._data.get(rk, [])}
        changed  = False
        for tb, vlist in bins.items():
            if len(vlist) < _MIN_BIN_SAMPLES:
                continue
            existing[tb] = sorted(vlist)[len(vlist) // 2]
            changed = True

        if changed:
            curve = _enforce_monotonicity(sorted(existing.items()))
            self._data[rk] = [[t, v] for t, v in curve]
            self._save()
        # FF-5 END

    def scan_log_folder(self, log_folder: str):
        """
        Ingest all un-seen CSVs found by a recursive walk of log_folder.

        Uses a manifest file (feedforward_ingest_manifest.json) keyed by file
        path + mtime so previously ingested files are skipped.  Safe to call
        from a background thread.
        """
        # FF-8 START — startup ingest scan
        manifest = self._load_manifest()
        changed  = False
        count    = 0

        for dirpath, _dirs, files in os.walk(log_folder):
            for fname in files:
                if not fname.endswith('.csv'):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue
                if manifest.get(fpath) == mtime:
                    continue
                self.ingest_csv(fpath)
                manifest[fpath] = mtime
                changed = True
                count  += 1

        if changed:
            self._save_manifest(manifest)
        if count:
            logger.info("[FeedforwardMap] scan_log_folder: ingested %d new CSV(s)", count)
        # FF-8 END

    # ── Private helpers ────────────────────────────────────────────────────────

    def _interp_curve(self, rate_key: str, temp_c: float) -> float:
        """Linearly interpolate voltage at temp_c from the stored curve."""
        curve = self._data.get(rate_key, [])
        if not curve:
            return 0.0
        if temp_c <= curve[0][0]:
            return curve[0][1]
        if temp_c >= curve[-1][0]:
            return curve[-1][1]
        for i in range(len(curve) - 1):
            t0, v0 = curve[i]
            t1, v1 = curve[i + 1]
            if t0 <= temp_c <= t1:
                frac = (temp_c - t0) / (t1 - t0) if t1 != t0 else 0.0
                return v0 + frac * (v1 - v0)
        return curve[-1][1]

    def _save(self):
        """Write the current map to disk (atomic-ish: write then replace)."""
        try:
            out = {
                '_comment': (
                    'Rate-indexed feedforward map. Keys are K/min rates (strings). '
                    'Values are [temp_C, voltage_V] pairs sorted ascending by temperature. '
                    'Updated automatically by FeedforwardMap.ingest_csv / append_run.'
                )
            }
            out.update(self._data)
            tmp = self._map_path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(out, f, indent=2)
            os.replace(tmp, self._map_path)
        except Exception as exc:
            logger.error("[FeedforwardMap] Save error: %s", exc)

    def _load_manifest(self) -> dict:
        try:
            with open(self._manifest_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_manifest(self, manifest: dict):
        try:
            with open(self._manifest_path, 'w') as f:
                json.dump(manifest, f)
        except Exception as exc:
            logger.debug("[FeedforwardMap] Manifest save error: %s", exc)


# ── Module-level helpers ───────────────────────────────────────────────────────

def _rkey(rate: float) -> str:
    """Canonical string key for a rate value (e.g. 10.0 → '10')."""
    return str(int(round(rate)))


def _enforce_monotonicity(curve: list) -> list:
    """
    Remove points that would cause voltage to decrease with temperature.
    Input/output: list of (temp_C, voltage_V) tuples sorted by temp_C.
    """
    result = []
    max_v  = -float('inf')
    for t, v in curve:
        if v >= max_v:
            result.append((t, v))
            max_v = v
    return result


def _parse_csv(path: str):
    """
    Parse a T8 data-log CSV into parallel (timestamps_sec, temps_C, voltages_V) lists.

    Finds the first TC_ column (temperature, no _rawV suffix) and
    PS_Voltage_Setpoint or PS_Voltage for the commanded voltage.
    Raises ValueError if required columns are not found.
    """
    from datetime import datetime

    timestamps: list = []
    temps:      list = []
    volts:      list = []
    tc_col   = None
    volt_col = None
    tc_idx   = None
    volt_idx = None
    header   = None

    with open(path, 'r', newline='', encoding='utf-8', errors='replace') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')

            # Extract column hints from #META: line
            if line.startswith('#META:'):
                try:
                    meta = json.loads(line[6:])
                    sensors_raw = meta.get('sensors', '')
                    sensors = (
                        [s.strip() for s in sensors_raw.split(',')]
                        if isinstance(sensors_raw, str) else list(sensors_raw)
                    )
                    for s in sensors:
                        if tc_col is None and s.startswith('TC_') and not s.endswith('_rawV'):
                            tc_col = s
                        if volt_col is None and s == 'PS_Voltage_Setpoint':
                            volt_col = s
                    if volt_col is None and 'PS_Voltage' in sensors:
                        volt_col = 'PS_Voltage'
                except Exception:
                    pass
                continue

            if line.startswith('#'):
                continue

            row = next(csv.reader([line]))
            if not row:
                continue

            if row[0] == 'Timestamp':
                header = row
                # Resolve column indices
                for col in header[1:]:
                    if tc_col is None and col.startswith('TC_') and not col.endswith('_rawV'):
                        tc_col = col
                if volt_col is None:
                    if 'PS_Voltage_Setpoint' in header:
                        volt_col = 'PS_Voltage_Setpoint'
                    elif 'PS_Voltage' in header:
                        volt_col = 'PS_Voltage'
                if tc_col is None or volt_col is None or tc_col not in header or volt_col not in header:
                    raise ValueError(f"Required columns not found (tc={tc_col}, volt={volt_col})")
                tc_idx   = header.index(tc_col)
                volt_idx = header.index(volt_col)
                continue

            if header is None:
                continue

            # Data row
            try:
                ts   = datetime.fromisoformat(row[0]).timestamp()
                temp = float(row[tc_idx])   if row[tc_idx]   else None
                volt = float(row[volt_idx]) if row[volt_idx] else None
                timestamps.append(ts)
                temps.append(temp)
                volts.append(volt)
            except (ValueError, IndexError):
                continue

    return timestamps, temps, volts
