"""FastAPI app powering the product and serving built frontend in production."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .domain import FIRST_DELIVERY, LAST_DELIVERY, analyse_day, compare_cutoffs, ensure_delivery_in_scope, parse_cutoff, summarise_month
from .elexon import ARCHIVE_DIR, UpstreamError, fetch_delivery_data
from .sample import demo_rows

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
app = FastAPI(title='WindScope API', version='2.2.0', description='Reproducible UK wind day-ahead forecast assessment. January 2026 decision scope.')
app.add_middleware(CORSMiddleware, allow_origins=[x for x in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',') if x], allow_methods=['GET'], allow_headers=['*'])
MODE = os.getenv('WINDSCOPE_DATA_MODE', 'live').lower()
if MODE not in ('live', 'demo'):
    raise RuntimeError('WINDSCOPE_DATA_MODE must be live or demo')


def validate(raw_date: date, cutoff: str):
    try:
        ensure_delivery_in_scope(raw_date)
        return parse_cutoff(cutoff)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def origin_for(delivery_date: date) -> str:
    # An API lookup may hit a local HTTP cache. Don't label it as a fresh response.
    if MODE == 'demo':
        return 'synthetic'
    if os.getenv('WINDSCOPE_IGNORE_ARCHIVE', '0') != '1' and (ARCHIVE_DIR / f'{delivery_date.isoformat()}.json').is_file():
        return 'local_snapshot'
    return 'api_or_cache'


async def day_report(delivery_date: date, cutoff: str) -> dict:
    parsed = validate(delivery_date, cutoff)
    try:
        forecasts, actuals = demo_rows(delivery_date) if MODE == 'demo' else await fetch_delivery_data(delivery_date)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = analyse_day(delivery_date, parsed, forecasts, actuals, 'DEMO · synthetic illustrative data' if MODE == 'demo' else 'Elexon BMRS · WINDFOR + FUELHH')
    result['data_origin'] = origin_for(delivery_date)
    return result


@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': app.version, 'mode': MODE, 'build_commit': os.getenv('WINDSCOPE_BUILD_COMMIT', 'local')}


@app.get('/api/meta')
def meta():
    return {
        'product': 'WindScope', 'mode': MODE,
        'first_delivery': FIRST_DELIVERY.isoformat(),
        'last_delivery': LAST_DELIVERY.isoformat(),
        'decision_month': 'January 2026',
        'default_cutoff': '12:00',
        'comparison_method': 'Hourly WINDFOR MW against the mean of both FUELHH half-hour readings',
        'cutoff_note': '12:00 UK local time is a configurable scenario assumption, not a verified market gate-closure.',
    }


@app.get('/api/analysis')
async def analysis(delivery_date: date = Query(default=date(2026, 1, 16)), cutoff: str = '12:00'):
    return await day_report(delivery_date, cutoff)


@app.get('/api/month')
async def month(cutoff: str = '12:00'):
    validate(FIRST_DELIVERY, cutoff)
    # Bound concurrent fetching to avoid hammering the public Elexon API.
    semaphore = asyncio.Semaphore(3)
    async def bounded(day: date):
        async with semaphore:
            return await day_report(day, cutoff)
    dates = [FIRST_DELIVERY + timedelta(days=n) for n in range((LAST_DELIVERY - FIRST_DELIVERY).days + 1)]
    daily = await asyncio.gather(*(bounded(day) for day in dates))
    return summarise_month(daily, cutoff, daily[0]['source'])


@app.get('/api/compare')
async def compare(delivery_date: date = Query(default=date(2026, 1, 16)), early: str = '09:00', late: str = '18:00'):
    early_time = validate(delivery_date, early)
    late_time = validate(delivery_date, late)
    if early_time >= late_time:
        raise HTTPException(status_code=422, detail='Early cut-off must precede late cut-off')
    try:
        forecasts, actuals = demo_rows(delivery_date) if MODE == 'demo' else await fetch_delivery_data(delivery_date)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = compare_cutoffs(delivery_date, early_time, late_time, forecasts, actuals,
                           'DEMO · synthetic illustrative data' if MODE == 'demo' else 'Elexon BMRS · WINDFOR + FUELHH')
    result['data_origin'] = origin_for(delivery_date)
    return result


@app.get('/api/export')
async def export(delivery_date: date = Query(default=date(2026, 1, 16)), cutoff: str = '12:00'):
    report = await day_report(delivery_date, cutoff)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['hour_start_utc', 'hour_start_uk', 'forecast_mw', 'hourly_actual_avg_mw', 'actual_first_half_hour_mw', 'actual_second_half_hour_mw', 'signed_error_mw', 'forecast_published_at_utc', 'status', 'decision_cutoff_utc', 'source', 'data_origin'])
    for row in report['periods']:
        writer.writerow([row['time'], row['label'], row['forecast_mw'], row['actual_mw'], *row['actual_half_hours_mw'], row['error_mw'], row['published_at'], row['status'], report['cutoff_utc'], report['source'], report['data_origin']])
    return Response(content=output.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="windscope-{delivery_date.isoformat()}.csv"'})


# Multi-stage Docker image copies the Vite build here; optional in Python-only dev.
STATIC_DIR = Path(__file__).parent / 'static'
if STATIC_DIR.exists():
    from starlette.responses import FileResponse
    app.mount('/assets', StaticFiles(directory=STATIC_DIR / 'assets'), name='assets')
    @app.get('/{path:path}', include_in_schema=False)
    async def spa(path: str):
        file = STATIC_DIR / path
        if path and file.is_file() and STATIC_DIR.resolve() in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(STATIC_DIR / 'index.html')
