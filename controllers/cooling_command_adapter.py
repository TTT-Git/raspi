from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
from typing import Optional


logger = logging.getLogger(__name__)


class CoolingCommandType(str, Enum):
    NOOP = 'noop'
    ENSURE_COOLING = 'ensure_cooling'
    SET_COOLER_TEMP = 'set_cooler_temp'
    TURN_OFF = 'turn_off'


@dataclass(frozen=True)
class CoolingCommand:
    command_type: CoolingCommandType
    cooler_temp: Optional[float]
    requested_at: datetime
    reason: str
    target_fan: Optional[str] = None
    previous_fan: Optional[str] = None
    control_state: Optional[str] = None


@dataclass(frozen=True)
class CoolingCommandResult:
    success: bool
    command: CoolingCommand
    message: str
    executed_at: datetime
    error: Optional[str] = None
    simulated: bool = False


class CoolingCommandAdapter(ABC):
    @abstractmethod
    def execute(self, command):
        raise NotImplementedError


class DryRunCoolingCommandAdapter(CoolingCommandAdapter):
    """Record commands and return configurable simulated results."""

    def __init__(self, succeed=True):
        self.succeed = succeed
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        if self.succeed:
            return CoolingCommandResult(
                success=True,
                command=command,
                message='dry-run command accepted',
                executed_at=command.requested_at,
                simulated=True,
            )
        return CoolingCommandResult(
            success=False,
            command=command,
            message='dry-run command rejected',
            executed_at=command.requested_at,
            error='simulated adapter failure',
            simulated=True,
        )


class RealCoolingCommandAdapter(CoolingCommandAdapter):
    """Execute commands through a sender that explicitly confirms success."""

    def __init__(self, sender, now_provider=None):
        self.sender = sender
        self.now_provider = now_provider or datetime.now

    def execute(self, command):
        if command.command_type == CoolingCommandType.NOOP:
            return self._result(
                command=command,
                success=True,
                message='no IR command required',
            )

        try:
            sender_result = self._send(command)
        except Exception as error:
            return self._result(
                command=command,
                success=False,
                message='IR command raised an exception',
                error=f'{type(error).__name__}: {error}',
            )

        if sender_result is True:
            return self._result(
                command=command,
                success=True,
                message='IR sender confirmed command success',
            )

        return self._result(
            command=command,
            success=False,
            message='IR sender did not confirm command success',
            error=f'unconfirmed sender result: {sender_result!r}',
        )

    def _send(self, command):
        if command.command_type in (
            CoolingCommandType.ENSURE_COOLING,
            CoolingCommandType.SET_COOLER_TEMP,
        ):
            if command.cooler_temp is None:
                raise ValueError(
                    f'{command.command_type.value} requires cooler_temp'
                )
            if command.target_fan is None:
                raise ValueError(
                    f'{command.command_type.value} requires target_fan'
                )
            return self.sender.cooler(
                temp=command.cooler_temp,
                fan=command.target_fan,
            )
        if command.command_type == CoolingCommandType.TURN_OFF:
            return self.sender.off()
        raise ValueError(
            f'unsupported cooling command: {command.command_type}'
        )

    def _result(
        self,
        command,
        success,
        message,
        error=None,
    ):
        executed_at = self.now_provider()
        result = CoolingCommandResult(
            success=success,
            command=command,
            message=message,
            executed_at=executed_at,
            error=error,
            simulated=False,
        )
        log_data = {
            'action': 'real cooling command',
            'status': 'success' if success else 'failed',
            'command': command.command_type.value,
            'target_temp': command.cooler_temp,
            'fan': command.target_fan,
            'previous_fan': command.previous_fan,
            'target_fan': command.target_fan,
            'control_state': command.control_state,
            'reason': command.reason,
            'success': success,
            'error': error,
            'executed_at': executed_at.isoformat(),
            'simulated': False,
        }
        if success:
            logger.info(log_data)
        else:
            logger.error(log_data)
        return result
