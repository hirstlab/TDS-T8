"""
program_executor.py
PURPOSE: Unified execution engine for block-based programs.
Supports Voltage Ramp, Stable Hold, and Temperature Ramp blocks.
"""

import threading
import time
import datetime
from .temp_ramp_pid import PIDController, TempRampHistory, FeedforwardTable

class ProgramExecutor:
    def __init__(self, power_supply, get_temp_k_fn_provider, history=None,
                 on_block_start=None, on_block_complete=None,
                 on_program_complete=None, on_status=None,
                 practice_mode=False):
        self._ps = power_supply
        self._get_temp_k_provider = get_temp_k_fn_provider # Returns a function for a given TC name
        self._history = history or TempRampHistory()
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
        self._feedforward = FeedforwardTable()

        # Shared state between blocks
        self.current_voltage_setpoint = 0.0
        self.current_current_limit = 180.0  # amps — full rated current for tungsten
        self.current_block_index = 0
        
        # Diagnostics
        self._practice_temp_k = 293.15
        self._last_tick_time = None

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
            
            if self.practice_mode:
                try:
                    fn = self._get_temp_k_provider("TC_1")
                    temp = fn() if fn else None
                    if temp:
                        self._practice_temp_k = temp
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
                    except Exception as e:
                        print(f"[ProgramExecutor] Warning: output_on/set_current failed: {e}")

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        
        # Safety: zero the output
        if self._ps:
            try:
                self._ps.set_voltage(0.0)
                self._ps.set_current(0.0)
            except:
                pass

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
        
        # For inter-block continuity
        last_voltage = 0.0
        if self._ps:
            try:
                # Try to get current state if possible, else 0
                last_voltage = 0.0 
            except:
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

                if self._on_block_start:
                    self._on_block_start(self.current_block_index, block)

                success = self._execute_block(block)

                if not success:
                    print(f"[ProgramExecutor] Block {self.current_block_index} returned failure/stopped")
                    break

                if self._on_block_complete:
                    self._on_block_complete(self.current_block_index)

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
        
        # For StableHold stability tracking
        stability_start = None

        while self._running:
            now = time.time()
            dt = now - self._last_tick_time if self._last_tick_time else 0.1
            self._last_tick_time = now
            
            elapsed = now - start_time
            current_temp_k = self._current_get_temp_k() if self._current_get_temp_k else 293.15

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
                # FF from target temp: gives steady-state voltage for the hold point
                ff_v = self._feedforward.lookup(setpoint_k - 273.15)
                pid_correction = self._pid.compute(setpoint_k, current_temp_k, now)
                v_out = max(0.0, min(ff_v + pid_correction, 6.0))
                self.current_voltage_setpoint = v_out
                
                # Stability check
                if abs(current_temp_k - setpoint_k) <= block.tolerance_k:
                    if stability_start is None:
                        stability_start = now
                    elif now - stability_start >= block.hold_duration_sec:
                        return True
                else:
                    stability_start = None

            elif block.block_type == "temp_ramp":
                # PID control with ramping setpoint
                rate_k_per_sec = block.rate_k_per_min / 60.0
                setpoint_k = start_temp_k + rate_k_per_sec * elapsed
                
                # Cap setpoint at end_temp_k
                is_finished = False
                if rate_k_per_sec > 0:
                    if setpoint_k >= block.end_temp_k:
                        setpoint_k = block.end_temp_k
                        is_finished = True
                else:
                    if setpoint_k <= block.end_temp_k:
                        setpoint_k = block.end_temp_k
                        is_finished = True
                
                # FF from the ramping setpoint temp: grows as setpoint advances
                ff_v = self._feedforward.lookup(setpoint_k - 273.15)
                pid_correction = self._pid.compute(setpoint_k, current_temp_k, now)
                v_out = max(0.0, min(ff_v + pid_correction, 6.0))
                self.current_voltage_setpoint = v_out

                if is_finished:
                    return True

            # Apply to hardware
            if not self.practice_mode and self._ps:
                try:
                    # Guard against interlock (Task 3c)
                    if hasattr(self._ps, 'interlock_active') and self._ps.interlock_active:
                        print("[ProgramExecutor] Interlock active - skipping DAC write")
                    else:
                        self._ps.set_voltage(self.current_voltage_setpoint)
                        # Maintain the software current limit (don't re-set every tick
                        # to avoid hammering the DAC; only set if it changed)
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
