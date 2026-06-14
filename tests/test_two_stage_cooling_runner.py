import unittest
from datetime import datetime
from datetime import timedelta

from controllers.cooling_command_adapter import CoolingCommandType
from controllers.cooling_command_adapter import DryRunCoolingCommandAdapter
from controllers.two_stage_cooling_runner import TwoStageCoolingRunner
from controllers.two_stage_cooling_runner import (
    TwoStageCoolingRuntimeState,
)
from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import StableDirection
from models.two_stage_cooling import TemperatureSample


class TwoStageCoolingRunnerTest(unittest.TestCase):
    def setUp(self):
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

    def test_stopped_to_stable_ensures_cooling_without_setting_change(self):
        adapter = DryRunCoolingCommandAdapter()
        runner = TwoStageCoolingRunner(adapter)

        result = runner.run_cycle(
            self._samples(25.5, 25.7, 25.9),
            self.now,
        )

        self.assertFalse(result.decision.should_change)
        self.assertTrue(result.decision.action_required)
        self.assertEqual(
            result.command.command_type,
            CoolingCommandType.ENSURE_COOLING,
        )
        self.assertEqual(result.command.cooler_temp, 26.0)
        self.assertTrue(result.committed)
        self.assertEqual(
            runner.state.control_state,
            CoolingState.STABLE_COOLING,
        )

    def test_stopped_to_recovery_sets_cooler_to_24(self):
        adapter = DryRunCoolingCommandAdapter()
        runner = TwoStageCoolingRunner(adapter)

        result = runner.run_cycle(
            self._samples(27.5, 28.0, 28.5),
            self.now,
        )

        self.assertTrue(result.decision.should_change)
        self.assertTrue(result.decision.action_required)
        self.assertEqual(
            result.command.command_type,
            CoolingCommandType.SET_COOLER_TEMP,
        )
        self.assertEqual(result.command.cooler_temp, 24.0)
        self.assertEqual(
            runner.state.control_state,
            CoolingState.RECOVERY_COOLING,
        )
        self.assertEqual(runner.state.current_cooler_temp, 24.0)
        self.assertEqual(runner.state.last_change_at, self.now)
        self.assertEqual(runner.state.recovery_started_at, self.now)

    def test_stable_deadband_is_noop_when_cooling_is_already_on(self):
        adapter = DryRunCoolingCommandAdapter()
        runner = TwoStageCoolingRunner(
            adapter,
            initial_state=TwoStageCoolingRuntimeState(
                control_state=CoolingState.STABLE_COOLING,
                current_cooler_temp=26.0,
            ),
        )

        result = runner.run_cycle(
            self._samples(25.5, 25.7, 25.9),
            self.now,
        )

        self.assertFalse(result.decision.should_change)
        self.assertFalse(result.decision.action_required)
        self.assertEqual(
            result.command.command_type,
            CoolingCommandType.NOOP,
        )
        self.assertEqual(runner.state.current_cooler_temp, 26.0)

    def test_stable_setting_change_generates_set_temperature_command(self):
        adapter = DryRunCoolingCommandAdapter()
        runner = TwoStageCoolingRunner(
            adapter,
            initial_state=TwoStageCoolingRuntimeState(
                control_state=CoolingState.STABLE_COOLING,
                current_cooler_temp=27.0,
                consecutive_direction=StableDirection.COOL_MORE,
                consecutive_count=1,
            ),
        )

        result = runner.run_cycle(
            self._samples(26.3, 26.4, 26.5),
            self.now,
        )

        self.assertTrue(result.decision.should_change)
        self.assertTrue(result.decision.action_required)
        self.assertEqual(
            result.command.command_type,
            CoolingCommandType.SET_COOLER_TEMP,
        )
        self.assertEqual(result.command.cooler_temp, 26.0)
        self.assertEqual(runner.state.current_cooler_temp, 26.0)

    def test_adapter_success_commits_all_proposed_state(self):
        adapter = DryRunCoolingCommandAdapter(succeed=True)
        runner = TwoStageCoolingRunner(adapter)

        result = runner.run_cycle(
            self._samples(27.5, 28.0, 28.5),
            self.now,
        )

        self.assertTrue(result.committed)
        self.assertEqual(
            result.state.control_state,
            result.decision.next_state,
        )
        self.assertEqual(
            result.state.current_cooler_temp,
            result.decision.recommended_cooler_temp,
        )
        self.assertEqual(
            result.state.last_change_at,
            result.decision.last_change_at,
        )
        self.assertEqual(
            result.state.recovery_started_at,
            result.decision.recovery_started_at,
        )

    def test_adapter_failure_does_not_commit_any_proposed_state(self):
        adapter = DryRunCoolingCommandAdapter(succeed=False)
        initial_state = TwoStageCoolingRuntimeState(
            control_state=CoolingState.STABLE_COOLING,
            current_cooler_temp=27.0,
            last_change_at=self.now - timedelta(minutes=20),
            consecutive_direction=StableDirection.COOL_MORE,
            consecutive_count=1,
        )
        runner = TwoStageCoolingRunner(
            adapter,
            initial_state=initial_state,
        )

        result = runner.run_cycle(
            self._samples(26.3, 26.4, 26.5),
            self.now,
        )

        self.assertFalse(result.committed)
        self.assertFalse(result.command_result.success)
        self.assertTrue(result.decision.should_change)
        self.assertEqual(runner.state, initial_state)
        self.assertEqual(result.state, initial_state)

    def test_dry_run_adapter_records_without_real_ir_dependency(self):
        adapter = DryRunCoolingCommandAdapter()
        runner = TwoStageCoolingRunner(adapter)

        result = runner.run_cycle(
            self._samples(27.5, 28.0, 28.5),
            self.now,
        )

        self.assertEqual(adapter.commands, [result.command])
        self.assertTrue(result.command_result.simulated)
        self.assertEqual(
            result.command_result.command,
            result.command,
        )
        self.assertEqual(
            result.command_result.executed_at,
            self.now,
        )


if __name__ == '__main__':
    unittest.main()
