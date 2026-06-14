from datetime import datetime
from datetime import timedelta
import logging
import math
import os

from controllers.cooling_command_adapter import (
    DryRunCoolingCommandAdapter,
)
from controllers.two_stage_cooling_runner import (
    TwoStageCoolingRunner as CoolingDecisionRunner,
)
from models.two_stage_cooling import TemperatureSample
import settings


logger = logging.getLogger(__name__)

LEGACY_MODE = 'legacy'
TWO_STAGE_DRY_RUN_MODE = 'two_stage_dry_run'
TWO_STAGE_REAL_MODE = 'two_stage_real'
SUPPORTED_CONTROL_MODES = {
    LEGACY_MODE,
    TWO_STAGE_DRY_RUN_MODE,
    TWO_STAGE_REAL_MODE,
}


def normalize_control_mode(value):
    mode = str(value or LEGACY_MODE).strip().lower()
    if mode not in SUPPORTED_CONTROL_MODES:
        logger.warning({
            'action': 'aircon control mode',
            'status': 'invalid_mode',
            'message': 'invalid control mode; falling back to legacy',
            'control_mode': mode,
        })
        return LEGACY_MODE
    if mode == TWO_STAGE_REAL_MODE:
        logger.warning({
            'action': 'aircon control mode',
            'status': 'mode_not_connected',
            'message': 'two_stage_real is not connected; falling back to legacy',
            'control_mode': mode,
        })
        return LEGACY_MODE
    return mode


def resolve_control_mode(configured_mode=None, environ=None):
    environment = os.environ if environ is None else environ
    value = environment.get('AIRCON_CONTROL_MODE')
    if value is None:
        value = (
            getattr(settings, 'control_mode', LEGACY_MODE)
            if configured_mode is None
            else configured_mode
        )
    return normalize_control_mode(value)


class LegacyControlRunner:
    def __init__(self, ai):
        self.ai = ai

    def run_cycle(self):
        return self.ai.ctrl_temp()

    def stop(self):
        return self.ai.aircon.off()


class TemperatureDataUnavailable(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RecentTemperatureProvider:
    def __init__(
        self,
        hostname,
        device_num,
        window_minutes=5,
        freshness_minutes=5,
        minimum_samples=2,
        temp_humid_class=None,
    ):
        self.hostname = hostname
        self.device_num = device_num
        self.window_minutes = window_minutes
        self.freshness_minutes = freshness_minutes
        self.minimum_samples = minimum_samples
        self.temp_humid_class = temp_humid_class

    def get_samples(self, now):
        temp_humid_class = (
            self.temp_humid_class or self._temp_humid_class()
        )
        history_minutes = max(
            self.window_minutes,
            self.freshness_minutes * 2,
        )
        records = temp_humid_class.get_data_after_time(
            now - timedelta(minutes=history_minutes)
        )
        history = []
        for record in records or ():
            value = record.value
            temperature = value.get('temperature')
            sample_time = value.get('time')
            if temperature is None or sample_time is None:
                continue
            temperature = float(temperature)
            if not math.isfinite(temperature):
                continue
            if sample_time > now:
                continue
            history.append(TemperatureSample(
                time=sample_time,
                temperature=temperature,
            ))

        history.sort(key=lambda sample: sample.time)
        if not history:
            raise TemperatureDataUnavailable(
                'insufficient_temperature_data',
                'no valid temperature samples were found',
            )

        latest_at = history[-1].time
        if now - latest_at > timedelta(minutes=self.freshness_minutes):
            raise TemperatureDataUnavailable(
                'stale_temperature_data',
                'latest temperature data is older than freshness threshold',
            )

        window_start = now - timedelta(minutes=self.window_minutes)
        samples = [
            sample for sample in history
            if sample.time >= window_start
        ]
        if len(samples) < self.minimum_samples:
            raise TemperatureDataUnavailable(
                'insufficient_temperature_data',
                (
                    f'at least {self.minimum_samples} temperature samples '
                    'are required'
                ),
            )
        return tuple(samples), latest_at

    def _temp_humid_class(self):
        from models.base import factory_temp_humid_class

        temp_humid_class = factory_temp_humid_class(
            self.hostname,
            self.device_num,
        )
        if temp_humid_class is None:
            raise TemperatureDataUnavailable(
                'temperature_source_not_found',
                'temperature database model was not found',
            )
        return temp_humid_class


class TwoStageCoolingDryRunRunner:
    def __init__(
        self,
        temperature_provider,
        decision_runner=None,
        now_provider=None,
    ):
        self.temperature_provider = temperature_provider
        self.adapter = DryRunCoolingCommandAdapter()
        self.decision_runner = decision_runner or CoolingDecisionRunner(
            self.adapter
        )
        self.now_provider = now_provider or self._now

    @staticmethod
    def _now():
        return datetime.utcnow() + timedelta(hours=9)

    def run_cycle(self):
        now = self.now_provider()
        try:
            samples, latest_at = self.temperature_provider.get_samples(now)
        except TemperatureDataUnavailable as error:
            logger.warning({
                'action': 'two-stage dry-run',
                'status': error.status,
                'message': str(error),
                'control_mode': TWO_STAGE_DRY_RUN_MODE,
                'simulated': True,
            })
            return None
        except Exception:
            logger.exception({
                'action': 'two-stage dry-run',
                'status': 'temperature_read_failed',
                'message': 'temperature read failed; skipping decision',
                'control_mode': TWO_STAGE_DRY_RUN_MODE,
                'simulated': True,
            })
            return None

        previous_cooler_temp = (
            self.decision_runner.state.current_cooler_temp
        )
        result = self.decision_runner.run_cycle(samples, now)
        decision = result.decision
        state = result.state
        logger.info({
            'action': 'two-stage dry-run',
            'status': 'decision_simulated',
            'control_mode': TWO_STAGE_DRY_RUN_MODE,
            'control_state': state.control_state.value,
            'median_temperature': decision.median_temperature,
            'current_cooler_temp': previous_cooler_temp,
            'recommended_cooler_temp': (
                decision.recommended_cooler_temp
            ),
            'should_change': decision.should_change,
            'action_required': decision.action_required,
            'command': result.command.command_type.value,
            'reason': decision.reason,
            'confirm_count': decision.consecutive_count,
            'last_change_at': (
                state.last_change_at.isoformat()
                if state.last_change_at is not None
                else None
            ),
            'recovery_started_at': (
                state.recovery_started_at.isoformat()
                if state.recovery_started_at is not None
                else None
            ),
            'predicted_temperature': decision.predicted_temperature,
            'temperature_data_at': latest_at.isoformat(),
            'simulated': True,
        })
        return result

    def stop(self):
        logger.info({
            'action': 'two-stage dry-run',
            'status': 'stop_simulated',
            'message': 'dry-run stopped without sending an IR command',
            'control_mode': TWO_STAGE_DRY_RUN_MODE,
            'simulated': True,
        })


def create_control_runner(
    mode=None,
    ai=None,
    temperature_provider=None,
):
    selected_mode = resolve_control_mode(configured_mode=mode)
    if selected_mode == TWO_STAGE_DRY_RUN_MODE:
        provider = temperature_provider or RecentTemperatureProvider(
            hostname=settings.use_temperature_sensor_hostname,
            device_num=settings.use_temperature_sensor_device_num,
        )
        return TwoStageCoolingDryRunRunner(provider)

    if ai is None:
        from models.ai_aircon_ctrl import Ai

        ai = Ai()
    return LegacyControlRunner(ai)
