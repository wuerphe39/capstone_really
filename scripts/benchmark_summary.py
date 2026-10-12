"""Reproducible aggregate-only SQL/time benchmark on isolated synthetic records."""
import argparse
import hashlib
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from petmind.backend.database import Base, ObservationLog
from petmind.backend.services.outings import aggregate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    context = {'window_s': 5, 'timestamp': 5, 'bark': {'count': 1},
               'motion': {'dominant': 'unknown', 'seconds_by_label': {'unknown': 5}}}
    with Session(engine) as db:
        db.add_all([ObservationLog(pet_id='benchmark', session_id=f'input-{i}',
                    observed_at=datetime(2026, 10, 11), source='synthetic_demo',
                    context_json=json.dumps(context), summary='synthetic observation') for i in range(1000)])
        db.commit()
    counter = [0]
    @event.listens_for(engine, 'before_cursor_execute')
    def count(*_): counter[0] += 1
    runs = []
    for _ in range(3):
        with Session(engine) as db:
            rows = db.scalars(select(ObservationLog).order_by(ObservationLog.id)).all()
            counter[0] = 0
            start = time.perf_counter(); output = aggregate(db, rows); elapsed = time.perf_counter()-start
            runs.append({'seconds': elapsed, 'queries': counter[0],
                         'output_sha256': hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest()})
    result = {'rows': 1000, 'runs': runs, 'median_seconds': statistics.median(r['seconds'] for r in runs),
              'scope': 'in-memory SQLite synthetic records, aggregate only; not network or LLM latency'}
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
