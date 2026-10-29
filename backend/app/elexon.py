"""Asynchronous Elexon BMRS stream API client with bounded retries and disk cache."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
BASE_URL = 'https://data.elexon.co.uk/bmrs/api/v1'
CACHE_ROOT = Path(os.getenv('WINDSCOPE_CACHE_DIR', '/tmp/windscope-cache'))
CACHE_TTL_SECONDS = int(os.getenv('WINDSCOPE_CACHE_TTL', '86400'))
ARCHIVE_DIR = Path(os.getenv('WINDSCOPE_ARCHIVE_DIR', str(Path(__file__).parent / 'data')))
SEMAPHORE = asyncio.Semaphore(3)


class UpstreamError(Exception):
    pass


async def _request(path: str, params: dict[str, str]) -> list[dict]:
    """Stream endpoints respond with JSON arrays. Persist raw payload with date ranges."""
    cache_key = hashlib.sha256(json.dumps([path, sorted(params.items())]).encode()).hexdigest()
    cache_path = CACHE_ROOT / f'{cache_key}.json'
    if cache_path.exists():
        import time
        if time.time() - cache_path.stat().st_mtime < CACHE_TTL_SECONDS:
            return json.loads(cache_path.read_text())

    async with SEMAPHORE:
        async with httpx.AsyncClient(timeout=45.0, headers={'Accept': 'application/json', 'User-Agent': 'WindScope/1.0 (assessment project)'}) as client:
            for attempt in range(3):
                try:
                    response = await client.get(f'{BASE_URL}{path}', params=params)
                    if response.status_code == 429 or response.status_code >= 500:
                        raise httpx.HTTPStatusError('Elexon temporarily unavailable', request=response.request, response=response)
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, dict):
                        data = data.get('data', [])
                    if not isinstance(data, list):
                        raise UpstreamError('Unexpected Elexon response schema')
                    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
                    tmp = cache_path.with_name(cache_path.name + '.' + uuid4().hex + '.tmp')
                    tmp.write_text(json.dumps(data))
                    tmp.replace(cache_path)
                    return data
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if attempt == 2 or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429):
                        logger.warning('Elexon fetch failed: %s', exc)
                        raise UpstreamError('Elexon data could not be retrieved. Please retry or use explicit demo mode.') from exc
                    await asyncio.sleep(1.5 * (2 ** attempt))
                except (ValueError, TypeError) as exc:
                    raise UpstreamError('Elexon returned invalid JSON') from exc
    raise UpstreamError('Elexon unavailable')


async def fetch_delivery_data(delivery: date) -> tuple[list[dict], list[dict]]:
    """Get forecast revisions across decision day and one prior day; actuals on delivery day."""
    snapshot = ARCHIVE_DIR / f'{delivery.isoformat()}.json'
    if snapshot.is_file() and os.getenv('WINDSCOPE_IGNORE_ARCHIVE', '0') != '1':
        try:
            archived = json.loads(snapshot.read_text())
            if archived.get('delivery_date') != delivery.isoformat():
                raise ValueError('Date mismatch in archived data')
            if not isinstance(archived.get('forecasts'), list) or not isinstance(archived.get('actuals'), list):
                raise ValueError('Invalid archived data')
            return archived['forecasts'], archived['actuals']
        except (OSError, ValueError, TypeError) as exc:
            raise UpstreamError(f'Corrupt archived Elexon snapshot for {delivery.isoformat()}') from exc
    decision = delivery - timedelta(days=1)
    # Include the preceding publication day: an early decision may rely on an earlier revision.
    lookback = decision - timedelta(days=1)
    publication_from = f'{lookback.isoformat()}T00:00:00Z'
    publication_to = f'{delivery.isoformat()}T00:00:00Z'
    # Query through the following date; domain strictly filters target UTC intervals.
    # This accommodates APIs treating the upper date bound as exclusive.
    # Split the two-day publication lookback into one-day requests. This avoids
    # exceeding dataset-specific maximum time-window constraints upstream.
    forecast_first_day = {
        'publishDateTimeFrom': publication_from,
        'publishDateTimeTo': f'{decision.isoformat()}T00:00:00Z',
    }
    forecast_second_day = {
        'publishDateTimeFrom': f'{decision.isoformat()}T00:00:00Z',
        'publishDateTimeTo': publication_to,
    }
    actual_query = {
        'settlementDateFrom': delivery.isoformat(),
        'settlementDateTo': (delivery + timedelta(days=1)).isoformat(),
    }
    first, second, actuals = await asyncio.gather(
        _request('/datasets/WINDFOR/stream', forecast_first_day),
        _request('/datasets/WINDFOR/stream', forecast_second_day),
        _request('/datasets/FUELHH/stream', actual_query),
    )
    forecasts = first + second
    return forecasts, actuals
