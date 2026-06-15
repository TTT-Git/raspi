from datetime import datetime
from datetime import timedelta
import logging
import math
import os

from controllers.cooling_command_adapter import (
    DryRunCoolingCommandAdapter,
)
from controllers.cooling_command_adapter import RealCoolingCommandAdapter
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


class AirconCoolingCommandSender:
    """Adapt the existing Aircon API to an explicit success contract."""

    def __init__(self, aircon=None):
        if aircon is None:
            from pigpios.ir_ctrl import Aircon

            aircon = Aircon(
                remote_raspi=settings.remote_ir,
                ssh_num=settings.remote_ir_raspi_ssh_num,
            )
        self.aircon = aircon

    def cooler(self, temp, fan='auto'):
        self.aircon.cooler(temp=temp, fan=fan)
        return True

    def off(self):
        self.aircon.off()
        return True


class AirconStateRecorder:
    """Persist confirmed two-stage cooling state for the existing Web UI."""

    def record_cooling(self, time, cooler_temp):
        from models.base import AirconState

        return bool(AirconState.create(
            time=time,
            mode='cooler',
            setting_temp=cooler_temp,
            heater_setting_temp=None,
            cooler_setting_temp=cooler_temp,
        ))


class TwoStageCoolingControlRunner:
    def __init__(
        self,
        temperature_provider,
        adapter,
        control_mode,
        decision_runner=None,
        now_provider=None,
    ):
        self.temperature_provider = temperature_provider
        self.adapter = adapter
        self.control_mode = control_mode
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
                'action': 'two-stage cooling',
                'status': error.status,
                'message': str(error),
                'control_mode': self.control_mode,
                'simulated': self._simulated,
            })
            return None
        except Exception:
            logger.exception({
                'action': 'two-stage cooling',
                'status': 'temperature_read_failed',
                'message': 'temperature read failed; skipping decision',
                'control_mode': self.control_mode,
                'simulated': self._simulated,
            })
            return None

        previous_cooler_temp = (
            self.decision_runner.state.current_cooler_temp
        )
        previous_fan = self.decision_runner.state.current_fan
        result = self.decision_runner.run_cycle(samples, now)
        self._after_run_cycle(now, result)
        decision = result.decision
        state = result.state
        logger.info({
            'action': 'two-stage cooling',
            'status': (
                'decision_applied'
                if result.command_result.success
                else 'decision_not_applied'
            ),
            'control_mode': self.control_mode,
            'control_state': state.control_state.value,
            'median_temperature': decision.median_temperature,
            'current_cooler_temp': previous_cooler_temp,
            'recommended_cooler_temp': (
                decision.recommended_cooler_temp
            ),
            'should_change': decision.should_change,
            'action_required': (
                result.command.command_type.value != 'noop'
            ),
            'command': result.command.command_type.value,
            'reason': decision.reason,
            'fan': result.command.target_fan,
            'previous_fan': previous_fan,
            'current_fan': state.current_fan,
            'target_fan': result.command.target_fan,
            'success': result.command_result.success,
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
            'simulated': result.command_result.simulated,
        })
        return result

    def _after_run_cycle(self, now, result):
        del now
        del result

    @property
    def _simulated(self):
        return self.control_mode == TWO_STAGE_DRY_RUN_MODE


class TwoStageCoolingDryRunRunner(TwoStageCoolingControlRunner):
    def __init__(
        self,
        temperature_provider,
        decision_runner=None,
        now_provider=None,
    ):
        super().__init__(
            temperature_provider=temperature_provider,
            adapter=DryRunCoolingCommandAdapter(),
            control_mode=TWO_STAGE_DRY_RUN_MODE,
            decision_runner=decision_runner,
            now_provider=now_provider,
        )

    def stop(self):
        logger.info({
            'action': 'two-stage dry-run',
            'status': 'stop_simulated',
            'message': 'dry-run stopped without sending an IR command',
            'control_mode': TWO_STAGE_DRY_RUN_MODE,
            'simulated': True,
        })


class TwoStageCoolingRealRunner(TwoStageCoolingControlRunner):
    def __init__(
        self,
        temperature_provider,
        sender,
        decision_runner=None,
        now_provider=None,
        state_recorder=None,
    ):
        self.sender = sender
        self.state_recorder = state_recorder or AirconStateRecorder()
        super().__init__(
            temperature_provider=temperature_provider,
            adapter=RealCoolingCommandAdapter(sender),
            control_mode=TWO_STAGE_REAL_MODE,
            decision_runner=decision_runner,
            now_provider=now_provider,
        )

    def _after_run_cycle(self, now, result):
        if not result.command_result.success:
            return

        cooler_temp = result.state.current_cooler_temp
        try:
            recorded = self.state_recorder.record_cooling(
                time=now,
                cooler_temp=cooler_temp,
            )
        except Exception:
            logger.exception({
                'action': 'two-stage aircon_state write',
                'status': 'write_skipped',
                'message': (
                    'failed to record confirmed cooling state; '
                    'control will continue'
                ),
                'control_mode': TWO_STAGE_REAL_MODE,
                'command': result.command.command_type.value,
                'cooler_temp': cooler_temp,
            })
            return

        if not recorded:
            logger.warning({
                'action': 'two-stage aircon_state write',
                'status': 'write_skipped',
                'message': (
                    'confirmed cooling state was not recorded; '
                    'control will continue'
                ),
                'control_mode': TWO_STAGE_REAL_MODE,
                'command': result.command.command_type.value,
                'cooler_temp': cooler_temp,
            })

    def stop(self):
        return self.sender.off()


def create_control_runner(
    mode=None,
    ai=None,
    temperature_provider=None,
    command_sender=None,
    state_recorder=None,
):
    selected_mode = resolve_control_mode(configured_mode=mode)
    if selected_mode in (
        TWO_STAGE_DRY_RUN_MODE,
        TWO_STAGE_REAL_MODE,
    ):
        provider = temperature_provider or RecentTemperatureProvider(
            hostname=settings.use_temperature_sensor_hostname,
            device_num=settings.use_temperature_sensor_device_num,
        )
        if selected_mode == TWO_STAGE_REAL_MODE:
            sender = command_sender or AirconCoolingCommandSender()
            return TwoStageCoolingRealRunner(
                provider,
                sender,
                state_recorder=state_recorder,
            )
        return TwoStageCoolingDryRunRunner(provider)

    if ai is None:
        from models.ai_aircon_ctrl import Ai

        ai = Ai()
    return LegacyControlRunner(ai)
