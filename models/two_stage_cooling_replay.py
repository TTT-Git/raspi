from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path
import re
import sqlite3
from typing import Optional
from typing import Sequence

from models.two_stage_cooling import CoolingControlInput
from models.two_stage_cooling import CoolingDecision
from models.two_stage_cooling import CoolingState
from models.two_stage_cooling import TemperatureSample
from models.two_stage_cooling import TwoStageCoolingController


@dataclass(frozen=True)
class CoolingReplayEvent:
    time: datetime
    temperature: float
    median_temperature: float
    previous_state: CoolingState
    next_state: CoolingState
    previous_cooler_temp: float
    recommended_cooler_temp: float
    should_change: bool
    change_amount: float
    reason: str


@dataclass(frozen=True)
class CoolingReplaySummary:
    total_cycles: int
    duration_hours: float
    setting_change_count: int
    changes_per_hour: float
    max_change_amount: float
    max_stable_change_amount: float
    recovery_entry_count: int
    stable_entry_count: int
    reason_counts: dict
    deadband_cycle_count: int
    deadband_change_count: int
    minimum_interval_suppression_count: int


@dataclass(frozen=True)
class CoolingReplayResult:
    events: Sequence[CoolingReplayEvent]
    summary: CoolingReplaySummary


class TwoStageCoolingReplay:
    """Replay temperature samples without DB writes, IR sends, or GPIO I/O."""

    def __init__(self, controller=None):
        self.controller = controller or TwoStageCoolingController()

    def run(
        self,
        samples,
        initial_cooler_temp=26.0,
        initial_state=CoolingState.STOPPED,
        cycle_interval_minutes=None,
    ):
        ordered_samples = self._ordered_samples(samples)
        if not ordered_samples:
            return CoolingReplayResult(
                events=(),
                summary=self._summarize(()),
            )

        state = initial_state
        current_cooler_temp = float(initial_cooler_temp)
        last_change_at = None
        recovery_started_at = None
        consecutive_direction = None
        consecutive_count = 0
        history = []
        events = []
        last_cycle_at = None

        for sample in ordered_samples:
            history.append(sample)
            if (
                cycle_interval_minutes is not None
                and last_cycle_at is not None
                and sample.time - last_cycle_at
                < timedelta(minutes=cycle_interval_minutes)
            ):
                continue

            decision = self.controller.decide(CoolingControlInput(
                state=state,
                temperatures=history,
                current_cooler_temp=current_cooler_temp,
                now=sample.time,
                last_change_at=last_change_at,
                recovery_started_at=recovery_started_at,
                consecutive_direction=consecutive_direction,
                consecutive_count=consecutive_count,
            ))
            last_cycle_at = sample.time
            event = self._event(
                sample=sample,
                previous_state=state,
                previous_cooler_temp=current_cooler_temp,
                decision=decision,
            )
            events.append(event)

            state = decision.next_state
            if decision.should_change:
                current_cooler_temp = decision.recommended_cooler_temp
            last_change_at = decision.last_change_at
            recovery_started_at = decision.recovery_started_at
            consecutive_direction = decision.consecutive_direction
            consecutive_count = decision.consecutive_count

        return CoolingReplayResult(
            events=tuple(events),
            summary=self._summarize(events),
        )

    @staticmethod
    def _ordered_samples(samples):
        ordered = sorted(samples, key=lambda sample: sample.time)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.time == current.time:
                raise ValueError('temperature sample times must be unique')
        return ordered

    @staticmethod
    def _event(
        sample,
        previous_state,
        previous_cooler_temp,
        decision,
    ):
        change_amount = (
            abs(decision.recommended_cooler_temp - previous_cooler_temp)
            if decision.should_change
            else 0.0
        )
        return CoolingReplayEvent(
            time=sample.time,
            temperature=float(sample.temperature),
            median_temperature=decision.median_temperature,
            previous_state=previous_state,
            next_state=decision.next_state,
            previous_cooler_temp=previous_cooler_temp,
            recommended_cooler_temp=decision.recommended_cooler_temp,
            should_change=decision.should_change,
            change_amount=change_amount,
            reason=decision.reason,
        )

    @staticmethod
    def _summarize(events):
        events = tuple(events)
        changes = [event for event in events if event.should_change]
        stable_changes = [
            event
            for event in changes
            if event.previous_state == CoolingState.STABLE_COOLING
            and event.next_state == CoolingState.STABLE_COOLING
        ]
        reason_counts = Counter(event.reason for event in events)
        deadband_events = [
            event for event in events if event.reason == 'within_deadband'
        ]

        duration_hours = 0.0
        if len(events) >= 2:
            duration_hours = (
                events[-1].time - events[0].time
            ).total_seconds() / 3600.0
        changes_per_hour = (
            len(changes) / duration_hours
            if duration_hours > 0
            else 0.0
        )

        return CoolingReplaySummary(
            total_cycles=len(events),
            duration_hours=duration_hours,
            setting_change_count=len(changes),
            changes_per_hour=changes_per_hour,
            max_change_amount=max(
                (event.change_amount for event in changes),
                default=0.0,
            ),
            max_stable_change_amount=max(
                (event.change_amount for event in stable_changes),
                default=0.0,
            ),
            recovery_entry_count=sum(
                event.previous_state != CoolingState.RECOVERY_COOLING
                and event.next_state == CoolingState.RECOVERY_COOLING
                for event in events
            ),
            stable_entry_count=sum(
                event.previous_state != CoolingState.STABLE_COOLING
                and event.next_state == CoolingState.STABLE_COOLING
                for event in events
            ),
            reason_counts=dict(sorted(reason_counts.items())),
            deadband_cycle_count=len(deadband_events),
            deadband_change_count=sum(
                event.should_change for event in deadband_events
            ),
            minimum_interval_suppression_count=reason_counts.get(
                'minimum_change_interval',
                0,
            ),
        )


def load_temperature_samples_from_sqlite(
    database_path,
    table='TempHumid_Raspi4B_1_0',
    start=None,
    end=None,
):
    """Load temperature samples from SQLite using a read-only connection."""
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table):
        raise ValueError('invalid SQLite table name')

    path = Path(database_path).expanduser().resolve()
    connection = sqlite3.connect(
        f'{path.as_uri()}?mode=ro',
        uri=True,
    )
    try:
        table_exists = connection.execute(
            'SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?',
            ('table', table),
        ).fetchone()
        if table_exists is None:
            raise ValueError(f'SQLite table does not exist: {table}')

        conditions = ['temperature IS NOT NULL']
        parameters = []
        if start is not None:
            conditions.append('time >= ?')
            parameters.append(_sqlite_time(start))
        if end is not None:
            conditions.append('time <= ?')
            parameters.append(_sqlite_time(end))

        query = (
            f'SELECT time, temperature FROM "{table}" '
            f'WHERE {" AND ".join(conditions)} ORDER BY time'
        )
        rows = connection.execute(query, parameters).fetchall()
    finally:
        connection.close()

    return [
        TemperatureSample(
            time=datetime.fromisoformat(time_text),
            temperature=float(temperature),
        )
        for time_text, temperature in rows
    ]


def _sqlite_time(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    return str(value)
