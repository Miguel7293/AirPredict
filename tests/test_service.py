from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from airepredict.data import load_config
from airepredict.features import make_features
from airepredict.live import save_hours
from airepredict.service import Predictor, create_app


class FlatChange:
    def predict(self, frame):
        return np.zeros(len(frame))


def test_delayed_measurements_remain_visible_without_current_forecast(tmp_path, engine):
    database = tmp_path/'observations.sqlite'
    save_hours(database, [{'timestamp': '2020-01-01T01:00:00+00:00', 'pm25': 12.5, 'coverage': 100}],
               load_config(), datetime.now(timezone.utc))
    with TestClient(create_app(engine, database=database)) as client:
        measured = client.get('/api/observations').json()
        assert len(measured['history']) == 1
        assert measured['history'][0]['pm25'] == 12.5
        assert measured['fresh_for_next_hour'] is False
        assert client.get('/api/forecast').status_code == 409


@pytest.fixture
def engine():
    instance = Predictor.__new__(Predictor)
    instance.bundle = {'model': FlatChange()}
    instance.version = 'test-version'
    instance.config = load_config()
    return instance


@pytest.fixture
def observations():
    return [{'timestamp': f'2026-10-19T{hour}:00:00+00:00', 'pm25': value}
            for hour, value in [(14, 10), (15, 12), (16, 11)]]


def test_inference_never_requires_next_hour_outcome():
    frame = pd.DataFrame({'source': 'OpenAQ', 'station': '2415', 'timestamp': pd.date_range('2020-01-01', periods=3, freq='h', tz='UTC'), 'pm25': [4, 5, 6]})
    assert make_features(frame).empty
    inputs = make_features(frame, require_target=False)
    assert len(inputs) == 1 and inputs.iloc[0]['pm25_now'] == 6 and pd.isna(inputs.iloc[0]['y'])


def test_live_forecast_rejects_past_horizon(engine, observations):
    with pytest.raises(ValueError, match='stale'):
        engine.forecast(observations, 2415, mode='live', now=datetime(2026, 10, 19, 17, 1, tzinfo=timezone.utc))


def test_current_forecast_has_future_horizon(engine, observations):
    now = datetime(2026, 10, 19, 16, 30, tzinfo=timezone.utc)
    forecast = engine.forecast(observations, 2415, mode='live', now=now)
    assert forecast['is_current_forecast'] and forecast['predicted_pm25'] == 11
    assert datetime.fromisoformat(forecast['target_time_utc']) > now


def test_future_measurement_is_rejected(engine, observations):
    with pytest.raises(ValueError, match='Future observations'):
        engine.forecast(observations, 2415, now=datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc))


@pytest.fixture
def client(tmp_path, engine):
    times = pd.date_range('2020-01-01', periods=6, freq='h', tz='UTC')
    path = tmp_path / 'demo.csv'
    pd.DataFrame({'source': 'OpenAQ', 'station': '2415', 'timestamp': times, 'pm25': [10, 12, 11, 14, 13, 15]}).to_csv(path, index=False)
    with TestClient(create_app(engine, database=tmp_path/'live.sqlite', demo_path=path)) as connection:
        yield connection


def test_historical_demo_is_labelled_and_works_without_credentials(client, monkeypatch):
    monkeypatch.delenv('OPENAQ_API_KEY', raising=False)
    response = client.get('/api/demo')
    assert response.status_code == 200
    data = response.json()
    assert data['mode'] == 'historical' and not data['is_current_forecast']
    assert data['predicted_pm25'] == 15 and len(data['history']) == 6
    assert client.get('/api/status').json()['api_key_configured'] is False


def test_api_refuses_other_stations_and_missing_hours(client):
    body = {'location_id': 999, 'observations': [{'timestamp': f'2020-01-01T0{h}:00:00Z', 'pm25': 10} for h in [1, 2, 3]]}
    assert client.post('/api/predict', json=body).status_code == 422
    body['location_id'] = 2415
    body['observations'][-1]['timestamp'] = '2020-01-01T05:00:00Z'
    assert client.post('/api/predict', json=body).status_code == 422


def test_api_rejects_negative_measurements_and_naive_timestamps(client):
    body = {'observations': [{'timestamp': f'2020-01-01T0{h}:00:00Z', 'pm25': 10} for h in [1, 2, 3]]}
    body['observations'][0]['pm25'] = -1
    assert client.post('/api/predict', json=body).status_code == 422
    body['observations'][0]['pm25'] = 1
    body['observations'][0]['timestamp'] = '2020-01-01T01:00:00'
    assert client.post('/api/predict', json=body).status_code == 422


def test_empty_live_store_never_falls_back_to_historical_demo(client):
    response = client.get('/api/forecast')
    assert response.status_code == 409


def test_stale_live_store_is_rejected(tmp_path, engine):
    database = tmp_path/'live.sqlite'
    now = datetime.now(timezone.utc)
    start = (now-timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
    save_hours(database, [{'timestamp': (start+timedelta(hours=i)).isoformat(), 'pm25': 10, 'coverage': 100} for i in range(3)], load_config(), now)
    with TestClient(create_app(engine, database=database)) as connection:
        response = connection.get('/api/forecast')
        assert response.status_code == 409 and 'stale' in response.json()['detail']


def test_page_assets_and_health(client):
    assert 'EXPLORACIÓN GEOGRÁFICA' in client.get('/').text
    assert 'Usar mi ubicación' in client.get('/').text
    assert 'geolocation=(self)' in client.get('/').headers['permissions-policy']
    assert client.get('/static/nearby.js').status_code==200
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/health').json()['status'] == 'ok'
