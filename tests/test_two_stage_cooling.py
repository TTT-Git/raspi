import unittest
from datetime import datetime
from datetime import timedelta

from models.two_stage_cooling import CoolingControlConfig
from models.two_stage_cooling import CoolingControlInput
from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import StableDirection
from models.two_stage_cooling import TemperatureSample
from models.two_stage_cooling import TwoStageCoolingController


class TwoStageCoolingControllerTest(unittest.TestCase):
    def setUp(self):
        self.controller = TwoStageCoolingController()
        self.now = datetime(2026, 6, 14, 18, 0, 0)

    def _samples(self, *temperatures, now=None):
        sample_now = now or self.now
        return [
            TemperatureSample(
                time=sample_now - timedelta(minutes=index),
                temperature=temperature,
            )
            for index, temperature in enumerate(reversed(temperatures))
        ]

    def _input(
        self,
        state,
        temperatures,
        current_cooler_temp=26.0,
        now=None,
        **kwargs,
    ):
        return CoolingControlInput(
            state=state,
            temperatures=temperatures,
            current_cooler_temp=current_cooler_temp,
            now=now or self.now,
            **kwargs,
        )

    def test_uses_only_five_minute_window_and_calculates_median(self):
        samples = [
            TemperatureSample(
                time=self.now - timedelta(minutes=6),
                temperature=40.0,
            ),
            *self._samples(25.0, 27.0, 26.0),
        ]

        decision = self.controller.decide(self._input(
            CoolingState.STOPPED,
            samples,
        ))

        self.assertEqual(decision.median_temperature, 26.0)
        self.assertEqual(decision.next_state, CoolingState.STABLE_COOLING)

    def test_start_enters_recovery_at_27_0_and_recommends_24(self):
        decision = self.controller.decide(self._input(
            CoolingState.STOPPED,
            self._samples(26.9, 27.0, 27.1),
            current_cooler_temp=26.0,
        ))

        self.assertEqual(decision.median_temperature, 27.0)
        self.assertEqual(decision.next_state, CoolingState.RECOVERY_COOLING)
        self.assertTrue(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 24.0)
        self.assertEqual(decision.reason, 'recovery_started')
        self.assertEqual(decision.recovery_started_at, self.now)

    def test_recovery_start_threshold_is_derived_from_target_and_margin(self):
        config = CoolingControlConfig(
            target_temp=24.0,
            recovery_start_margin=1.3,
            recovery_end_threshold=24.5,
        )

        self.assertAlmostEqual(config.recovery_start_threshold, 25.3)

    def test_start_at_26_9_enters_stable_cooling(self):
        decision = self.controller.decide(self._input(
            CoolingState.STOPPED,
            self._samples(26.8, 26.9, 27.0),
            current_cooler_temp=26.0,
        ))

        self.assertEqual(decision.median_temperature, 26.9)
        self.assertEqual(decision.next_state, CoolingState.STABLE_COOLING)
        self.assertFalse(decision.should_change)
        self.assertEqual(decision.reason, 'stable_started')

    def test_force_recovery_allows_future_manual_recovery_start(self):
        decision = self.controller.decide(self._input(
            CoolingState.STOPPED,
            self._samples(25.5, 25.7, 25.9),
            current_cooler_temp=26.0,
            force_recovery=True,
        ))

        self.assertEqual(decision.next_state, CoolingState.RECOVERY_COOLING)
        self.assertTrue(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 24.0)
        self.assertEqual(decision.reason, 'recovery_forced')

    def test_recovery_holds_24_without_periodic_changes(self):
        started_at = self.now - timedelta(minutes=20)
        decision = self.controller.decide(self._input(
            CoolingState.RECOVERY_COOLING,
            self._samples(26.8, 26.9, 27.0),
            current_cooler_temp=24.0,
            recovery_started_at=started_at,
        ))

        self.assertEqual(decision.next_state, CoolingState.RECOVERY_COOLING)
        self.assertFalse(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 24.0)
        self.assertEqual(decision.reason, 'recovery_holding')

    def test_recovery_exits_when_median_reaches_26_2(self):
        decision = self.controller.decide(self._input(
            CoolingState.RECOVERY_COOLING,
            self._samples(26.1, 26.2, 26.3),
            current_cooler_temp=24.0,
            recovery_started_at=self.now - timedelta(minutes=20),
        ))

        self.assertEqual(decision.median_temperature, 26.2)
        self.assertEqual(decision.next_state, CoolingState.STABLE_COOLING)
        self.assertTrue(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 26.0)
        self.assertEqual(decision.reason, 'recovery_temperature_reached')

    def test_recovery_exits_at_45_minute_limit(self):
        decision = self.controller.decide(self._input(
            CoolingState.RECOVERY_COOLING,
            self._samples(27.0, 27.1, 27.2),
            current_cooler_temp=24.0,
            recovery_started_at=self.now - timedelta(minutes=45),
        ))

        self.assertEqual(decision.next_state, CoolingState.STABLE_COOLING)
        self.assertTrue(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 26.0)
        self.assertEqual(decision.reason, 'recovery_time_limit_reached')

    def test_high_temperature_requires_two_consecutive_cycles(self):
        first = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(26.2, 26.3, 26.4),
            current_cooler_temp=27.0,
        ))
        second = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(26.3, 26.4, 26.5),
            current_cooler_temp=27.0,
            consecutive_direction=first.consecutive_direction,
            consecutive_count=first.consecutive_count,
        ))

        self.assertFalse(first.should_change)
        self.assertEqual(first.reason, 'awaiting_confirmation')
        self.assertEqual(first.consecutive_count, 1)
        self.assertTrue(second.should_change)
        self.assertEqual(second.recommended_cooler_temp, 26.0)
        self.assertEqual(second.reason, 'above_deadband_confirmed')

    def test_low_temperature_requires_two_consecutive_cycles(self):
        first = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(25.0, 25.1, 25.2),
            current_cooler_temp=26.0,
        ))
        second = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(24.9, 25.0, 25.1),
            current_cooler_temp=26.0,
            consecutive_direction=first.consecutive_direction,
            consecutive_count=first.consecutive_count,
        ))

        self.assertFalse(first.should_change)
        self.assertEqual(
            first.consecutive_direction,
            StableDirection.COOL_LESS,
        )
        self.assertTrue(second.should_change)
        self.assertEqual(second.recommended_cooler_temp, 27.0)
        self.assertEqual(second.reason, 'below_deadband_confirmed')

    def test_deadband_resets_confirmation_without_change(self):
        decision = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(25.3, 25.7, 26.1),
            current_cooler_temp=26.0,
            consecutive_direction=StableDirection.COOL_MORE,
            consecutive_count=1,
        ))

        self.assertFalse(decision.should_change)
        self.assertEqual(decision.reason, 'within_deadband')
        self.assertIsNone(decision.consecutive_direction)
        self.assertEqual(decision.consecutive_count, 0)

    def test_change_is_blocked_within_15_minutes(self):
        decision = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(26.3, 26.4, 26.5),
            current_cooler_temp=27.0,
            last_change_at=self.now - timedelta(minutes=14),
            consecutive_direction=StableDirection.COOL_MORE,
            consecutive_count=1,
        ))

        self.assertFalse(decision.should_change)
        self.assertEqual(decision.recommended_cooler_temp, 27.0)
        self.assertEqual(decision.reason, 'minimum_change_interval')

    def test_each_stable_action_changes_at_most_one_degree(self):
        high = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(30.0, 30.0, 30.0),
            current_cooler_temp=30.0,
            consecutive_direction=StableDirection.COOL_MORE,
            consecutive_count=1,
        ))
        low = self.controller.decide(self._input(
            CoolingState.STABLE_COOLING,
            self._samples(20.0, 20.0, 20.0),
            current_cooler_temp=24.0,
            consecutive_direction=StableDirection.COOL_LESS,
            consecutive_count=1,
        ))

        self.assertEqual(high.recommended_cooler_temp, 29.0)
        self.assertEqual(low.recommended_cooler_temp, 25.0)

    def test_prediction_is_logged_but_does_not_change_decision(self):
        common = {
            'state': CoolingState.STABLE_COOLING,
            'temperatures': self._samples(25.5, 25.7, 25.9),
            'current_cooler_temp': 26.0,
            'now': self.now,
        }
        low_prediction = self.controller.decide(CoolingControlInput(
            predicted_temperature=20.0,
            **common,
        ))
        high_prediction = self.controller.decide(CoolingControlInput(
            predicted_temperature=35.0,
            **common,
        ))

        self.assertEqual(
            (
                low_prediction.next_state,
                low_prediction.should_change,
                low_prediction.recommended_cooler_temp,
                low_prediction.reason,
            ),
            (
                high_prediction.next_state,
                high_prediction.should_change,
                high_prediction.recommended_cooler_temp,
                high_prediction.reason,
            ),
        )
        self.assertEqual(
            low_prediction.log_data['predicted_temperature'],
            20.0,
        )
        self.assertEqual(
            high_prediction.log_data['predicted_temperature'],
            35.0,
        )


if __name__ == '__main__':
    unittest.main()
