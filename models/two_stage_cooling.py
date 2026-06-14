from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from enum import Enum
import math
from statistics import median
from typing import Optional
from typing import Sequence


_UNSET = object()


class CoolingState(str, Enum):
    STOPPED = 'stopped'
    RECOVERY_COOLING = 'recovery_cooling'
    STABLE_COOLING = 'stable_cooling'


class StableDirection(str, Enum):
    COOL_MORE = 'cool_more'
    COOL_LESS = 'cool_less'


@dataclass(frozen=True)
class CoolingControlConfig:
    target_temp: float = 25.7
    deadband_low: float = 25.3
    deadband_high: float = 26.1
    recovery_start_margin: float = 1.3
    recovery_end_threshold: float = 26.2
    recovery_cooler_temp: float = 24.0
    stable_exit_cooler_temp: float = 26.0
    stable_confirm_cycles: int = 2
    min_change_interval_minutes: int = 15
    max_temp_change_per_action: float = 1.0
    median_window_minutes: int = 5
    recovery_max_minutes: int = 45

    def __post_init__(self):
        if self.deadband_low >= self.deadband_high:
            raise ValueError('deadband_low must be lower than deadband_high')
        if self.recovery_start_margin <= 0:
            raise ValueError('recovery_start_margin must be positive')
        if self.recovery_end_threshold >= self.recovery_start_threshold:
            raise ValueError(
                'recovery_end_threshold must be lower than '
                'recovery_start_threshold'
            )
        if self.stable_confirm_cycles < 1:
            raise ValueError('stable_confirm_cycles must be at least 1')
        if self.min_change_interval_minutes < 0:
            raise ValueError('min_change_interval_minutes cannot be negative')
        if self.max_temp_change_per_action <= 0:
            raise ValueError('max_temp_change_per_action must be positive')
        if self.median_window_minutes <= 0:
            raise ValueError('median_window_minutes must be positive')
        if self.recovery_max_minutes <= 0:
            raise ValueError('recovery_max_minutes must be positive')

    @property
    def recovery_start_threshold(self):
        return self.target_temp + self.recovery_start_margin


@dataclass(frozen=True)
class TemperatureSample:
    time: datetime
    temperature: float


@dataclass(frozen=True)
class CoolingControlInput:
    state: CoolingState
    temperatures: Sequence[TemperatureSample]
    current_cooler_temp: float
    now: datetime
    last_change_at: Optional[datetime] = None
    recovery_started_at: Optional[datetime] = None
    consecutive_direction: Optional[StableDirection] = None
    consecutive_count: int = 0
    predicted_temperature: Optional[float] = None
    force_recovery: bool = False


@dataclass(frozen=True)
class CoolingDecision:
    next_state: CoolingState
    should_change: bool
    recommended_cooler_temp: float
    reason: str
    median_temperature: float
    consecutive_direction: Optional[StableDirection]
    consecutive_count: int
    last_change_at: Optional[datetime]
    recovery_started_at: Optional[datetime]
    predicted_temperature: Optional[float]

    @property
    def log_data(self):
        return {
            'state': self.next_state.value,
            'median_temperature': self.median_temperature,
            'consecutive_direction': (
                self.consecutive_direction.value
                if self.consecutive_direction is not None
                else None
            ),
            'consecutive_count': self.consecutive_count,
            'last_change_at': (
                self.last_change_at.isoformat()
                if self.last_change_at is not None
                else None
            ),
            'recommended_cooler_temp': self.recommended_cooler_temp,
            'should_change': self.should_change,
            'reason': self.reason,
            'predicted_temperature': self.predicted_temperature,
        }


class TwoStageCoolingController:
    """Decide cooling actions without performing I/O or retaining state."""

    def __init__(self, config=None):
        self.config = config or CoolingControlConfig()

    def decide(self, control_input):
        median_temperature = self._median_temperature(
            control_input.temperatures,
            control_input.now,
        )

        if control_input.state == CoolingState.STOPPED:
            return self._decide_start(control_input, median_temperature)
        if control_input.state == CoolingState.RECOVERY_COOLING:
            return self._decide_recovery(control_input, median_temperature)
        if control_input.state == CoolingState.STABLE_COOLING:
            return self._decide_stable(control_input, median_temperature)
        raise ValueError(f'unsupported cooling state: {control_input.state}')

    def _median_temperature(self, temperatures, now):
        window_start = now - timedelta(
            minutes=self.config.median_window_minutes
        )
        values = [
            float(sample.temperature)
            for sample in temperatures
            if window_start <= sample.time <= now
            and math.isfinite(float(sample.temperature))
        ]
        if not values:
            raise ValueError('no valid temperature samples in median window')
        return float(median(values))

    def _decide_start(self, control_input, median_temperature):
        if (
            control_input.force_recovery
            or median_temperature >= self.config.recovery_start_threshold
        ):
            recommended = self.config.recovery_cooler_temp
            should_change = (
                recommended != control_input.current_cooler_temp
            )
            reason = (
                'recovery_forced'
                if control_input.force_recovery
                else 'recovery_started'
            )
            return self._decision(
                control_input=control_input,
                next_state=CoolingState.RECOVERY_COOLING,
                should_change=should_change,
                recommended_cooler_temp=recommended,
                reason=reason,
                median_temperature=median_temperature,
                last_change_at=(
                    control_input.now
                    if should_change
                    else control_input.last_change_at
                ),
                recovery_started_at=control_input.now,
            )

        return self._decision(
            control_input=control_input,
            next_state=CoolingState.STABLE_COOLING,
            should_change=False,
            recommended_cooler_temp=control_input.current_cooler_temp,
            reason='stable_started',
            median_temperature=median_temperature,
        )

    def _decide_recovery(self, control_input, median_temperature):
        recovery_started_at = (
            control_input.recovery_started_at or control_input.now
        )
        recovery_elapsed = control_input.now - recovery_started_at
        temperature_reached = (
            median_temperature <= self.config.recovery_end_threshold
        )
        time_limit_reached = recovery_elapsed >= timedelta(
            minutes=self.config.recovery_max_minutes
        )

        if temperature_reached or time_limit_reached:
            recommended = self.config.stable_exit_cooler_temp
            should_change = (
                recommended != control_input.current_cooler_temp
            )
            reason = (
                'recovery_temperature_reached'
                if temperature_reached
                else 'recovery_time_limit_reached'
            )
            return self._decision(
                control_input=control_input,
                next_state=CoolingState.STABLE_COOLING,
                should_change=should_change,
                recommended_cooler_temp=recommended,
                reason=reason,
                median_temperature=median_temperature,
                last_change_at=(
                    control_input.now
                    if should_change
                    else control_input.last_change_at
                ),
                recovery_started_at=None,
            )

        return self._decision(
            control_input=control_input,
            next_state=CoolingState.RECOVERY_COOLING,
            should_change=False,
            recommended_cooler_temp=self.config.recovery_cooler_temp,
            reason='recovery_holding',
            median_temperature=median_temperature,
            recovery_started_at=recovery_started_at,
        )

    def _decide_stable(self, control_input, median_temperature):
        direction = self._stable_direction(median_temperature)
        if direction is None:
            return self._decision(
                control_input=control_input,
                next_state=CoolingState.STABLE_COOLING,
                should_change=False,
                recommended_cooler_temp=control_input.current_cooler_temp,
                reason='within_deadband',
                median_temperature=median_temperature,
                consecutive_direction=None,
                consecutive_count=0,
            )

        if direction == control_input.consecutive_direction:
            consecutive_count = control_input.consecutive_count + 1
        else:
            consecutive_count = 1

        if consecutive_count < self.config.stable_confirm_cycles:
            return self._decision(
                control_input=control_input,
                next_state=CoolingState.STABLE_COOLING,
                should_change=False,
                recommended_cooler_temp=control_input.current_cooler_temp,
                reason='awaiting_confirmation',
                median_temperature=median_temperature,
                consecutive_direction=direction,
                consecutive_count=consecutive_count,
            )

        if not self._change_interval_elapsed(control_input):
            return self._decision(
                control_input=control_input,
                next_state=CoolingState.STABLE_COOLING,
                should_change=False,
                recommended_cooler_temp=control_input.current_cooler_temp,
                reason='minimum_change_interval',
                median_temperature=median_temperature,
                consecutive_direction=direction,
                consecutive_count=consecutive_count,
            )

        change = self.config.max_temp_change_per_action
        if direction == StableDirection.COOL_MORE:
            recommended = control_input.current_cooler_temp - change
            reason = 'above_deadband_confirmed'
        else:
            recommended = control_input.current_cooler_temp + change
            reason = 'below_deadband_confirmed'

        return self._decision(
            control_input=control_input,
            next_state=CoolingState.STABLE_COOLING,
            should_change=True,
            recommended_cooler_temp=recommended,
            reason=reason,
            median_temperature=median_temperature,
            consecutive_direction=None,
            consecutive_count=0,
            last_change_at=control_input.now,
        )

    def _stable_direction(self, median_temperature):
        if median_temperature > self.config.deadband_high:
            return StableDirection.COOL_MORE
        if median_temperature < self.config.deadband_low:
            return StableDirection.COOL_LESS
        return None

    def _change_interval_elapsed(self, control_input):
        if control_input.last_change_at is None:
            return True
        return (
            control_input.now - control_input.last_change_at
            >= timedelta(minutes=self.config.min_change_interval_minutes)
        )

    @staticmethod
    def _decision(
        control_input,
        next_state,
        should_change,
        recommended_cooler_temp,
        reason,
        median_temperature,
        consecutive_direction=None,
        consecutive_count=0,
        last_change_at=_UNSET,
        recovery_started_at=_UNSET,
    ):
        return CoolingDecision(
            next_state=next_state,
            should_change=should_change,
            recommended_cooler_temp=recommended_cooler_temp,
            reason=reason,
            median_temperature=median_temperature,
            consecutive_direction=consecutive_direction,
            consecutive_count=consecutive_count,
            last_change_at=(
                control_input.last_change_at
                if last_change_at is _UNSET
                else last_change_at
            ),
            recovery_started_at=(
                control_input.recovery_started_at
                if recovery_started_at is _UNSET
                else recovery_started_at
            ),
            predicted_temperature=control_input.predicted_temperature,
        )
