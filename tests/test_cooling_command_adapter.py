import unittest
from datetime import datetime

from controllers.cooling_command_adapter import CoolingCommand
from controllers.cooling_command_adapter import CoolingCommandType
from controllers.cooling_command_adapter import RealCoolingCommandAdapter


class FakeSender:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.cooler_calls = []
        self.off_calls = 0

    def cooler(self, temp, fan='auto'):
        self.cooler_calls.append({
            'temp': temp,
            'fan': fan,
        })
        if self.error is not None:
            raise self.error
        return self.result

    def off(self):
        self.off_calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class RealCoolingCommandAdapterTest(unittest.TestCase):
    def setUp(self):
        self.requested_at = datetime(2026, 6, 14, 18, 0, 0)
        self.executed_at = datetime(2026, 6, 14, 18, 0, 1)

    def _command(
        self,
        command_type,
        cooler_temp=26.0,
        target_fan='low',
    ):
        return CoolingCommand(
            command_type=command_type,
            cooler_temp=cooler_temp,
            requested_at=self.requested_at,
            reason='test',
            target_fan=target_fan,
            previous_fan='auto',
            control_state='stable_cooling',
        )

    def _adapter(self, sender):
        return RealCoolingCommandAdapter(
            sender,
            now_provider=lambda: self.executed_at,
        )

    def test_noop_does_not_call_sender_and_succeeds(self):
        sender = FakeSender()

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.NOOP,
            cooler_temp=None,
        ))

        self.assertTrue(result.success)
        self.assertFalse(result.simulated)
        self.assertEqual(sender.cooler_calls, [])
        self.assertEqual(sender.off_calls, 0)

    def test_ensure_cooling_sends_recommended_temperature(self):
        sender = FakeSender(result=True)

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.ENSURE_COOLING,
            cooler_temp=26.0,
        ))

        self.assertTrue(result.success)
        self.assertEqual(
            sender.cooler_calls,
            [{'temp': 26.0, 'fan': 'low'}],
        )

    def test_set_cooler_temp_sends_recommended_temperature(self):
        sender = FakeSender(result=True)

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.SET_COOLER_TEMP,
            cooler_temp=24.0,
        ))

        self.assertTrue(result.success)
        self.assertEqual(
            sender.cooler_calls,
            [{'temp': 24.0, 'fan': 'low'}],
        )

    def test_missing_fan_fails_without_calling_sender(self):
        sender = FakeSender(result=True)

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.SET_COOLER_TEMP,
            target_fan=None,
        ))

        self.assertFalse(result.success)
        self.assertEqual(sender.cooler_calls, [])
        self.assertIn('requires target_fan', result.error)

    def test_explicit_true_is_successful_real_result(self):
        command = self._command(CoolingCommandType.SET_COOLER_TEMP)

        result = self._adapter(FakeSender(result=True)).execute(command)

        self.assertTrue(result.success)
        self.assertFalse(result.simulated)
        self.assertEqual(result.command, command)
        self.assertEqual(result.executed_at, self.executed_at)
        self.assertIsNone(result.error)

    def test_false_sender_result_is_failure(self):
        result = self._adapter(FakeSender(result=False)).execute(
            self._command(CoolingCommandType.SET_COOLER_TEMP)
        )

        self.assertFalse(result.success)
        self.assertFalse(result.simulated)
        self.assertIn('unconfirmed sender result', result.error)

    def test_none_sender_result_is_failure(self):
        result = self._adapter(FakeSender(result=None)).execute(
            self._command(CoolingCommandType.SET_COOLER_TEMP)
        )

        self.assertFalse(result.success)
        self.assertFalse(result.simulated)
        self.assertIn('None', result.error)

    def test_sender_exception_is_failure(self):
        result = self._adapter(FakeSender(
            error=RuntimeError('send failed'),
        )).execute(
            self._command(CoolingCommandType.SET_COOLER_TEMP)
        )

        self.assertFalse(result.success)
        self.assertFalse(result.simulated)
        self.assertIn('RuntimeError: send failed', result.error)

    def test_turn_off_uses_sender_off(self):
        sender = FakeSender(result=True)

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.TURN_OFF,
            cooler_temp=None,
        ))

        self.assertTrue(result.success)
        self.assertEqual(sender.off_calls, 1)

    def test_missing_temperature_fails_without_calling_sender(self):
        sender = FakeSender(result=True)

        result = self._adapter(sender).execute(self._command(
            CoolingCommandType.SET_COOLER_TEMP,
            cooler_temp=None,
        ))

        self.assertFalse(result.success)
        self.assertEqual(sender.cooler_calls, [])
        self.assertIn('requires cooler_temp', result.error)

    def test_result_log_contains_debug_fields(self):
        adapter = self._adapter(FakeSender(result=True))

        with self.assertLogs(
            'controllers.cooling_command_adapter',
            level='INFO',
        ) as captured:
            adapter.execute(self._command(
                CoolingCommandType.SET_COOLER_TEMP,
                cooler_temp=24.0,
            ))

        log_data = captured.records[-1].msg
        self.assertEqual(log_data['command'], 'set_cooler_temp')
        self.assertEqual(log_data['target_temp'], 24.0)
        self.assertEqual(log_data['fan'], 'low')
        self.assertEqual(log_data['previous_fan'], 'auto')
        self.assertEqual(log_data['target_fan'], 'low')
        self.assertEqual(log_data['control_state'], 'stable_cooling')
        self.assertEqual(log_data['reason'], 'test')
        self.assertTrue(log_data['success'])
        self.assertIsNone(log_data['error'])
        self.assertEqual(
            log_data['executed_at'],
            self.executed_at.isoformat(),
        )


if __name__ == '__main__':
    unittest.main()
