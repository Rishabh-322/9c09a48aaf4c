import os
os.environ['WINDSCOPE_DATA_MODE'] = 'demo'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_sample_day():
    assert client.get('/api/health').json()['mode'] == 'demo'
    response = client.get('/api/analysis', params={'delivery_date': '2026-01-16', 'cutoff': '12:00'})
    assert response.status_code == 200
    data = response.json()
    assert 'synthetic' in data['source']
    assert data['decision_date'] == '2026-01-15'
    assert len(data['periods']) == 24
    assert data['statistics']['period_minutes'] == 60
    assert data['data_origin'] == 'synthetic'
    assert data['decision_brief']['status'] in ('complete', 'partial')


def test_unsupported_delivery_rejected():
    assert client.get('/api/analysis?delivery_date=2026-03-01').status_code == 422


def test_csv_and_month():
    assert client.get('/api/export').headers['content-type'].startswith('text/csv')
    monthly = client.get('/api/month').json()
    assert len(monthly['days']) == 31
    assert monthly['statistics']['n'] > 0


def test_compare_endpoint_and_validation():
    response = client.get('/api/compare', params={'delivery_date':'2026-01-16','early':'09:00','late':'18:00'})
    assert response.status_code == 200
    data = response.json()
    assert data['early']['cutoff_uk'] == '09:00'
    assert data['late']['cutoff_uk'] == '18:00'
    assert data['revised_hours'] > 0
    assert data['common_comparison']['matched_hours'] > 0
    assert client.get('/api/compare', params={'early':'18:00','late':'09:00'}).status_code == 422


def test_data_provenance_does_not_claim_fresh_upstream_for_archives(monkeypatch, tmp_path):
    from datetime import date
    from app import main as module
    monkeypatch.setattr(module, 'MODE', 'live')
    monkeypatch.setattr(module, 'ARCHIVE_DIR', tmp_path)
    day = date(2026, 1, 16)
    assert module.origin_for(day) == 'api_or_cache'
    (tmp_path / '2026-01-16.json').write_text('{}')
    assert module.origin_for(day) == 'local_snapshot'
    monkeypatch.setenv('WINDSCOPE_IGNORE_ARCHIVE', '1')
    assert module.origin_for(day) == 'api_or_cache'
