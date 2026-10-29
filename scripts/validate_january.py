#!/usr/bin/env python3
"""Offline data-quality audit for genuine Elexon snapshot files.

Run from the repository root: python scripts/validate_january.py
Reads only data files; never uses synthetic data or network calls.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.domain import FIRST_DELIVERY, LAST_DELIVERY, analyse_day  # noqa: E402
from app.elexon import ARCHIVE_DIR  # noqa: E402


def audit(path: Path = ARCHIVE_DIR, cutoff: time = time(12)) -> list[dict]:
    records = []
    for n in range((LAST_DELIVERY - FIRST_DELIVERY).days + 1):
        delivery: date = FIRST_DELIVERY + timedelta(days=n)
        file = path / f'{delivery.isoformat()}.json'
        if not file.exists():
            records.append({'delivery_date': delivery.isoformat(), 'status': 'missing_snapshot', 'matched_hours': 0,
                            'coverage_pct': 0, 'forecast_rows': 0, 'wind_actual_rows': 0})
            continue
        try:
            raw = json.loads(file.read_text())
            if raw.get('delivery_date') != delivery.isoformat() or raw.get('source') != 'Elexon BMRS':
                raise ValueError('unexpected snapshot date or source')
            forecasts = raw['forecasts']
            actuals = raw['actuals']
            if not isinstance(forecasts, list) or not isinstance(actuals, list):
                raise ValueError('datasets must be lists')
            report = analyse_day(delivery, cutoff, forecasts, actuals, 'Elexon BMRS')
            matched = report['statistics']['matched_periods']
            records.append({'delivery_date': delivery.isoformat(), 'status': 'ok' if matched else 'no_matched_hours',
                            'matched_hours': matched, 'coverage_pct': report['statistics']['coverage_pct'],
                            'forecast_rows': len(forecasts),
                            'wind_actual_rows': sum(str(x.get('fuelType', '')).upper() == 'WIND' for x in actuals)})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            records.append({'delivery_date': delivery.isoformat(), 'status': f'invalid: {exc}', 'matched_hours': 0,
                            'coverage_pct': 0, 'forecast_rows': 0, 'wind_actual_rows': 0})
    return records


def main():
    rows = audit()
    output = ROOT / 'january_data_audit.csv'
    with output.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    passed = sum(row['status'] == 'ok' for row in rows)
    print(f'Days with matched genuine Elexon records: {passed}/{len(rows)}')
    print(f'Minimum daily coverage: {min(row["coverage_pct"] for row in rows)}%')
    print(f'Per-day audit: {output}')
    if passed != len(rows):
        print('WARNING: not all days have eligible matching records; investigate before claiming month coverage.', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
