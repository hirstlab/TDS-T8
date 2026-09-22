"""
program_executor.py
PURPOSE: Unified execution engine for block-based programs.
Supports Voltage Ramp, Stable Hold, and Temperature Ramp blocks.

WHY THIS EXISTS / TRANSITIONAL NOTE
------------------------------------
Previously, ProgramExecutor read the control TC independently via
DataAcquisition.get_tc_kelvin_by_name() -> ThermocoupleReader.read_single(),
which caused temperature readings to diverge from the GUI and CSV logging.
In ticket rig-architecture-05, its temperature source becomes the latest Snapshot
published by the Rig (converted to K at this module's conversion point).
Its voltage writes still go through the power-supply object it holds today
as a transitional step until ticket 10, when ProgramExecutor is replaced by
ProgramRun and pure block steps (ADRs 0002, 0003).
"""

import threading
import time
import datetime
import math
import random
from .temp_ramp_pid import PIDController, PIDRunLogger
from .feedforward_map import FeedforwardMap  # FF-5

class ProgramExecutor:
    def __init__(self, power_supply=None, get_temp_k_fn_provider=None,
                 on_block_start=None, on_block_complete=None,
                 on_program_complete=None, on_status=None,
                 practice_mode=False, rig=None):
        self._ps = power_supply
        self._rig = rig
        if get_temp_k_fn_provider is not None:
            self._get_temp_k_provider = get_temp_k_fn_provider
            self._using_default_snapshot_provider = False
        elif rig is not None:
            self._get_temp_k_provider = lambda tc_name: lambda: self._get_temp_k_from_snapshot(tc_name)
            self._using_default_snapshot_provider = True
        else:
            self._get_temp_k_provider = lambda tc_name: (lambda: 293.15)
            self._using_default_snapshot_provider = True

        self._on_block_start = on_block_start
        self._on_block_complete = on_block_complete
        self._on_program_complete = on_program_complete
        self._on_status = on_status
        self.practice_mode = practice_mode

        self._current_get_temp_k = None

        self._blocks = []
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self._pid = PIDController()
        self._pid_logger = PIDRunLogger()

        # FF-7 START — rate-indexed feedforward map
        self._ff_map = FeedforwardMap()
        self._ff_map.load()
        self._block_rate_k_per_min = 0.0   # rate of the currently executing block
        # FF-7 END

        # Shared state between blocks
        self.current_voltage_setpoint = 0.0
        self.current_current_limit = 180.0  # amps — full rated current for tungsten
        self.current_block_index = 0
        
        # Diagnostics
        self._practice_temp_k = 293.15
        self._practice_last_tick = None
        self._last_tick_time = None

        # Run history for post-run analysis
        self._run_log = []   # [(elapsed, setpoint_k, actual_k, voltage_v), ...]
        self._last_run_record = None

        # FF-3 START — scheduler state exposed for CSV logging (read by on_new_data)
        self._sched_kp = 0.0
        self._sched_ki = 0.0
        self._sched_kd = 0.0
        self._sched_zone = 0
        self._ff_voltage = 0.0
        self._pid_correction = 0.0
        # FF-3 END

        # QMS confirmation gate
        self._confirmation_event = threading.Event()
        self._waiting_for_confirmation = False
        self.on_waiting_for_confirmation = None   # callback(block_index)

    def set_rig(self, rig):
        with self._lock:
            self._rig = rig
            if getattr(self, '_using_default_snapshot_provider', True):
                self._using_default_snapshot_provider = True
                self._get_temp_k_provider = lambda tc_name: lambda: self._get_temp_k_from_snapshot(tc_name)

    def _get_temp_k_from_snapshot(self, tc_name: str) -> float | None:
        if self._rig is None:
            return 293.15
        snap = self._rig.latest() if hasattr(self._rig, "latest") else self._rig()
        if snap is None or not hasattr(snap, "tc_c"):
            return 293.15
        val_c = snap.tc_c.get(tc_name)
        if val_c is None:
            return None
        return val_c + 273.15

    def set_power_supply(self, ps):
        with self._lock:
            self._ps = ps

    def load_program(self, blocks):
        with self._lock:
            self._blocks = list(blocks)
            self.current_block_index = 0

    def start(self):
        with self._lock:
            if self._running:
                return False
            self._running = True
            self.current_block_index = 0
            self._pid.reset()
            self._last_tick_time = time.time()
            
            self._practice_last_tick = None
            self._practice_temp_k = 293.15
            if self.practice_mode:
                try:
                    fn = self._get_temp_k_provider("TC_1")
                    temp = fn() if fn else None
                    if temp:
                        self._practice_temp_k = temp
                except Exception:
                    pass
                # Turn on mock PS output so get_voltage/get_current return non-zero
                if self._ps is not None:
                    try:
                        self._ps.output_on()
                        max_amps = getattr(self._ps, 'current_limit',
                                           getattr(self._ps, 'rated_max_amps', 180.0))
                        self._ps.set_current(max_amps)
                    except Exception:
                        pass
            else:
                # Enable output and set current ceiling before starting.
                # DAC1 starts at 0V (= 0A) at power-on; must set current_limit
                # explicitly or the supply cannot source any current.
                if self._ps is not None:
                    try:
                        self._ps.output_on()
                        max_amps = getattr(self._ps, 'current_limit',
                                           getattr(self._ps, 'rated_max_amps', 180.0))
                        self._ps.set_current(max_amps)
                        print(f"[ProgramExecutor] output_on + set_current({max_amps}A)")
                        print(f"[ProgramExecutor] practice_mode={self.practice_mode}")
                        print(f"[ProgramExecutor] ps is None: {self._ps is None}")
                    except Exception as e:
                        print(f"[ProgramExecutor] Warning: output_on/set_current failed: {e}")

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return True

    def confirm_and_continue(self):
        """Release the QMS confirmation hold and continue to the next block."""
        self._confirmation_event.set()

    def stop(self):
        self._running = False
        self._confirmation_event.set()  # Release any waiting confirmation
        if self._thread:
            self._thread.join(timeout=2.0)
        
        # Safety: zero the output
        if self._ps:
            try:
                self._ps.set_voltage(0.0)
                self._ps.set_current(0.0)
            except Exception as e:
                print(f"[ProgramExecutor] Warning: zeroing output failed: {e}")

    def is_running(self):
        return self._running and self._thread and self._thread.is_alive()

    def compute_preview(self, blocks, start_temp_k=293.15, start_voltage=0.0):
        """
        Compute the expected voltage and temperature profile for the given blocks.
        Returns: (times, voltages, temps_k, block_boundaries)
        """
        times = [0.0]
        voltages = [start_voltage]
        temps_k = [start_temp_k]
        boundaries = [0.0]
        
        current_time = 0.0
        current_v = start_voltage
        current_t = start_temp_k
        
        for block in blocks:
            if block.block_type == "voltage_ramp":
                dur = block.duration_sec
                # Corrected loop
                steps = max(1, int(dur))
                v_start = block.start_voltage
                v_end = block.end_voltage
                for i in range(1, steps + 1):
                    t = current_time + i
                    p = i / steps
                    v = v_start + (v_end - v_start) * p
                    times.append(t)
                    voltages.append(v)
                    temps_k.append(current_t) # Assume temp stays same for voltage ramp preview
                current_time += steps
                current_v = v_end
                
            elif block.block_type == "stable_hold":
                # Preview: assume it reaches target temp and stays
                # In reality it takes time, but for preview we show target
                dur = block.hold_duration_sec
                steps = max(1, int(dur))
                for i in range(1, steps + 1):
                    times.append(current_time + i)
                    voltages.append(current_v) # Assume voltage stays same? Or show it at target?
                    temps_k.append(block.target_temp_k)
                current_time += steps
                current_t = block.target_temp_k
                
            elif block.block_type == "temp_ramp":
                rate_k_per_sec = abs(block.rate_k_per_min / 60.0)
                if rate_k_per_sec > 0:
                    dur = abs(block.end_temp_k - current_t) / rate_k_per_sec
                else:
                    dur = 0
                
                steps = max(1, int(dur))
                t_start = current_t
                t_end = block.end_temp_k
                for i in range(1, steps + 1):
                    t = current_time + i
                    p = i / steps
                    temp = t_start + (t_end - t_start) * p
                    times.append(t)
                    voltages.append(current_v) # Assume voltage stays same for preview
                    temps_k.append(temp)
                current_time += steps
                current_t = t_end
            
            boundaries.append(current_time)
            
        return times, voltages, temps_k, boundaries

    def _run_loop(self):
        # Initial temp from TC_1 or similar
        self._current_get_temp_k = self._get_temp_k_provider("TC_1")
        block_start_temp_k = self._current_get_temp_k() if self._current_get_temp_k else 293.15
        # NOTE: unused — possible bug, see workflow-setup ticket 02
        del block_start_temp_k
        
        # Seed the shared voltage setpoint from the live supply output if the
        # supply is already energised, so that starting a continuation program
        # does not snap back to 0 V. The first block's bumpless PID transfer
        # builds on this value. (Previously this was computed into a local that
        # was never used, so continuation runs still snapped to 0 V.)
        if self._ps:
            try:
                _measured_v = self._ps.get_voltage()
                if _measured_v and _measured_v > 0.1:
                    self.current_voltage_setpoint = _measured_v
            except Exception:
                pass

        # Use the first temp_ramp block's TC name for the initial reading so
        # the PID starts from the real measured temperature, not the 293.15 K default.
        first_tc = "TC_1"
        for b in self._blocks:
            if hasattr(b, 'tc_name'):
                first_tc = b.tc_name
                break
        self._current_get_temp_k = self._get_temp_k_provider(first_tc)
        live_start_k = self._current_get_temp_k() if self._current_get_temp_k else 293.15
        print(f"[ProgramExecutor] _run_loop started, {len(self._blocks)} block(s), practice={self.practice_mode}, ps={self._ps}, start_temp={live_start_k:.1f}K ({live_start_k-273.15:.1f}°C)")
        try:
            while self._running and self.current_block_index < len(self._blocks):
                block = self._blocks[self.current_block_index]
                print(f"[ProgramExecutor] Starting block {self.current_block_index}: {block.block_type}")

                # Update TC channel if this is a temp ramp block
                if block.block_type == "temp_ramp":
                    self._current_get_temp_k = self._get_temp_k_provider(block.tc_name)

                # FF-7 START — per-block feedforward/gain resolution
                self._resolve_block_control(block)
                # FF-7 END

                if self._on_block_start:
                    self._on_block_start(self.current_block_index, block)

                success = self._execute_block(block)

                if not success:
                    print(f"[ProgramExecutor] Block {self.current_block_index} returned failure/stopped")
                    break

                if self._on_block_complete:
                    self._on_block_complete(self.current_block_index)

                # QMS confirmation pause: if this StableHold has qms_trigger=True
                # and the next block is a TempRamp, wait for user confirmation.
                next_idx = self.current_block_index + 1
                if (getattr(block, 'qms_trigger', False) and
                        next_idx < len(self._blocks) and
                        self._blocks[next_idx].block_type == "temp_ramp"):
                    self._waiting_for_confirmation = True
                    self._confirmation_event.clear()
                    print(f"[ProgramExecutor] Waiting for QMS confirmation before block {next_idx}")
                    if self.on_waiting_for_confirmation:
                        self.on_waiting_for_confirmation(self.current_block_index)
                    while self._running and not self._confirmation_event.is_set():
                        self._confirmation_event.wait(timeout=0.5)
                    self._waiting_for_confirmation = False
                    print("[ProgramExecutor] QMS confirmation received, continuing")

                self.current_block_index += 1

        except Exception as exc:
            import traceback
            print(f"[ProgramExecutor] EXCEPTION in run loop: {exc}")
            traceback.print_exc()

        self._running = False
        print("[ProgramExecutor] _run_loop finished")
        if self._on_program_complete:
            self._on_program_complete()

    def _execute_block(self, block):
        start_time = time.time()
        start_temp_k = self._current_get_temp_k() if self._current_get_temp_k else 293.15

        # Bumpless PID re-init between blocks.
        # A hard self._pid.reset() here zeros the integrator, and because
        # PIDController.compute() returns 0.0 on its first call, the DAC was
        # driven to 0 V for one or more ticks at EVERY block boundary. To the
        # operator the power supply visibly switched off and back on between
        # blocks, wrecking the PID and sending the temperature out of control.
        #
        # Instead, re-seed the controller so its first output equals the
        # voltage we are already commanding: the output stays continuous
        # across the boundary while stale derivative/timing history is still
        # cleared. This also preserves the original intent of not letting a
        # wound-up integral fight a following cooldown — the integral is set
        # to exactly hold the current output, then unwinds naturally once the
        # error flips sign on the way down. Reset only for closed-loop blocks;
        # voltage_ramp is open-loop and drives the DAC directly.
        if block.block_type in ("temp_ramp", "stable_hold"):
            self._pid.reset_bumpless(self.current_voltage_setpoint, start_time)

        # For StableHold stability tracking
        stability_start = None

        # For TempRamp run history
        if block.block_type == "temp_ramp":
            self._run_log = []
            _overshoot_k = 0.0

        while self._running:
            now = time.time()
            dt = now - self._last_tick_time if self._last_tick_time else 0.1
            # NOTE: unused — possible bug, see workflow-setup ticket 02
            del dt
            self._last_tick_time = now

            elapsed = now - start_time
            current_temp_k = self._current_get_temp_k() if self._current_get_temp_k else 293.15
            print(f"[PE-TICK] block={self.current_block_index}, type={block.block_type}, elapsed={elapsed:.1f}s, temp={current_temp_k:.1f}K, practice={self.practice_mode}, ps={self._ps is not None}")

            if block.block_type == "voltage_ramp":
                # Linear voltage interpolation
                if block.duration_sec > 0:
                    progress = min(1.0, elapsed / block.duration_sec)
                else:
                    progress = 1.0
                
                v_out = block.start_voltage + (block.end_voltage - block.start_voltage) * progress
                self.current_voltage_setpoint = v_out
                
                # PID monitoring if requested
                if block.pid_active:
                    # Just run it to update internal state/diagnostics
                    # but we don't use the output
                    self._pid.compute(current_temp_k, current_temp_k, now)
                
                if progress >= 1.0:
                    return True

            elif block.block_type == "stable_hold":
                # PID control to target_temp_k
                setpoint_k = block.target_temp_k
                ff_v = 0.0
                pid_correction = self._pid.compute(setpoint_k, current_temp_k, now)
                v_out = max(0.0, min(ff_v + pid_correction, 6.0))
                self.current_voltage_setpoint = v_out
                # FF-3 START — update scheduler state
                self._ff_voltage = ff_v
                self._pid_correction = pid_correction
                self._sched_kp = self._pid._kp
                self._sched_ki = self._pid._ki
                self._sched_kd = self._pid._kd
                self._sched_zone = 0
                # FF-3 END

                # Stability check
                if abs(current_temp_k - setpoint_k) <= block.tolerance_k:
                    if stability_start is None:
                        stability_start = now
                    elif now - stability_start >= block.hold_duration_sec:
                        return True
                else:
                    stability_start = None

            elif block.block_type == "temp_ramp":
                # PID control with plain ramping setpoint at the requested rate.
                current_temp_c = current_temp_k - 273.15
                rate_k_per_sec = block.rate_k_per_min / 60.0
                setpoint_k = start_temp_k + rate_k_per_sec * elapsed

                # Cap at end_temp_k and detect completion
                is_finished = False
                if rate_k_per_sec > 0:
                    setpoint_k = min(setpoint_k, block.end_temp_k)
                    if setpoint_k >= block.end_temp_k:
                        is_finished = True
                else:
                    setpoint_k = max(setpoint_k, block.end_temp_k)
                    if setpoint_k <= block.end_temp_k:
                        is_finished = True

                # FIX-2 START — Suppress is_finished during the warmup window
                # If the TC cache hasn't populated yet, start_temp_k falls back
                # to 293.15 K. For a cooldown block with end_temp_k also near
                # 293 K, is_finished would fire on tick 1 and the block would
                # exit immediately. A 2 s guard lets the TC buffer populate
                # without affecting real completions (ramps last minutes).
                MIN_RAMP_ELAPSED_SEC = 2.0
                if elapsed < MIN_RAMP_ELAPSED_SEC:
                    is_finished = False
                # FIX-2 END

                # FF-7 START — feedforward voltage from steady-state backbone
                ff_v = self._ff_map.voltage_for(self._block_rate_k_per_min, current_temp_c)
                # FF-7 END
                pid_correction = self._pid.compute(setpoint_k, current_temp_k, now)
                v_out = max(0.0, min(ff_v + pid_correction, 6.0))
                # FF-3 START — update scheduler state
                self._ff_voltage = ff_v
                self._pid_correction = pid_correction
                self._sched_kp = self._pid._kp
                self._sched_ki = self._pid._ki
                self._sched_kd = self._pid._kd
                self._sched_zone = 0
                # FF-3 END

                if self.practice_mode:
                    # Override with a demo voltage that rises realistically with
                    # the setpoint fraction so plots look like a working PID.
                    # Real PID with feedforward: V ≈ proportional to temp fraction
                    # plus a small boost when lagging (error > 0), plus noise.
                    _temp_range = max(block.end_temp_k - start_temp_k, 1.0)
                    _sp_fraction = max(0.0, (setpoint_k - start_temp_k) / _temp_range)
                    _error_k = setpoint_k - current_temp_k
                    _demo_v = _sp_fraction * 5.5 + _error_k * 0.008
                    _demo_v += random.uniform(-0.03, 0.03)
                    # Exponential smoothing: blend toward target (alpha=0.25 → smooth ramp)
                    _prev_v = self.current_voltage_setpoint
                    v_out = max(0.0, min(0.25 * _demo_v + 0.75 * _prev_v, 6.0))

                # Cold-tungsten current protection: if current exceeds 180A,
                # hold voltage steady (don't increase) until current drops.
                # Tungsten resistance is ~17x lower cold than at operating temp;
                # without this guard the PID could command voltage that draws
                # excessive current before the Keysight's CC mode kicks in.
                # Compare v_out to the PREVIOUS tick's setpoint (before reassignment).
                cold_start_limit = 180.0  # amps
                if not self.practice_mode and self._ps is not None:
                    try:
                        measured_current = self._ps.get_current() or 0.0
                        if measured_current > cold_start_limit and v_out > self.current_voltage_setpoint:
                            v_out = self.current_voltage_setpoint  # hold, don't increase
                    except Exception:
                        pass

                self.current_voltage_setpoint = v_out

                # Track run log and overshoot for history
                self._run_log.append((elapsed, setpoint_k, current_temp_k, self.current_voltage_setpoint))
                _overshoot_k = max(_overshoot_k, current_temp_k - setpoint_k)

                if is_finished:
                    achieved_rate = ((current_temp_k - start_temp_k) / (elapsed / 60.0)
                                     if elapsed > 0 else 0.0)
                    self._save_run_to_history(block.rate_k_per_min, achieved_rate,
                                              _overshoot_k, elapsed)
                    return True

            # Practice-mode thermal simulation: drive _practice_temp_k toward
            # the current setpoint with a first-order lag (tau=20s).
            if self.practice_mode and block.block_type == "temp_ramp":
                _now_sim = time.time()
                if self._practice_last_tick is not None:
                    _dt_sim = _now_sim - self._practice_last_tick
                    _tau = 20.0  # thermal time constant in seconds
                    self._practice_temp_k += (setpoint_k - self._practice_temp_k) * (
                        1.0 - math.exp(-_dt_sim / _tau)
                    )
                    self._practice_temp_k += random.uniform(-0.5, 0.5)
                self._practice_last_tick = _now_sim

            # Apply to hardware
            print(f"[PE-APP] v_setpoint={self.current_voltage_setpoint:.4f}V, practice={self.practice_mode}, ps_present={self._ps is not None}")
            if self._ps:
                try:
                    if not self.practice_mode:
                        # Guard against interlock (Task 3c)
                        if hasattr(self._ps, 'interlock_active') and self._ps.interlock_active:
                            print("[ProgramExecutor] Interlock active - skipping DAC write")
                        else:
                            print(f"[PE-WRITE] set_voltage({self.current_voltage_setpoint:.4f}V) on ps={self._ps}")
                            result = self._ps.set_voltage(self.current_voltage_setpoint)
                            print(f"[PE-WRITE] set_voltage result={result}")
                    else:
                        # In practice mode: update mock PS so plots show simulated voltage
                        # and current rising proportionally (tungsten R ~ 0.033 Ω → I = V/R)
                        self._ps.set_voltage(self.current_voltage_setpoint)
                        _sim_current = self.current_voltage_setpoint * 30.0  # ~180A at 6V
                        max_amps = getattr(self._ps, 'current_limit',
                                           getattr(self._ps, 'rated_max_amps', 180.0))
                        self._ps.set_current(min(_sim_current, max_amps))
                except Exception as e:
                    print(f"[ProgramExecutor] DAC write error: {e}")

            if self._on_status:
                pid_terms = self._pid.get_debug_terms()
                self._on_status({
                    'block_index': self.current_block_index,
                    'block_type': block.block_type,
                    'elapsed_sec': elapsed,
                    'current_temp_k': current_temp_k,
                    'voltage_v': self.current_voltage_setpoint,
                    'ff_voltage': self.current_voltage_setpoint - pid_terms['p_term'] - pid_terms['i_term'] - pid_terms['d_term'],
                    'pid_p': pid_terms['p_term'],
                    'pid_i': pid_terms['i_term'],
                    'pid_d': pid_terms['d_term'],
                })

            # Sleep to match TICK_INTERVAL (approx 0.5s or 1.0s)
            time.sleep(0.5)

        return False

    def _save_run_to_history(self, target_rate, achieved_rate, overshoot_k, elapsed_span):
        """Compute settling/oscillation metrics, save the run record, and store it."""
        # Compute settling time: first time error stays within ±2K continuously for 10+ ticks
        SETTLE_BAND_K = 2.0
        SETTLE_MIN_TICKS = 10
        settling_time_sec = None
        consecutive = 0
        for entry in self._run_log:
            t, sp, actual, _ = entry
            if abs(actual - sp) <= SETTLE_BAND_K:
                consecutive += 1
                if consecutive >= SETTLE_MIN_TICKS and settling_time_sec is None:
                    settling_time_sec = t
            else:
                consecutive = 0

        # Compute oscillation count: zero crossings of (actual - setpoint)
        errors = [e[2] - e[1] for e in self._run_log]
        oscillation_count = sum(
            1 for i in range(1, len(errors))
            if errors[i - 1] * errors[i] < 0
        )

        record = {
            'timestamp':                    datetime.datetime.now().isoformat(),
            'target_rate_k_per_min':        target_rate,
            'achieved_mean_rate_k_per_min': achieved_rate,
            'overshoot_k':                  overshoot_k,
            'settling_time_sec':            settling_time_sec,
            'oscillation_count':            oscillation_count,
            'duration_sec':                 elapsed_span,
            'kp_used':                      self._pid._kp,
            'ki_used':                      self._pid._ki,
            'kd_used':                      self._pid._kd,
        }
        self._last_run_record = record
        self._pid_logger.save_run(record)

        # FF-8 START — append completed run data to feedforward map
        try:
            self._ff_map.append_run(self._run_log, target_rate)
        except Exception as _ff_exc:
            print(f"[ProgramExecutor] FF map append_run error: {_ff_exc}")
        # FF-8 END

    def get_pid_logger(self) -> 'PIDRunLogger':
        """Return the PIDRunLogger so the GUI can display the run history."""
        return self._pid_logger

    def validate_program(self, blocks) -> list:
        """
        Check blocks for power-envelope violations.

        Returns a list of warning strings; empty means no issues found.
        """
        return list(self._ff_map.validate_program(blocks))

    # FF-7 START — per-block feedforward/gain resolver
    def _resolve_block_control(self, block):
        """
        Called once at each block transition before _execute_block.

        Stores the block rate so the tick loop can query FeedforwardMap.voltage_for.
        Gain updates (suggest_gains per-block) are a Phase 3 extension; for now
        the gains set by main_window before start() carry through unchanged.
        """
        if block.block_type == "temp_ramp":
            self._block_rate_k_per_min = getattr(block, 'rate_k_per_min', 0.0)
        else:
            self._block_rate_k_per_min = 0.0
    # FF-7 END

    # FF-3 START — scheduler state getter for CSV logging
    def get_sched_state(self) -> dict:
        """Return a snapshot of the current scheduler state for CSV logging.

        Thread-safe for simple attribute reads under the Python GIL.
        Returns None-valued dict when no block is active.
        """
        return {
            'Sched_Kp':       self._sched_kp,
            'Sched_Ki':       self._sched_ki,
            'Sched_Kd':       self._sched_kd,
            'Sched_Zone':     self._sched_zone,
            'FF_Voltage':     self._ff_voltage,
            'PID_Correction': self._pid_correction,
        }
    # FF-3 END
