from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from typing import Sequence

from controllers.cooling_command_adapter import CoolingCommand
from controllers.cooling_command_adapter import CoolingCommandAdapter
from controllers.cooling_command_adapter import CoolingCommandResult
from controllers.cooling_command_adapter import CoolingCommandType
from models.two_stage_cooling import CoolingControlInput
from models.two_stage_cooling import CoolingDecision
from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import StableDirection
from models.two_stage_cooling import TemperatureSample
from models.two_stage_cooling import TwoStageCoolingController


@dataclass(frozen=True)
class TwoStageCoolingRuntimeState:
    control_state: CoolingState = CoolingState.STOPPED
    current_cooler_temp: float = 26.0
    last_change_at: Optional[datetime] = None
    recovery_started_at: Optional[datetime] = None
    consecutive_direction: Optional[StableDirection] = None
    consecutive_count: int = 0


@dataclass(frozen=True)
class TwoStageCoolingRunResult:
    decision: CoolingDecision
    command: CoolingCommand
    command_result: CoolingCommandResult
    committed: bool
    state: TwoStageCoolingRuntimeState


class TwoStageCoolingRunner:
    """Run one pure decision cycle and commit only accepted commands."""

    def __init__(
        self,
        adapter: CoolingCommandAdapter,
        controller=None,
        initial_state=None,
    ):
        self.adapter = adapter
        self.controller = controller or TwoStageCoolingController()
        self.state = initial_state or TwoStageCoolingRuntimeState()

    def run_cycle(
        self,
        temperatures: Sequence[TemperatureSample],
        now,
        predicted_temperature=None,
        force_recovery=False,
    ):
        previous_state = self.state
        decision = self.controller.decide(CoolingControlInput(
            state=previous_state.control_state,
            temperatures=temperatures,
            current_cooler_temp=previous_state.current_cooler_temp,
            now=now,
            last_change_at=previous_state.last_change_at,
            recovery_started_at=previous_state.recovery_started_at,
            consecutive_direction=previous_state.consecutive_direction,
            consecutive_count=previous_state.consecutive_count,
            predicted_temperature=predicted_temperature,
            force_recovery=force_recovery,
        ))
        command = self._command_for(decision, now)
        command_result = self.adapter.execute(command)

        if command_result.success:
            self.state = self._committed_state(decision, previous_state)

        return TwoStageCoolingRunResult(
            decision=decision,
            command=command,
            command_result=command_result,
            committed=command_result.success,
            state=self.state,
        )

    @staticmethod
    def _command_for(decision, now):
        if not decision.action_required:
            command_type = CoolingCommandType.NOOP
        elif decision.should_change:
            command_type = CoolingCommandType.SET_COOLER_TEMP
        else:
            command_type = CoolingCommandType.ENSURE_COOLING

        return CoolingCommand(
            command_type=command_type,
            cooler_temp=decision.recommended_cooler_temp,
            requested_at=now,
            reason=decision.reason,
        )

    @staticmethod
    def _committed_state(decision, previous_state):
        current_cooler_temp = previous_state.current_cooler_temp
        if decision.should_change:
            current_cooler_temp = decision.recommended_cooler_temp

        return TwoStageCoolingRuntimeState(
            control_state=decision.next_state,
            current_cooler_temp=current_cooler_temp,
            last_change_at=decision.last_change_at,
            recovery_started_at=decision.recovery_started_at,
            consecutive_direction=decision.consecutive_direction,
            consecutive_count=decision.consecutive_count,
        )
