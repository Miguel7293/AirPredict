import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import sklearn
from fastapi.testclient import TestClient
from sklearn.dummy import DummyRegressor

from airepredict.data import load_config
from airepredict.features import FEATURES
from airepredict.live import save_hours
from airepredict.maintenance import evaluate, load_policy
from airepredict.monitoring import monitor, record_forecast
from airepredict.registry import Registry
from airepredict.service import create_app


def bundle(change=0):
    model = DummyRegressor(strategy='constant', constant=change)
    model.fit(pd.DataFrame(np.zeros((2, len(FEATURES))), columns=FEATURES), [0, 0])
    return {'model': model, 'config': load_config(), 'features': FEATURES,
            'predicts': 'delta_pm25_t_plus_1', 'sklearn_version': sklearn.__version__}


@pytest.fixture
def registry(tmp_path):
    registry = Registry(tmp_path/'registry')
    identifier = registry.register(bundle(), {'trained_until': '2026-01-01', 'evaluated_until': '2026-02-01'})
    registry.activate(identifier, expected_active=None, reason='Test fixture')
    return registry


def test_candidate_cannot_activate_without_approval(registry):
    old = registry.state()['active']
    identifier = registry.register(bundle(1), {})
    with pytest.raises(ValueError, match='approved'):
        registry.activate(identifier, expected_active=old, reason='Should be rejected')
    assert registry.state()['active'] == old


def test_activation_is_compare_and_swap(registry):
    old = registry.state()['active']
    candidate = registry.register(bundle(1), {})
    registry.activate(candidate, expected_active=old, reason='Test setup', administrative=True)
    with pytest.raises(ValueError, match='concurrently'):
        registry.activate(old, expected_active=old, reason='Stale operator', administrative=True)
    assert registry.state()['active'] == candidate


def test_rollback_restores_previous_and_blocks_faulty_release(registry):
    old = registry.state()['active']
    candidate = registry.register(bundle(2), {})
    registry.activate(candidate, expected_active=old, reason='Test setup', administrative=True)
    assert registry.rollback(expected_active=candidate, mark_failed=True) == old
    assert registry.state() == {'active': old, 'previous': None}
    with pytest.raises(ValueError, match='faulty'):
        registry.validate(candidate)


def test_corrupt_artifact_never_replaces_active(registry):
    old = registry.state()['active']
    candidate = registry.register(bundle(2), {})
    (registry.root/'releases'/candidate/'model.joblib').write_bytes(b'broken')
    with pytest.raises(ValueError, match='checksum'):
        registry.activate(candidate, expected_active=old, reason='Corrupt candidate', administrative=True)
    assert registry.state()['active'] == old


def test_runtime_or_feature_mismatch_is_not_activated(registry):
    old = registry.state()['active']
    candidate = registry.register(bundle(2), {})
    with registry.connection() as connection:
        metadata = registry.manifest(candidate)
        metadata['environment']['sklearn'] = 'incompatible-version'
        connection.execute('UPDATE releases SET manifest=? WHERE id=?', (json.dumps(metadata), candidate))
        connection.commit()
    with pytest.raises(ValueError, match='runtime'):
        registry.activate(candidate, expected_active=old, reason='Mismatch', administrative=True)
    assert registry.state()['active'] == old


def test_sandbox_cannot_be_opened_as_application_registry(tmp_path):
    registry = Registry(tmp_path/'demo', sandbox=True)
    registry.event('sandbox')
    with pytest.raises(ValueError, match='environment mismatch'):
        Registry(tmp_path/'demo').history()


def test_historical_evaluation_cannot_authorize_application_promotion(registry):
    old = registry.state()['active']
    candidate = registry.register(bundle(2), {})
    with pytest.raises(ValueError, match='Historical'):
        registry.activate(candidate, expected_active=old, reason='Wrong environment', evaluation={
            'approved': True, 'candidate_id': candidate, 'champion_id': old, 'historical_demo': True})


def test_equal_model_is_rejected_by_quality_gate():
    frame = pd.DataFrame(np.zeros((168, len(FEATURES))), columns=FEATURES)
    frame['pm25_now'] = 10
    frame['y'] = 11
    frame['target_time'] = pd.date_range('2026-03-01', periods=168, freq='h', tz='UTC')
    result = evaluate(bundle(), bundle(), frame, load_policy())
    assert not result['approved'] and 'mae_improves_active' in result['reasons']


def test_service_reloads_promoted_model_and_recovers_from_corrupt_release(registry, tmp_path):
    path = tmp_path/'demo.csv'
    pd.DataFrame({'source': 'OpenAQ', 'station': '2415', 'timestamp': pd.date_range('2020-01-01', periods=4, freq='h', tz='UTC'), 'pm25': [10, 10, 10, 10]}).to_csv(path, index=False)
    old = registry.state()['active']
    with TestClient(create_app(registry=registry, demo_path=path, database=tmp_path/'live.sqlite')) as client:
        assert client.get('/api/demo').json()['model_version'] == old
        candidate = registry.register(bundle(1), {})
        registry.activate(candidate, expected_active=old, reason='Test setup', administrative=True)
        assert client.get('/api/demo').json()['model_version'] == candidate
        broken = registry.register(bundle(2), {})
        registry.activate(broken, expected_active=candidate, reason='Test setup', administrative=True)
        (registry.root/'releases'/broken/'model.joblib').write_bytes(b'broken')
        response = client.get('/api/demo')
        assert response.status_code == 200 and response.json()['model_version'] == candidate
        assert registry.state()['active'] == candidate


def test_live_monitor_rolls_back_only_when_previous_is_better(registry, tmp_path):
    old = registry.state()['active']
    bad = registry.register(bundle(10), {})
    registry.activate(bad, expected_active=old, reason='Test degradation setup', administrative=True)
    now = datetime(2026, 10, 19, 20, tzinfo=timezone.utc)
    database = tmp_path/'live.sqlite'
    actual = []
    for i in range(168):
        stamp = now-timedelta(hours=168-i)
        actual.append({'timestamp': stamp.isoformat(), 'pm25': 10, 'coverage': 100})
        observations = [{'timestamp': (stamp-timedelta(hours=j)).isoformat(), 'pm25': 10} for j in [3, 2, 1]]
        record_forecast({'is_current_forecast': True, 'model_version': bad, 'target_time_utc': stamp.isoformat(),
                         'predicted_pm25': 20, 'last_observed_pm25': 10,
                         'generated_at_utc': (stamp-timedelta(minutes=30)).isoformat()}, observations, database)
    save_hours(database, actual, load_config(), now)
    result = monitor(registry, database, now)
    assert result['status'] == 'rolled_back' and registry.state()['active'] == old


def test_retraining_failure_preserves_active(registry, monkeypatch):
    from airepredict import maintenance
    active = registry.state()['active']
    def fail_config():
        raise RuntimeError('Simulated training setup failure')
    monkeypatch.setattr(registry, 'manifest', lambda *args: fail_config())
    with pytest.raises(RuntimeError, match='Simulated'):
        maintenance.run(registry)
    assert registry.state()['active'] == active
    assert registry.history()[0]['action'] == 'retraining_failed'
