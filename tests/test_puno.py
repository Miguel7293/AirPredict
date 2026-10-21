"""The demonstration must never impersonate observed stations or real validation."""
import json
import math
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from airepredict import puno


def payload(start=0, count=48):
    first = datetime(2026, 10, 20, tzinfo=puno.LIMA)
    return {'site_id': 'puno_city', 'is_measurement': False, 'source': 'CAMS global forecast via Open-Meteo',
            'timezone': 'America/Lima', 'units': 'µg/m³', 'latitude': -15.8, 'longitude': -70,
            'history': [{'timestamp': (first+timedelta(hours=i)).isoformat(), 'pm25': 20+3*math.sin(i*.2)}
                        for i in range(start, start+count)]}


def initial(root):
    puno.ingest(root, payload(), now=datetime(2026, 10, 20, tzinfo=puno.LIMA))
    return puno.train(root)


@pytest.mark.parametrize('change', [
    {'is_measurement': True}, {'site_id': 'another_station'}, {'timezone': 'UTC'}, {'units': 'AQI'},
    {'latitude': -12}, {'source': 'sensor'},
])
def test_source_contract_rejects_mixed_sources(change):
    with pytest.raises(ValueError):
        puno.validate_payload({**payload(), **change})


def test_invalid_values_and_duplicate_hours_are_rejected():
    data = payload()
    data['history'][0]['pm25'] = float('nan')
    with pytest.raises(ValueError): puno.validate_payload(data)
    data = payload()
    data['history'][1]['timestamp'] = data['history'][0]['timestamp']
    with pytest.raises(ValueError): puno.validate_payload(data)


def test_forecast_revisions_are_not_new_examples(tmp_path):
    initial(tmp_path)
    original = json.loads((tmp_path/'data/processed/puno_forecasts.json').read_text(encoding='utf-8'))
    data = payload()
    data['history'][0]['pm25'] += 10
    result = puno.ingest(tmp_path, data)
    assert result['accepted_new_targets'] == 0
    current = json.loads((tmp_path/'data/processed/puno_forecasts.json').read_text(encoding='utf-8'))
    assert current['rows'] == original['rows']
    assert current['latest_curve'][0]['pm25'] != current['rows'][0]['pm25']
    assert puno.train(tmp_path)['status'] == 'skipped'


def test_temporal_evaluation_and_explicit_experimental_contract(tmp_path):
    initial(tmp_path)
    data = puno.view(tmp_path, datetime(2026, 10, 20, 3, tzinfo=puno.LIMA))
    r = data['report']
    assert r['train_end'] < r['validation_end'] < r['test_start'] <= r['test_end']
    assert r['train_n'] + r['validation_n'] + r['test']['n'] == 45
    assert r['small_sample'] and not data['is_measurement']
    assert not data['is_current_forecast'] and not data['health_alerts_enabled']
    assert data['predicted_pm25'] >= 0
    stale = puno.view(tmp_path, datetime(2026, 10, 20, 4, tzinfo=puno.LIMA))
    assert not stale['available'] and stale['predicted_pm25'] is None


def test_new_windows_promotion_and_restore(tmp_path):
    first = initial(tmp_path)['active']
    puno.ingest(tmp_path, payload(48, 200))
    second = puno.train(tmp_path)
    assert second['status'] == 'promoted'
    state = puno.registry(tmp_path)
    assert state['previous'] == first and state['active'] != first
    report = puno.load_model(state['active'], tmp_path)['report']
    assert report['test_start'] > puno.load_model(first, tmp_path)['report']['test_end']
    assert puno.rollback(tmp_path)['active'] == first


def test_worse_candidate_is_rejected_and_window_consumed(tmp_path, monkeypatch):
    active = initial(tmp_path)['active']
    puno.ingest(tmp_path, payload(48, 200))
    numbers = iter([10., 2., 1.])
    def scores(y, prediction):
        value = next(numbers)
        return {'n': len(y), 'mae': value, 'rmse': value, 'r2': 0.}
    monkeypatch.setattr(puno, 'metrics', scores)
    assert puno.train(tmp_path)['status'] == 'rejected'
    assert puno.registry(tmp_path)['active'] == active
    assert puno.train(tmp_path)['status'] == 'skipped'


def test_corrupt_active_uses_verified_previous(tmp_path):
    first = initial(tmp_path)['active']
    puno.ingest(tmp_path, payload(48, 200))
    second = puno.train(tmp_path)['active']
    (tmp_path/f'models/puno_experimental/{second}.joblib').write_bytes(b'broken')
    result = puno.view(tmp_path)
    assert result['local_recovery'] and result['model_version'] == first
    (tmp_path/f'models/puno_experimental/{first}.joblib').write_bytes(b'broken')
    with pytest.raises(HTTPException) as exception:
        puno.view(tmp_path)
    assert exception.value.status_code == 503


def test_public_route_does_not_add_a_measured_station():
    from airepredict.service import create_app
    with TestClient(create_app()) as client:
        assert client.get('/puno').status_code == 200
        data = client.get('/api/puno/experiment').json()
        assert data['mode'] == 'experimental' and data['site_id'] == 'puno_city'
        assert data['is_measurement'] is False and data['health_alerts_enabled'] is False
        assert all(s['name'] != 'Puno' for s in client.get('/api/stations').json()['stations'])


def test_refresh_renews_inference_without_writing_or_training(tmp_path, monkeypatch):
    initial(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    calls = []
    monkeypatch.setattr(puno, 'fetch_payload', lambda: calls.append(True) or payload())
    cache = puno.SourceCache()
    now = datetime(2026, 10, 20, 4, tzinfo=puno.LIMA)
    fresh = puno.view(tmp_path, now, refresh_source=True, source_cache=cache)
    assert fresh['available'] and fresh['source_refresh']['status'] == 'downloaded'
    assert fresh['target_time'] > now.isoformat()
    cached = puno.view(tmp_path, now+timedelta(minutes=1), refresh_source=True, source_cache=cache)
    assert len(calls) == 1 and cached['source_refresh']['status'] == 'cached'
    assert cached['fetched_at'] == fresh['fetched_at']
    assert cached['model_version'] == fresh['model_version']
    assert cached['report'] == fresh['report'] and not cached['health_alerts_enabled']
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before
    projected = puno.view(tmp_path, now, source_cache=cache)
    assert projected['fetched_at'] == fresh['fetched_at']


@pytest.mark.parametrize('invalid', [None, {'site_id': 'other'}, {'is_measurement': True}])
def test_refresh_failure_preserves_stale_state_and_backs_off(tmp_path, monkeypatch, invalid):
    initial(tmp_path)
    calls = []
    def download():
        calls.append(True)
        if invalid is None:
            raise OSError('Provider unavailable')
        return {**payload(), **invalid}
    monkeypatch.setattr(puno, 'fetch_payload', download)
    cache = puno.SourceCache()
    now = datetime(2026, 10, 20, 4, tzinfo=puno.LIMA)
    failed = puno.view(tmp_path, now, refresh_source=True, source_cache=cache)
    assert not failed['available'] and failed['predicted_pm25'] is None
    assert failed['source_refresh']['status'] == 'failed'
    retry = puno.view(tmp_path, now, refresh_source=True, source_cache=cache)
    assert retry['source_refresh']['status'] == 'retry_later' and len(calls) == 1
    assert failed['fetched_at'] == retry['fetched_at']


def test_cached_curve_expires_even_when_provider_fails(tmp_path, monkeypatch):
    initial(tmp_path)
    clock = [0.]
    monkeypatch.setattr(puno.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(puno, 'fetch_payload', payload)
    cache = puno.SourceCache()
    now = datetime(2026, 10, 20, 4, tzinfo=puno.LIMA)
    fresh = puno.view(tmp_path, now, refresh_source=True, source_cache=cache)
    clock[0] = 601.
    def fail(): raise OSError('Unavailable')
    monkeypatch.setattr(puno, 'fetch_payload', fail)
    still_valid = puno.view(tmp_path, now+timedelta(minutes=11), refresh_source=True, source_cache=cache)
    assert still_valid['available'] and still_valid['source_refresh']['status'] == 'failed'
    clock[0] = 12000.
    stale = puno.view(tmp_path, now+timedelta(hours=4), refresh_source=True, source_cache=cache)
    assert stale['fetched_at'] == fresh['fetched_at']
    assert not stale['available'] and stale['predicted_pm25'] is None


def test_concurrent_refresh_reuses_snapshot_and_missing_future_stays_unavailable(tmp_path, monkeypatch):
    initial(tmp_path)
    cache = puno.SourceCache()
    monkeypatch.setattr(puno, 'fetch_payload', lambda: pytest.fail('Concurrent request must not call provider'))
    cache.lock.acquire()
    try:
        data = puno.view(tmp_path, datetime(2026, 10, 20, 4, tzinfo=puno.LIMA),
                         refresh_source=True, source_cache=cache)
        assert data['source_refresh']['status'] == 'refreshing' and not data['available']
    finally:
        cache.lock.release()
    monkeypatch.setattr(puno, 'fetch_payload', payload)
    data = puno.view(tmp_path, datetime(2026, 10, 23, tzinfo=puno.LIMA),
                     refresh_source=True, source_cache=cache)
    assert data['source_refresh']['status'] == 'downloaded'
    assert not data['available'] and data['predicted_pm25'] is None


def test_public_refresh_route_shares_cache_without_touching_mlops(monkeypatch):
    from airepredict.service import create_app
    calls = []
    monkeypatch.setattr(puno, 'fetch_payload', lambda: calls.append(True) or payload())
    with TestClient(create_app()) as client:
        before = client.get('/api/puno/experiment').json()
        assert not calls
        refreshed = client.get('/api/puno/experiment?refresh=true').json()
        assert refreshed['source_refresh']['status'] == 'downloaded' and len(calls) == 1
        cached = client.get('/api/puno/experiment?refresh=true').json()
        assert cached['source_refresh']['status'] == 'cached' and len(calls) == 1
        assert refreshed['model_version'] == before['model_version']
        assert refreshed['mlops'] == before['mlops'] and refreshed['report'] == before['report']
        assert refreshed['is_measurement'] is False and not refreshed['health_alerts_enabled']
