import unittest
from datetime import datetime
from datetime import timedelta
from unittest import mock

from controllers.aircon_control_runner import AirconCoolingCommandSender
from controllers.aircon_control_runner import AirconStateRecorder
from controllers.aircon_control_runner import create_control_runner
from controllers.aircon_control_runner import LEGACY_MODE
from controllers.aircon_control_runner import LegacyControlRunner
from controllers.aircon_control_runner import RecentTemperatureProvider
from controllers.aircon_control_runner import resolve_control_mode
from controllers.aircon_control_runner import TemperatureDataUnavailable
from controllers.aircon_control_runner import TWO_STAGE_DRY_RUN_MODE
from controllers.aircon_control_runner import TWO_STAGE_REAL_MODE
from controllers.aircon_control_runner import TwoStageCoolingDryRunRunner
from controllers.aircon_control_runner import TwoStageCoolingRealRunner
from controllers.cooling_command_adapter import (
    DryRunCoolingCommandAdapter,
)
from controllers.cooling_command_adapter import RealCoolingCommandAdapter
from controllers.two_stage_cooling_runner import (
    TwoStageCoolingRuntimeState,
)
from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import StableDirection


class DummyAircon:
    def __init__(self):
        self.off_calls = 0
        self.cooler_calls = []
        self.error = None

    def cooler(self, temp, fan='auto'):
        self.cooler_calls.append({
            'temp': temp,
            'fan': fan,
        })
        if self.error is not None:
            raise self.error

    def off(self):
        self.off_calls += 1
        if self.error is not None:
            raise self.error


class DummyAi:
    def __init__(self):
        self.aircon = DummyAircon()
        self.ctrl_calls = 0

    def ctrl_temp(self):
        self.ctrl_calls += 1


class FakeRecord:
    def __init__(self, time, temperature):
        self.value = {
            'time': time,
            'temperature': temperature,
        }


class FakeTemperatureTable:
    records = ()

    @classmethod
    def get_data_after_time(cls, _time):
        return cls.records


class FailingTemperatureProvider:
    def get_samples(self, _now):
        raise RuntimeError('simulated read failure')


class UnavailableTemperatureProvider:
    def get_samples(self, _now):
        raise TemperatureDataUnavailable(
            'insufficient_temperature_data',
            'not enough data',
        )


class RecordingDecisionRunner:
    def __init__(self):
        self.calls = 0

    def run_cycle(self, _samples, _now):
        self.calls += 1
        raise AssertionError('decision runner must not be called')


class FakeCommandSender:
    def __init__(self, result=True):
        self.result = result
        self.cooler_calls = []
        self.off_calls = 0

    def cooler(self, temp, fan='auto'):
        self.cooler_calls.append({
            'temp': temp,
            'fan': fan,
        })
        return self.result

    def off(self):
        self.off_calls += 1
        return self.result


class FakeStateRecorder:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def record_cooling(self, time, cooler_temp):
        self.calls.append({
            'time': time,
            'cooler_temp': cooler_temp,
        })
        if self.error is not None:
            raise self.error
        return self.result


class AirconControlModeTest(unittest.TestCase):
    def test_default_mode_is_legacy(self):
        self.assertEqual(
            resolve_control_mode(configured_mode=None, environ={}),
            LEGACY_MODE,
        )

    def test_environment_overrides_configured_mode(self):
        self.assertEqual(
            resolve_control_mode(
                configured_mode=LEGACY_MODE,
                environ={
                    'AIRCON_CONTROL_MODE': TWO_STAGE_DRY_RUN_MODE,
                },
            ),
            TWO_STAGE_DRY_RUN_MODE,
        )

    def test_invalid_mode_falls_back_to_legacy(self):
        self.assertEqual(
            resolve_control_mode(
                configured_mode='invalid',
                environ={},
            ),
            LEGACY_MODE,
        )

    def test_real_mode_is_allowed(self):
        self.assertEqual(
            resolve_control_mode(
                configured_mode='two_stage_real',
                environ={},
            ),
            TWO_STAGE_REAL_MODE,
        )


class AirconControlRunnerFactoryTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 14, 18, 0, 0)

    def _provider(self, *temperatures):
        FakeTemperatureTable.records = tuple(
            FakeRecord(
                self.now - timedelta(minutes=index),
                temperature,
            )
            for index, temperature in enumerate(reversed(temperatures))
        )
        return RecentTemperatureProvider(
            hostname='test',
            device_num=0,
            temp_humid_class=FakeTemperatureTable,
        )

    def test_factory_returns_one_legacy_runner(self):
        ai = DummyAi()
        recorder = FakeStateRecorder()
        with mock.patch.dict(
            'os.environ',
            {'AIRCON_CONTROL_MODE': LEGACY_MODE},
            clear=False,
        ):
            runner = create_control_runner(
                ai=ai,
                state_recorder=recorder,
            )

        self.assertIsInstance(runner, LegacyControlRunner)
        self.assertIs(runner.ai, ai)
        runner.run_cycle()
        self.assertEqual(recorder.calls, [])

    def test_legacy_runner_calls_existing_ai_and_stop(self):
        ai = DummyAi()
        runner = LegacyControlRunner(ai)

        runner.run_cycle()
        runner.stop()

        self.assertEqual(ai.ctrl_calls, 1)
        self.assertEqual(ai.aircon.off_calls, 1)

    def test_factory_returns_dry_run_runner_without_using_legacy_ai(self):
        ai = DummyAi()
        with mock.patch.dict(
            'os.environ',
            {'AIRCON_CONTROL_MODE': TWO_STAGE_DRY_RUN_MODE},
            clear=False,
        ):
            runner = create_control_runner(
                ai=ai,
                temperature_provider=self._provider(25.6, 25.8),
            )

        self.assertIsInstance(runner, TwoStageCoolingDryRunRunner)
        self.assertIsInstance(
            runner.adapter,
            DryRunCoolingCommandAdapter,
        )
        runner.now_provider = lambda: self.now
        result = runner.run_cycle()
        runner.stop()

        self.assertIsNotNone(result)
        self.assertTrue(result.command_result.simulated)
        self.assertEqual(ai.ctrl_calls, 0)
        self.assertEqual(ai.aircon.off_calls, 0)

    def test_factory_returns_real_runner_without_using_legacy_ai(self):
        ai = DummyAi()
        sender = FakeCommandSender(result=True)
        recorder = FakeStateRecorder()
        with mock.patch.dict(
            'os.environ',
            {'AIRCON_CONTROL_MODE': TWO_STAGE_REAL_MODE},
            clear=False,
        ):
            runner = create_control_runner(
                ai=ai,
                temperature_provider=self._provider(27.5, 28.0),
                command_sender=sender,
                state_recorder=recorder,
            )

        self.assertIsInstance(runner, TwoStageCoolingRealRunner)
        self.assertIsInstance(
            runner.adapter,
            RealCoolingCommandAdapter,
        )
        runner.now_provider = lambda: self.now
        result = runner.run_cycle()

        self.assertTrue(result.command_result.success)
        self.assertFalse(result.command_result.simulated)
        self.assertEqual(ai.ctrl_calls, 0)
        self.assertEqual(
            sender.cooler_calls,
            [{'temp': 24.0, 'fan': 'auto'}],
        )
        self.assertEqual(
            recorder.calls,
            [{'time': self.now, 'cooler_temp': 24.0}],
        )

    def test_real_runner_commits_state_only_after_sender_success(self):
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )

        result = runner.run_cycle()

        self.assertTrue(result.committed)
        self.assertEqual(
            runner.decision_runner.state.control_state,
            CoolingState.RECOVERY_COOLING,
        )
        self.assertEqual(
            runner.decision_runner.state.current_cooler_temp,
            24.0,
        )

    def test_real_runner_keeps_state_after_sender_failure(self):
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=False),
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )
        initial_state = runner.decision_runner.state

        result = runner.run_cycle()

        self.assertFalse(result.committed)
        self.assertEqual(runner.decision_runner.state, initial_state)

    def test_real_runner_logs_required_fields(self):
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )

        with self.assertLogs(
            'controllers.aircon_control_runner',
            level='INFO',
        ) as captured:
            runner.run_cycle()

        log_data = captured.records[-1].msg
        required_fields = {
            'control_mode',
            'control_state',
            'median_temperature',
            'current_cooler_temp',
            'recommended_cooler_temp',
            'should_change',
            'action_required',
            'command',
            'reason',
            'success',
            'simulated',
            'temperature_data_at',
            'fan',
            'previous_fan',
            'current_fan',
            'target_fan',
        }
        self.assertTrue(required_fields.issubset(log_data))
        self.assertEqual(log_data['control_mode'], TWO_STAGE_REAL_MODE)
        self.assertTrue(log_data['success'])
        self.assertFalse(log_data['simulated'])
        self.assertEqual(log_data['target_fan'], 'auto')
        self.assertEqual(log_data['current_fan'], 'auto')

    def test_real_runner_records_ensure_cooling_after_success(self):
        recorder = FakeStateRecorder()
        runner = TwoStageCoolingRealRunner(
            self._provider(25.6, 25.8),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )

        result = runner.run_cycle()

        self.assertEqual(
            result.command.command_type.value,
            'ensure_cooling',
        )
        self.assertEqual(result.command.target_fan, 'low')
        self.assertEqual(
            runner.decision_runner.state.current_fan,
            'low',
        )
        self.assertEqual(
            runner.sender.cooler_calls,
            [{'temp': 26.0, 'fan': 'low'}],
        )
        self.assertEqual(
            recorder.calls,
            [{'time': self.now, 'cooler_temp': 26.0}],
        )

    def test_real_runner_records_changed_temperature_after_success(self):
        recorder = FakeStateRecorder()
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )

        result = runner.run_cycle()

        self.assertEqual(
            result.command.command_type.value,
            'set_cooler_temp',
        )
        self.assertEqual(
            recorder.calls,
            [{'time': self.now, 'cooler_temp': 24.0}],
        )

    def test_real_runner_sends_low_for_stable_temperature_change(self):
        sender = FakeCommandSender(result=True)
        runner = TwoStageCoolingRealRunner(
            self._provider(26.3, 26.5),
            sender,
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )
        runner.decision_runner.state = TwoStageCoolingRuntimeState(
            control_state=CoolingState.STABLE_COOLING,
            current_cooler_temp=27.0,
            current_fan='low',
            consecutive_direction=StableDirection.COOL_MORE,
            consecutive_count=1,
        )

        result = runner.run_cycle()

        self.assertEqual(result.command.command_type.value, 'set_cooler_temp')
        self.assertEqual(result.command.target_fan, 'low')
        self.assertEqual(
            sender.cooler_calls,
            [{'temp': 26.0, 'fan': 'low'}],
        )

    def test_real_runner_keeps_auto_fan_after_low_switch_failure(self):
        sender = FakeCommandSender(result=False)
        runner = TwoStageCoolingRealRunner(
            self._provider(25.6, 25.8),
            sender,
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )
        initial_state = TwoStageCoolingRuntimeState(
            control_state=CoolingState.STABLE_COOLING,
            current_cooler_temp=26.0,
            current_fan='auto',
        )
        runner.decision_runner.state = initial_state

        result = runner.run_cycle()

        self.assertFalse(result.committed)
        self.assertEqual(result.command.command_type.value, 'ensure_cooling')
        self.assertEqual(result.command.target_fan, 'low')
        self.assertEqual(
            sender.cooler_calls,
            [{'temp': 26.0, 'fan': 'low'}],
        )
        self.assertEqual(runner.decision_runner.state, initial_state)
        self.assertEqual(runner.decision_runner.state.current_fan, 'auto')

    def test_real_runner_records_current_temperature_after_noop(self):
        recorder = FakeStateRecorder()
        runner = TwoStageCoolingRealRunner(
            self._provider(25.6, 25.8),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )
        runner.run_cycle()
        recorder.calls.clear()
        next_time = self.now + timedelta(minutes=3)
        runner.now_provider = lambda: next_time
        runner.temperature_provider = self._provider(25.6, 25.8)

        result = runner.run_cycle()

        self.assertEqual(result.command.command_type.value, 'noop')
        self.assertEqual(
            runner.sender.cooler_calls,
            [{'temp': 26.0, 'fan': 'low'}],
        )
        self.assertEqual(
            recorder.calls,
            [{'time': next_time, 'cooler_temp': 26.0}],
        )

    def test_real_runner_does_not_record_after_adapter_failure(self):
        recorder = FakeStateRecorder()
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=False),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )

        result = runner.run_cycle()

        self.assertFalse(result.command_result.success)
        self.assertEqual(recorder.calls, [])

    def test_real_runner_continues_after_recording_exception(self):
        recorder = FakeStateRecorder(
            error=RuntimeError('database failed')
        )
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )

        result = runner.run_cycle()

        self.assertTrue(result.committed)
        self.assertEqual(
            runner.decision_runner.state.current_cooler_temp,
            24.0,
        )

    def test_real_runner_continues_when_recording_returns_false(self):
        recorder = FakeStateRecorder(result=False)
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            FakeCommandSender(result=True),
            now_provider=lambda: self.now,
            state_recorder=recorder,
        )

        result = runner.run_cycle()

        self.assertTrue(result.committed)
        self.assertEqual(
            runner.decision_runner.state.current_cooler_temp,
            24.0,
        )
        self.assertEqual(len(recorder.calls), 1)

    def test_aircon_state_recorder_uses_existing_schema(self):
        recorder = AirconStateRecorder()

        with mock.patch('models.base.AirconState.create') as create:
            create.return_value = object()
            self.assertTrue(recorder.record_cooling(
                time=self.now,
                cooler_temp=24.0,
            ))

        create.assert_called_once_with(
            time=self.now,
            mode='cooler',
            setting_temp=24.0,
            heater_setting_temp=None,
            cooler_setting_temp=24.0,
        )

    def test_real_runner_stop_uses_sender_off(self):
        sender = FakeCommandSender(result=True)
        runner = TwoStageCoolingRealRunner(
            self._provider(27.5, 28.0),
            sender,
            now_provider=lambda: self.now,
            state_recorder=FakeStateRecorder(),
        )

        self.assertTrue(runner.stop())
        self.assertEqual(sender.off_calls, 1)

    def test_aircon_sender_wrapper_returns_true_after_completion(self):
        aircon = DummyAircon()
        sender = AirconCoolingCommandSender(aircon=aircon)

        self.assertTrue(sender.cooler(temp=24.0, fan='auto'))
        self.assertTrue(sender.off())
        self.assertEqual(
            aircon.cooler_calls,
            [{'temp': 24.0, 'fan': 'auto'}],
        )
        self.assertEqual(aircon.off_calls, 1)

    def test_aircon_sender_wrapper_propagates_exception(self):
        aircon = DummyAircon()
        aircon.error = RuntimeError('IR failed')
        sender = AirconCoolingCommandSender(aircon=aircon)

        with self.assertRaisesRegex(RuntimeError, 'IR failed'):
            sender.cooler(temp=24.0, fan='auto')

    def test_dry_run_does_not_record_aircon_state(self):
        runner = TwoStageCoolingDryRunRunner(
            self._provider(25.6, 25.8),
            now_provider=lambda: self.now,
        )

        with mock.patch('models.base.AirconState.create') as create:
            runner.run_cycle()

        create.assert_not_called()

    def test_dry_run_logs_required_decision_fields(self):
        runner = TwoStageCoolingDryRunRunner(
            self._provider(25.6, 25.8),
            now_provider=lambda: self.now,
        )

        with self.assertLogs(
            'controllers.aircon_control_runner',
            level='INFO',
        ) as captured:
            runner.run_cycle()

        log_data = captured.records[-1].msg
        required_fields = {
            'control_mode',
            'control_state',
            'median_temperature',
            'current_cooler_temp',
            'recommended_cooler_temp',
            'should_change',
            'action_required',
            'command',
            'reason',
            'confirm_count',
            'last_change_at',
            'recovery_started_at',
            'predicted_temperature',
            'temperature_data_at',
            'simulated',
            'fan',
            'previous_fan',
            'current_fan',
            'target_fan',
        }
        self.assertTrue(required_fields.issubset(log_data))
        self.assertTrue(log_data['simulated'])
        self.assertEqual(log_data['target_fan'], 'low')
        self.assertEqual(log_data['current_fan'], 'low')

    def test_temperature_read_failure_skips_decision(self):
        decision_runner = RecordingDecisionRunner()
        runner = TwoStageCoolingDryRunRunner(
            FailingTemperatureProvider(),
            decision_runner=decision_runner,
            now_provider=lambda: self.now,
        )

        self.assertIsNone(runner.run_cycle())
        self.assertEqual(decision_runner.calls, 0)

    def test_unavailable_temperature_skips_decision(self):
        decision_runner = RecordingDecisionRunner()
        runner = TwoStageCoolingDryRunRunner(
            UnavailableTemperatureProvider(),
            decision_runner=decision_runner,
            now_provider=lambda: self.now,
        )

        self.assertIsNone(runner.run_cycle())
        self.assertEqual(decision_runner.calls, 0)

    def test_provider_rejects_insufficient_data(self):
        provider = self._provider(25.7)

        with self.assertRaises(TemperatureDataUnavailable) as context:
            provider.get_samples(self.now)

        self.assertEqual(
            context.exception.status,
            'insufficient_temperature_data',
        )

    def test_provider_rejects_stale_data(self):
        FakeTemperatureTable.records = (
            FakeRecord(self.now - timedelta(minutes=7), 25.7),
            FakeRecord(self.now - timedelta(minutes=6), 25.8),
        )
        provider = RecentTemperatureProvider(
            hostname='test',
            device_num=0,
            temp_humid_class=FakeTemperatureTable,
        )

        with self.assertRaises(TemperatureDataUnavailable) as context:
            provider.get_samples(self.now)

        self.assertEqual(
            context.exception.status,
            'stale_temperature_data',
        )


if __name__ == '__main__':
    unittest.main()
