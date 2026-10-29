#!/usr/bin/env python3
"""Opt-in genuine Elexon archive preparation (requires internet and Python backend deps).

Run from repo root: PYTHONPATH=backend python scripts/snapshot_january.py
Never stores generated demo/sample numbers. Fails if upstream fails.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from datetime import date, datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['WINDSCOPE_IGNORE_ARCHIVE'] = '1'

from app.domain import FIRST_DELIVERY, LAST_DELIVERY  # noqa: E402
from app.elexon import ARCHIVE_DIR, fetch_delivery_data  # noqa: E402


async def main():
    archive = ARCHIVE_DIR
    archive.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(3)
    async def fetch_one(day: date):
        async with semaphore:
            print(f'Fetching {day.isoformat()} from real Elexon endpoints…', flush=True)
            forecast, actual = await fetch_delivery_data(day)
            # Never write a snapshot whose raw sources are both empty.
            if not forecast or not actual:
                raise RuntimeError(f'Upstream incomplete on {day}: forecasts={len(forecast)} actuals={len(actual)}. Nothing archived for this day.')
            payload = {'delivery_date': day.isoformat(), 'source': 'Elexon BMRS', 'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'datasets': ['WINDFOR','FUELHH'], 'forecasts': forecast, 'actuals': actual}
            target = archive / f'{day.isoformat()}.json'
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(payload, separators=(',', ':')))
            temp.replace(target)
            print(f'  ✓ {day}: {len(forecast)} raw forecast rows (multiple target days), {len(actual)} raw outturn rows (all fuels)')
    days = [FIRST_DELIVERY + timedelta(days=i) for i in range((LAST_DELIVERY - FIRST_DELIVERY).days + 1)]
    await asyncio.gather(*(fetch_one(day) for day in days))
    print(f'\nAll {len(days)} Elexon daily snapshots saved under {archive}. Run tests and inspect monthly coverage before deployment.')


if __name__ == '__main__':
    asyncio.run(main())
