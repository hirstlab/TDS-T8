"""
Ramp Profile Data Structure for Power Supply Control.

Defines heating/cooling profiles as a series of steps that can be loaded,
saved, validated, and interpolated to get setpoints at any time.
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum


class StepType(Enum):
    """Types of steps in a ramp profile."""
    RAMP = "ramp"
    HOLD = "hold"


@dataclass
class RampStep:
    """
    A single step in a ramp profile.

    Attributes:
        step_type: Either 'ramp' (change voltage) or 'hold' (maintain voltage)
        duration_sec: How long this step takes in seconds
        target_voltage: For ramp steps, the voltage to reach by end of step
                       For hold steps, this is ignored (uses previous voltage)
    """
    step_type: str
    duration_sec: float
    target_voltage: Optional[float] = None

    def __post_init__(self):
        """Validate step after initialization."""
        if self.step_type not in [StepType.RAMP.value, StepType.HOLD.value]:
            raise ValueError(f"Invalid step type: {self.step_type}. "
                           f"Must be 'ramp' or 'hold'")
        if self.duration_sec <= 0:
            raise ValueError(f"Duration must be positive: {self.duration_sec}")
        if self.step_type == StepType.RAMP.value and self.target_voltage is None:
            raise ValueError("Ramp steps must have a target_voltage")
        if self.target_voltage is not None and self.target_voltage < 0:
            raise ValueError(f"Target voltage cannot be negative: {self.target_voltage}")

    def to_dict(self) -> dict:
        """Convert step to dictionary for JSON serialization."""
        result = {
            "type": self.step_type,
            "duration_sec": self.duration_sec
        }
        if self.target_voltage is not None:
            result["target_voltage"] = self.target_voltage
        return result

    @classmethod
    def from_dict(cls, data: dict) -> 'RampStep':
        """Create a RampStep from a dictionary."""
        return cls(
            step_type=data.get("type", "hold"),
            duration_sec=data.get("duration_sec", 0),
            target_voltage=data.get("target_voltage")
        )


class RampProfile:
    """
    A complete ramp profile consisting of multiple steps.

    The profile defines a sequence of voltage changes and holds over time.
    It can be loaded from JSON, saved to JSON, validated, and queried for
    the setpoint at any elapsed time.

    Example profile structure:
        [
            {"type": "ramp", "target_voltage": 5.0, "duration_sec": 60},
            {"type": "hold", "duration_sec": 120},
            {"type": "ramp", "target_voltage": 10.0, "duration_sec": 120},
            {"type": "hold", "duration_sec": 300},
            {"type": "ramp", "target_voltage": 0.0, "duration_sec": 60},
        ]
    """

    def __init__(self, name: str = "Untitled Profile",
                 description: str = "",
                 start_voltage: float = 0.0,
                 current_limit: float = 50.0):
        """
        Initialize an empty ramp profile.

        Args:
            name: Human-readable name for the profile
            description: Optional description of the profile purpose
            start_voltage: Initial voltage before first step (default 0V)
            current_limit: Current limit to apply during profile (Amps)
        """
        self.name = name
        self.description = description
        self.start_voltage = start_voltage
        self.current_limit = current_limit
        self.steps: List[RampStep] = []
        self._filepath: Optional[str] = None

    def add_step(self, step: RampStep) -> None:
        """
        Add a step to the profile.

        Args:
            step: RampStep to add to the end of the profile
        """
        self.steps.append(step)

    def add_ramp(self, target_voltage: float, duration_sec: float) -> None:
        """
        Convenience method to add a ramp step.

        Args:
            target_voltage: Voltage to reach by end of ramp
            duration_sec: Duration of the ramp in seconds
        """
        self.steps.append(RampStep(
            step_type=StepType.RAMP.value,
            duration_sec=duration_sec,
            target_voltage=target_voltage
        ))

    def add_hold(self, duration_sec: float) -> None:
        """
        Convenience method to add a hold step.

        Args:
            duration_sec: Duration to hold at current voltage
        """
        self.steps.append(RampStep(
            step_type=StepType.HOLD.value,
            duration_sec=duration_sec
        ))

    def clear(self) -> None:
        """Remove all steps from the profile."""
        self.steps.clear()

    def get_total_duration(self) -> float:
        """
        Get total duration of the profile in seconds.

        Returns:
            Total duration in seconds
        """
        return sum(step.duration_sec for step in self.steps)

    def get_step_count(self) -> int:
        """
        Get the number of steps in the profile.

        Returns:
            Number of steps
        """
        return len(self.steps)

    def get_step_at_time(self, elapsed_sec: float) -> tuple:
        """
        Get which step is active at a given elapsed time.

        Args:
            elapsed_sec: Elapsed time since profile start in seconds

        Returns:
            Tuple of (step_index, step, time_into_step) or (None, None, 0)
            if profile is complete
        """
        if elapsed_sec < 0:
            elapsed_sec = 0

        cumulative_time = 0.0
        for i, step in enumerate(self.steps):
            if cumulative_time + step.duration_sec > elapsed_sec:
                time_into_step = elapsed_sec - cumulative_time
                return (i, step, time_into_step)
            cumulative_time += step.duration_sec

        # Profile complete
        return (None, None, 0.0)

    def get_setpoint_at_time(self, elapsed_sec: float) -> float:
        """
        Calculate the voltage setpoint at a given elapsed time.

        For ramp steps, linearly interpolates between start and target voltage.
        For hold steps, maintains the voltage from the previous step.

        Args:
            elapsed_sec: Elapsed time since profile start in seconds

        Returns:
            Voltage setpoint in Volts
        """
        if elapsed_sec <= 0:
            return self.start_voltage

        if not self.steps:
            return self.start_voltage

        # Find current voltage at the START of each step
        # by tracking what voltage we reach at each step
        cumulative_time = 0.0
        current_voltage = self.start_voltage

        for step in self.steps:
            step_start_time = cumulative_time
            step_end_time = cumulative_time + step.duration_sec

            if elapsed_sec <= step_end_time:
                # We're in this step
                time_into_step = elapsed_sec - step_start_time
                progress = time_into_step / step.duration_sec if step.duration_sec > 0 else 1.0

                if step.step_type == StepType.RAMP.value:
                    # Linear interpolation from current_voltage to target
                    return current_voltage + (step.target_voltage - current_voltage) * progress
                else:
                    # Hold step - maintain current voltage
                    return current_voltage

            # Move to next step - update current_voltage to what it is at step end
            if step.step_type == StepType.RAMP.value:
                current_voltage = step.target_voltage
            # Hold steps don't change voltage

            cumulative_time = step_end_time

        # Past end of profile - return final voltage
        return current_voltage

    def get_final_voltage(self) -> float:
        """
        Get the voltage at the end of the profile.

        Returns:
            Final voltage in Volts
        """
        return self.get_setpoint_at_time(self.get_total_duration())

    def validate(self) -> tuple:
        """
        Validate the profile for errors.

        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []

        if not self.steps:
            errors.append("Profile has no steps")

        if self.start_voltage < 0:
            errors.append(f"Start voltage cannot be negative: {self.start_voltage}")

        if self.current_limit <= 0:
            errors.append(f"Current limit must be positive: {self.current_limit}")

        for i, step in enumerate(self.steps):
            try:
                # Re-validate each step
                if step.step_type not in [StepType.RAMP.value, StepType.HOLD.value]:
                    errors.append(f"Step {i+1}: Invalid step type '{step.step_type}'")
                if step.duration_sec <= 0:
                    errors.append(f"Step {i+1}: Duration must be positive")
                if step.step_type == StepType.RAMP.value:
                    if step.target_voltage is None:
                        errors.append(f"Step {i+1}: Ramp step missing target_voltage")
                    elif step.target_voltage < 0:
                        errors.append(f"Step {i+1}: Target voltage cannot be negative")
            except Exception as e:
                errors.append(f"Step {i+1}: {str(e)}")

        return (len(errors) == 0, errors)

    def to_dict(self) -> dict:
        """
        Convert profile to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the profile
        """
        return {
            "name": self.name,
            "description": self.description,
            "start_voltage": self.start_voltage,
            "current_limit": self.current_limit,
            "steps": [step.to_dict() for step in self.steps]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RampProfile':
        """
        Create a RampProfile from a dictionary.

        Args:
            data: Dictionary containing profile data

        Returns:
            New RampProfile instance
        """
        profile = cls(
            name=data.get("name", "Untitled Profile"),
            description=data.get("description", ""),
            start_voltage=data.get("start_voltage", 0.0),
            current_limit=data.get("current_limit", 50.0)
        )
        for step_data in data.get("steps", []):
            profile.add_step(RampStep.from_dict(step_data))
        return profile

    def save(self, filepath: str) -> bool:
        """
        Save profile to a JSON file.

        Args:
            filepath: Path to save the profile to

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            self._filepath = filepath
            return True
        except Exception as e:
            print(f"Error saving profile: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional['RampProfile']:
        """
        Load a profile from a JSON file.

        Args:
            filepath: Path to the JSON profile file

        Returns:
            RampProfile instance or None if loading fails
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            profile = cls.from_dict(data)
            profile._filepath = filepath
            return profile
        except FileNotFoundError:
            print(f"Profile file not found: {filepath}")
            return None
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in profile file: {e}")
            return None
        except Exception as e:
            print(f"Error loading profile: {e}")
            return None

    def __repr__(self) -> str:
        """String representation of the profile."""
        return (f"RampProfile(name='{self.name}', steps={len(self.steps)}, "
                f"duration={self.get_total_duration():.1f}s)")
