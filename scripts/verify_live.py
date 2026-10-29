#!/usr/bin/env python3
"""Release gate against a running WindScope HTTP server (requires live Elexon data)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def get_json(url: str) -> dict:
    with urlopen(url, timeout=90) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description='Reject demo/missing/hindsight data in an actual running release')
    parser.add_argument('--url', default='http://localhost:8001', help='Application base URL')
    parser.add_argument('--date', default='2026-01-16', help='Delivery date in scope')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    try:
        health = get_json(f'{base}/api/health')
        if health.get('mode') != 'live':
            raise ValueError(f'Expected live mode; got {health.get("mode")!r}. Do not submit synthetic demo results.')
        report = get_json(f'{base}/api/analysis?delivery_date={args.date}&cutoff=12:00')
        if not report.get('source', '').startswith('Elexon BMRS'):
            raise ValueError('Analysis provenance is not Elexon BMRS')
        periods = report.get('periods', [])
        if len(periods) != 24:
            raise ValueError(f'Expected 24 hourly points, received {len(periods)}')
        if not report['statistics']['matched_periods']:
            raise ValueError('No comparable hourly forecasts and complete actuals')
        cutoff = datetime.fromisoformat(report['cutoff_utc'].replace('Z', '+00:00'))
        for row in periods:
            published = row.get('published_at')
            if published and datetime.fromisoformat(published.replace('Z', '+00:00')) > cutoff:
                raise ValueError(f'Future forecast leaked into analysis for {row["time"]}')
            if row['status'] == 'matched' and any(v is None for v in row['actual_half_hours_mw']):
                raise ValueError(f'Partial actual incorrectly reported as matched for {row["time"]}')
        stats = report['statistics']
        print(f'PASS: live Elexon, {stats["matched_periods"]}/24 matched hours, {stats["coverage_pct"]}% coverage, source timestamps verified')
        print('Next step: verify several dates and run the full January snapshot audit.')
    except (HTTPError, URLError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
