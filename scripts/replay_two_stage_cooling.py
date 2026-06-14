import argparse
from dataclasses import asdict
from datetime import datetime
from datetime import timedelta
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from models.two_stage_cooling import TemperatureSample
from models.two_stage_cooling_replay import TwoStageCoolingReplay
from models.two_stage_cooling_replay import (
    load_temperature_samples_from_sqlite,
)


def sample_temperatures():
    start = datetime(2026, 6, 14, 18, 0, 0)
    values = (
        28.0,
        27.6,
        26.0,
        26.0,
        26.4,
        26.4,
        26.4,
        26.4,
        26.4,
        25.7,
        25.7,
    )
    return [
        TemperatureSample(
            time=start + timedelta(minutes=3 * index),
            temperature=value,
        )
        for index, value in enumerate(values)
    ]


def parse_args():
    parser = argparse.ArgumentParser(
        description='Replay two-stage cooling decisions without IR or DB writes',
    )
    parser.add_argument(
        '--db',
        help='SQLite database path; omitted to use built-in sample data',
    )
    parser.add_argument(
        '--table',
        default='TempHumid_Raspi4B_1_0',
        help='temperature table used with --db',
    )
    parser.add_argument('--start', help='inclusive ISO start time')
    parser.add_argument('--end', help='inclusive ISO end time')
    parser.add_argument(
        '--initial-cooler-temp',
        type=float,
        default=26.0,
    )
    parser.add_argument(
        '--cycle-minutes',
        type=float,
        default=3.0,
        help='minimum interval between replayed control cycles',
    )
    parser.add_argument(
        '--events',
        action='store_true',
        help='include per-cycle replay events',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.db:
        samples = load_temperature_samples_from_sqlite(
            database_path=args.db,
            table=args.table,
            start=args.start,
            end=args.end,
        )
        source = str(Path(args.db))
    else:
        samples = sample_temperatures()
        source = 'built-in sample'

    result = TwoStageCoolingReplay().run(
        samples,
        initial_cooler_temp=args.initial_cooler_temp,
        cycle_interval_minutes=args.cycle_minutes,
    )
    output = {
        'source': source,
        'summary': asdict(result.summary),
    }
    if args.events:
        output['events'] = [
            {
                **asdict(event),
                'time': event.time.isoformat(),
                'previous_state': event.previous_state.value,
                'next_state': event.next_state.value,
            }
            for event in result.events
        ]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
