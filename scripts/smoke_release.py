#!/usr/bin/env python3
"""Dependency-free release acceptance test against a running WindScope HTTP URL.

Examples:
  python scripts/smoke_release.py --url http://localhost:8004 --mode live --expect-origin local_snapshot --full-coverage
  python scripts/smoke_release.py --url http://localhost:8004 --mode demo
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def fetch(url: str, endpoint: str, params=None, *, as_text=False):
    target = url.rstrip('/') + endpoint + (('?' + urlencode(params)) if params else '')
    with urlopen(target, timeout=120) as response:
        body = response.read().decode('utf-8')
        if response.status != 200:
            raise AssertionError(f'{endpoint} returned HTTP {response.status}')
    return body if as_text else json.loads(body)


def check(url: str, mode: str, expect_origin: str | None, full_coverage: bool):
    # Container boot can take a moment on CI machines.
    for attempt in range(20):
        try:
            health = fetch(url, '/api/health')
            break
        except (URLError, ConnectionError):
            if attempt == 19:
                raise
            time.sleep(1)
    assert health['status'] == 'ok', health
    assert health['mode'] == mode, health
    assert health['version'] == '2.2.0', health
    print(f"PASS health: version={health['version']} mode={health['mode']} commit={health.get('build_commit')}")

    day = '2026-01-16'
    report = fetch(url, '/api/analysis', {'delivery_date': day, 'cutoff': '12:00'})
    assert report['delivery_date'] == day
    assert len(report['periods']) == 24
    assert report['statistics']['period_minutes'] == 60
    assert report['data_origin'] in {'synthetic', 'local_snapshot', 'api_or_cache'}
    if expect_origin:
        assert report['data_origin'] == expect_origin, report['data_origin']
    assert ('DEMO' in report['source']) == (mode == 'demo')
    cutoff = datetime.fromisoformat(report['cutoff_utc'].replace('Z', '+00:00'))
    errors = []
    for row in report['periods']:
        if row['published_at']:
            publication = datetime.fromisoformat(row['published_at'].replace('Z', '+00:00'))
            assert publication <= cutoff, row
        if row['error_mw'] is not None:
            assert row['forecast_mw'] is not None and row['actual_mw'] is not None
            assert abs(row['forecast_mw'] - row['actual_mw'] - row['error_mw']) <= 0.02
            errors.append(row['error_mw'])
    assert len(errors) == report['statistics']['matched_periods']
    net = round(sum(errors), 1) if errors else None
    assert net == report['decision_brief']['net_energy_error_mwh'], (net, report['decision_brief'])
    print(f"PASS daily: {report['data_origin']} {len(errors)}/24 matched; net forecast error {net} MWh")

    compare = fetch(url, '/api/compare', {'delivery_date':day,'early':'09:00','late':'18:00'})
    paired = compare['common_comparison']
    assert paired['matched_hours'] <= 24
    assert paired['matched_hours'] <= min(compare['early']['statistics']['matched_periods'], compare['late']['statistics']['matched_periods'])
    if paired['matched_hours']:
        assert abs(round(paired['late_mae_mw'] - paired['early_mae_mw'],1)-paired['delta_mae_mw']) <= 0.11
    print(f"PASS decision comparison: {paired['matched_hours']} common hours; {paired['outcome']}")

    month = fetch(url, '/api/month', {'cutoff':'12:00'})
    assert len(month['days']) == 31
    assert month['statistics']['total_periods'] == 744
    if full_coverage:
        assert month['statistics']['matched_periods'] == 744, month['statistics']
    print(f"PASS monthly: {len(month['days'])} days, {month['statistics']['matched_periods']}/744 hours")

    csv = fetch(url, '/api/export', {'delivery_date':day, 'cutoff':'12:00'}, as_text=True)
    assert 'hour_start_utc' in csv and 'forecast_published_at_utc' in csv and 'data_origin' in csv
    assert len(csv.strip().splitlines()) == 25
    print('PASS CSV: 24 hourly data rows plus header')

    try:
        fetch(url, '/api/analysis', {'delivery_date':'2026-03-01'})
    except HTTPError as exc:
        assert exc.code == 422, exc.code
        print('PASS invalid date: HTTP 422')
    else:
        raise AssertionError('Invalid delivery date was accepted')
    print('RELEASE SMOKE CHECK: PASSED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8004')
    parser.add_argument('--mode', choices=('live','demo'), default='live')
    parser.add_argument('--expect-origin', choices=('synthetic','local_snapshot','api_or_cache'))
    parser.add_argument('--full-coverage', action='store_true')
    args = parser.parse_args()
    try:
        check(args.url, args.mode, args.expect_origin, args.full_coverage)
    except Exception as exc:
        print(f'RELEASE SMOKE CHECK: FAILED — {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
