import unittest
from datetime import datetime
from datetime import timedelta

from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import TemperatureSample
from models.two_stage_cooling_replay import TwoStageCoolingReplay


class TwoStageCoolingReplayTest(unittest.TestCase):
    def setUp(self):
        self.replay = TwoStageCoolingReplay()
        self.start = datetime(2026, 6, 14, 18, 0, 0)

    def _samples(self, *temperatures):
        return [
            TemperatureSample(
                time=self.start + timedelta(minutes=3 * index),
                temperature=temperature,
            )
            for index, temperature in enumerate(temperatures)
        ]

    def test_fixed_samples_replay_without_database(self):
        result = self.replay.run(self._samples(25.7, 25.8, 25.6))

        self.assertEqual(result.summary.total_cycles, 3)
        self.assertEqual(result.summary.setting_change_count, 0)
        self.assertEqual(result.summary.deadband_cycle_count, 2)
        self.assertEqual(result.summary.deadband_change_count, 0)

    def test_recovery_transitions_to_stable(self):
        result = self.replay.run(self._samples(
            28.0,
            27.6,
            26.0,
            26.0,
        ))

        self.assertEqual(result.summary.recovery_entry_count, 1)
        self.assertEqual(result.summary.stable_entry_count, 1)
        self.assertEqual(
            result.events[0].next_state,
            CoolingState.RECOVERY_COOLING,
        )
        self.assertEqual(
            result.events[-1].next_state,
            CoolingState.STABLE_COOLING,
        )

    def test_stable_changes_are_limited_and_not_excessive(self):
        result = self.replay.run(
            self._samples(
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
                26.4,
            ),
            initial_state=CoolingState.STABLE_COOLING,
        )

        self.assertLessEqual(result.summary.changes_per_hour, 4.0)
        self.assertLessEqual(result.summary.max_stable_change_amount, 1.0)
        self.assertGreater(
            result.summary.minimum_interval_suppression_count,
            0,
        )

    def test_minimum_interval_suppression_is_counted(self):
        result = self.replay.run(
            self._samples(26.4, 26.4, 26.4, 26.4, 26.4, 26.4),
            initial_state=CoolingState.STABLE_COOLING,
        )

        self.assertEqual(result.summary.setting_change_count, 1)
        self.assertGreaterEqual(
            result.summary.minimum_interval_suppression_count,
            1,
        )
        self.assertEqual(
            result.summary.reason_counts['minimum_change_interval'],
            result.summary.minimum_interval_suppression_count,
        )

    def test_deadband_cycles_never_change_setting(self):
        result = self.replay.run(
            self._samples(25.3, 25.7, 26.1, 25.5, 25.9),
            initial_state=CoolingState.STABLE_COOLING,
        )

        self.assertEqual(result.summary.setting_change_count, 0)
        self.assertEqual(result.summary.deadband_change_count, 0)
        self.assertEqual(
            result.summary.deadband_cycle_count,
            result.summary.total_cycles,
        )

    def test_replay_sorts_samples_by_time(self):
        samples = self._samples(25.7, 25.8, 25.9)

        result = self.replay.run(tuple(reversed(samples)))

        self.assertEqual(
            [event.time for event in result.events],
            [sample.time for sample in samples],
        )

    def test_cycle_interval_keeps_raw_samples_for_median(self):
        samples = [
            TemperatureSample(
                time=self.start + timedelta(minutes=index),
                temperature=temperature,
            )
            for index, temperature in enumerate(
                (28.0, 27.8, 27.6, 27.4, 27.2, 27.0, 26.8)
            )
        ]

        result = self.replay.run(
            samples,
            cycle_interval_minutes=3,
        )

        self.assertEqual(result.summary.total_cycles, 3)
        self.assertEqual(
            [event.time for event in result.events],
            [samples[0].time, samples[3].time, samples[6].time],
        )
        self.assertAlmostEqual(
            result.events[1].median_temperature,
            27.7,
        )


if __name__ == '__main__':
    unittest.main()
