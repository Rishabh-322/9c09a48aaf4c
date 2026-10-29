from datetime import date
from unittest.mock import AsyncMock
import pytest
from app import elexon


@pytest.mark.asyncio
async def test_fetches_earlier_publications_and_delivery_actuals(monkeypatch, tmp_path):
    monkeypatch.setattr(elexon, 'ARCHIVE_DIR', tmp_path)
    mocked = AsyncMock(side_effect=lambda path, params: [])
    monkeypatch.setattr(elexon, '_request', mocked)
    forecasts, actuals = await elexon.fetch_delivery_data(date(2026, 1, 16))
    assert (forecasts, actuals) == ([], [])
    path, params = mocked.call_args_list[0].args
    assert path == '/datasets/WINDFOR/stream'
    assert params['publishDateTimeFrom'] == '2026-01-14T00:00:00Z'
    assert params['publishDateTimeTo'] == '2026-01-15T00:00:00Z'
    path, params = mocked.call_args_list[1].args
    assert params['publishDateTimeFrom'] == '2026-01-15T00:00:00Z'
    assert params['publishDateTimeTo'] == '2026-01-16T00:00:00Z'
    path, params = mocked.call_args_list[2].args
    assert path == '/datasets/FUELHH/stream'
    assert params['settlementDateFrom'] == '2026-01-16'
    assert params['settlementDateTo'] == '2026-01-17'

