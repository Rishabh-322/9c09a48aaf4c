#!/usr/bin/env python3
"""Independent offline integrity audit for real Elexon snapshots.

Run from the project root: python scripts/deep_audit_january.py
This validates existing files, not live API correctness or dataset licenses.
"""
from __future__ import annotations
import csv
import hashlib
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.domain import FIRST_DELIVERY, LAST_DELIVERY, analyse_day, decision_cutoff, parse_timestamp  # noqa: E402
from app.elexon import ARCHIVE_DIR  # noqa: E402


def audit():
    results = []
    issues = []
    actual_signatures = {}
    forecast_signatures = {}
    for offset in range((LAST_DELIVERY - FIRST_DELIVERY).days + 1):
        day = FIRST_DELIVERY + timedelta(days=offset)
        file = ARCHIVE_DIR / f'{day}.json'
        if not file.is_file():
            issues.append(f'{day}: missing snapshot {file}')
            continue
        try:
            raw_bytes = file.read_bytes()
            snapshot = json.loads(raw_bytes)
            assert snapshot.get('delivery_date') == str(day), 'wrong embedded delivery date'
            assert snapshot.get('source') == 'Elexon BMRS', 'unexpected source label'
            assert snapshot.get('datasets') == ['WINDFOR', 'FUELHH'], 'unexpected datasets metadata'
            forecasts, actuals = snapshot['forecasts'], snapshot['actuals']
            assert isinstance(forecasts, list) and isinstance(actuals, list), 'non-list records'
            # Only FUELHH WIND records with target timestamps inside this delivery day
            # count as a day's raw half-hour actuals.
            wind = [r for r in actuals if r.get('fuelType', '').upper() == 'WIND']
            valid_wind_times = {
                parse_timestamp(r['startTime'])
                for r in wind if parse_timestamp(r['startTime']).date() == day
            }
            cutoff = time(12)
            decision = decision_cutoff(day, cutoff)
            report = analyse_day(day, cutoff, forecasts, actuals, 'Elexon BMRS')
            points = report['periods']
            eligible_pub = [p['published_at'] for p in points if p['published_at']]
            assert all(parse_timestamp(p) <= decision for p in eligible_pub), 'look-ahead publication detected'
            # Signature intentionally excludes timestamps: identical power profiles
            # across days should not be counted as independent merely due to dates.
            actual_profile = [(p['actual_mw'], p['actual_half_hours_mw']) for p in points]
            forecast_profile = [p['forecast_mw'] for p in points]
            actual_sig = hashlib.sha256(json.dumps(actual_profile).encode()).hexdigest()
            forecast_sig = hashlib.sha256(json.dumps(forecast_profile).encode()).hexdigest()
            if actual_sig in actual_signatures:
                issues.append(f'{day}: actual power profile identical to {actual_signatures[actual_sig]}')
            if forecast_sig in forecast_signatures:
                issues.append(f'{day}: selected forecast profile identical to {forecast_signatures[forecast_sig]}')
            actual_signatures[actual_sig] = str(day)
            forecast_signatures[forecast_sig] = str(day)
            s = report['statistics']
            if s['matched_periods'] != 24 or s['raw_actual_half_hours'] != 48:
                issues.append(f"{day}: only {s['matched_periods']}/24 matched; {s['raw_actual_half_hours']}/48 raw half-hours")
            if len(valid_wind_times) != 48:
                issues.append(f'{day}: {len(valid_wind_times)} distinct WIND timestamps for this date (expected 48)')
            if s['energy_basis'] != 'matched_hours_only':
                issues.append(f'{day}: energy totals do not declare matched-hour basis')
            results.append({
                'delivery_date': str(day),
                'raw_forecast_rows': len(forecasts),
                'raw_all_fuel_rows': len(actuals),
                'raw_wind_rows': len(wind),
                'distinct_wind_half_hours': len(valid_wind_times),
                'matched_hours': s['matched_periods'],
                'coverage_pct': s['coverage_pct'],
                'mae_mw': s['mae'],
                'selected_publications': len(eligible_pub),
                'snapshot_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                'actual_profile_sha256': actual_sig,
                'forecast_profile_sha256': forecast_sig,
            })
        except (AssertionError, KeyError, ValueError, TypeError, OSError) as exc:
            issues.append(f'{day}: invalid snapshot: {exc}')
    path = ROOT / 'january_deep_audit.csv'
    if results:
        with path.open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
    print(f'Snapshots checked: {len(results)}/31')
    print(f'Distinct daily actual power profiles: {len(actual_signatures)}')
    print(f'Distinct daily forecast profiles: {len(forecast_signatures)}')
    print(f'Matched hours total: {sum(r["matched_hours"] for r in results)}/744')
    if results:
        print(f'First snapshot raw rows: {results[0]["raw_forecast_rows"]} WINDFOR; {results[0]["raw_all_fuel_rows"]} FUELHH (all fuels); {results[0]["raw_wind_rows"]} WIND')
        print(f'CSV audit: {path}')
    if issues:
        print('FAIL:')
        for issue in issues:
            print(' -', issue)
        return 1
    print('PASS: independent snapshot integrity checks completed. This does not prove external source authenticity or matching measurement coverage definitions.')
    return 0


if __name__ == '__main__':
    raise SystemExit(audit())
