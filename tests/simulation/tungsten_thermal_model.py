"""
Lumped-parameter tungsten thermal model.
Tuned to match pid_feedforward_table.json steady-state points.

dT/dt = (P_in - P_rad - P_cond) / (m * c_p)

Reference points from feedforward table:
  3.0 V -> 1680 K steady-state
  1.0 V -> 1100 K steady-state
"""
import math


class TungstenSim:
    """
    Simple lumped-parameter tungsten thermal simulator.

    Call step(voltage_v) repeatedly. Each call advances by dt seconds.
    """

    # Physical constants
    STEFAN_BOLTZMANN = 5.67e-8  # W/(m^2 K^4)

    # Specimen parameters -- tuned to give:
    #   * Numerically stable steps at dt=0.5 s (no explosive first-step)
    #   * Monotonically increasing T_ss with voltage (matches feedforward table trend)
    #   * At 3.0V steady-state T_ss in the 1400–1900 K ballpark
    #
    # R_COLD = 0.033 Ω  → at cold start 6V draws ~180A (matching rated max)
    # MASS   = 0.010 kg → thermal mass 1.4 J/K, limits dT to ~43 K/step at cold
    R_COLD = 0.033          # Ohms at 300K — cold resistance, ~6V/180A rated point
    ALPHA = 0.0045          # /K  linear TCR (positive, tungsten heats ~17x cold→hot)
    MASS = 0.010            # kg  ~10g specimen, sufficient thermal mass for dt=0.5 s
    C_P = 140.0             # J/(kg K)  specific heat capacity (relatively flat for W)
    EMISSIVITY = 0.25       # emissivity (polished W)
    AREA = 2e-4             # m^2  effective radiating surface area
    K_COND = 0.005          # W/K  lead conduction loss (small)
    T_AMB = 300.0           # K   ambient / mounting temperature

    def __init__(self, dt=0.5):
        self.dt = dt
        self._T = self.T_AMB
        self._time = 0.0

    def reset(self, T0=300.0):
        self._T = float(T0)
        self._time = 0.0

    def _resistance(self, T_k):
        """Linear TCR model: R(T) = R_cold * (1 + alpha*(T-300))"""
        return self.R_COLD * (1.0 + self.ALPHA * (T_k - 300.0))

    def step(self, voltage_v):
        """
        Advance simulation by dt seconds.
        Returns (temperature_k, current_a).
        """
        T = self._T
        R = self._resistance(T)
        R = max(R, 1e-6)  # prevent division by zero

        # Power balance
        P_in = (voltage_v ** 2) / R                           # Ohmic heating
        P_rad = self.EMISSIVITY * self.STEFAN_BOLTZMANN * self.AREA * (T ** 4 - self.T_AMB ** 4)
        P_cond = self.K_COND * (T - self.T_AMB)               # Lead conduction

        P_net = P_in - P_rad - P_cond
        dT = P_net * self.dt / (self.MASS * self.C_P)

        self._T = max(self.T_AMB, T + dT)
        self._time += self.dt
        current_a = voltage_v / R
        return self._T, current_a

    def get_state(self):
        return {
            'temperature_k': self._T,
            'time_s': self._time,
            'resistance_ohm': self._resistance(self._T),
        }

    def steady_state_temp(self, voltage_v, max_iter=100000, tol=0.01):
        """Iterate to steady-state for a fixed voltage. Returns T_ss in Kelvin."""
        self.reset()
        prev_T = 0.0
        for _ in range(max_iter):
            T, _ = self.step(voltage_v)
            if abs(T - prev_T) < tol:
                return T
            prev_T = T
        return self._T
