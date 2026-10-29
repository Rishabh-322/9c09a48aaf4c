from datetime import date
import json
import pytest
from app import elexon


@pytest.mark.asyncio
async def test_genuine_snapshot_skips_network(monkeypatch, tmp_path):
    monkeypatch.setattr(elexon, 'ARCHIVE_DIR', tmp_path)
    monkeypatch.delenv('WINDSCOPE_IGNORE_ARCHIVE', raising=False)
    body = {'delivery_date': '2026-01-16', 'source': 'Elexon BMRS', 'forecasts': [{'generation': 1}], 'actuals': [{'generation': 2}]}
    (tmp_path / '2026-01-16.json').write_text(json.dumps(body))
    async def fail_request(*args, **kwargs):
        raise AssertionError('HTTP should not be called for archived day')
    monkeypatch.setattr(elexon, '_request', fail_request)
    f, a = await elexon.fetch_delivery_data(date(2026, 1, 16))
    assert f == [{'generation': 1}]
    assert a == [{'generation': 2}]


@pytest.mark.asyncio
async def test_corrupt_snapshot_does_not_silently_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(elexon, 'ARCHIVE_DIR', tmp_path)
    monkeypatch.delenv('WINDSCOPE_IGNORE_ARCHIVE', raising=False)
    (tmp_path / '2026-01-16.json').write_text('bad json')
    with pytest.raises(elexon.UpstreamError, match='Corrupt archived'):
        await elexon.fetch_delivery_data(date(2026, 1, 16))
