from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


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
