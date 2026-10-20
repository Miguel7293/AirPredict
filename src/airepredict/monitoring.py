"""Compare recorded live predictions with later observations and an older release."""
import json
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np
import pandas as pd

from .data import load_config
from .experiment import metrics, predict
from .features import make_features
from .live import DEFAULT_DATABASE, connect
from .registry import Registry


def forecast_table(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS forecasts (
       version TEXT NOT NULL, target_time TEXT NOT NULL, predicted REAL NOT NULL,
       last_pm25 REAL NOT NULL, generated_at TEXT NOT NULL, inputs TEXT NOT NULL,
       PRIMARY KEY(version,target_time))''')


def record_forecast(result, observations, database=DEFAULT_DATABASE):
    if not result.get('is_current_forecast'):
        return
    with connect(database) as connection:
        forecast_table(connection)
        # Preserve the first emitted prediction; do not rewrite it after seeing outcomes.
        connection.execute('INSERT OR IGNORE INTO forecasts VALUES (?,?,?,?,?,?)',
            (result['model_version'], result['target_time_utc'], result['predicted_pm25'],
             result['last_observed_pm25'], result['generated_at_utc'], json.dumps(observations)))


def monitor(registry=None, database=DEFAULT_DATABASE, now=None):
    registry = registry or Registry()
    state = registry.state()
    now = now or datetime.now(timezone.utc)
    if not state['active'] or not state['previous']:
        return {'status': 'skipped', 'reason': 'No active/previous release pair is available.'}
    config = load_config()
    with connect(database) as connection:
        forecast_table(connection)
        rows = connection.execute('''SELECT f.*, o.pm25 AS observed FROM forecasts f
            JOIN observations o ON o.timestamp=f.target_time AND o.sensor_id=? AND o.location_id=?
            WHERE f.version=? AND f.target_time>=? AND f.target_time<=? AND f.generated_at<f.target_time
            ORDER BY f.target_time''',
            (config['target_sensor_id'], config['target_location_id'], state['active'],
             (now-timedelta(days=14)).isoformat(), now.isoformat())).fetchall()
    if len(rows) < 50:
        return {'status': 'skipped', 'reason': 'At least 50 completed live predictions are required.', 'n': len(rows)}
    target_times = pd.to_datetime([r['target_time'] for r in rows], utc=True)
    if len(set(target_times.tz_convert('Etc/GMT+5').date)) < 7:
        return {'status': 'skipped', 'reason': 'At least seven observed days are required.', 'n': len(rows)}
    previous = joblib.load(registry.validate(state['previous']))
    inputs = []
    for row in rows:
        # Use the saved measurements as known at emission time, not corrected future inputs.
        frame = pd.DataFrame(json.loads(row['inputs'])).assign(source='OpenAQ', station=str(config['target_location_id']))
        features = make_features(frame, require_target=False)
        if len(features) != 1:
            raise ValueError('Recorded prediction does not contain a complete input window')
        inputs.append(features)
    old_predictions = predict(previous['model'], pd.concat(inputs, ignore_index=True))
    y = np.array([r['observed'] for r in rows])
    active = metrics(y, np.array([r['predicted'] for r in rows]))
    baseline = metrics(y, np.array([r['last_pm25'] for r in rows]))
    old = metrics(y, old_predictions)
    # Conservative prototype rule: both degradation vs persistence and a better fallback.
    degraded = active['mae'] > baseline['mae']*1.10 and active['rmse'] > baseline['rmse']*1.10
    fallback_better = old['mae'] < active['mae']*.98 and old['rmse'] <= active['rmse']
    report = {'status': 'observed', 'n': len(rows), 'active_id': state['active'], 'previous_id': state['previous'],
              'active': active, 'persistence': baseline, 'previous_replay': old,
              'degraded': degraded, 'fallback_better': fallback_better,
              'note': 'Prototype thresholds: +10% MAE/RMSE vs persistence and at least 2% better fallback MAE; requires future validation.'}
    if degraded and fallback_better:
        report['restored'] = registry.rollback(expected_active=state['active'], reason='Observed live degradation; compatible previous release performed better on recorded inputs', mark_failed=True)
        report['status'] = 'rolled_back'
    registry.event('monitoring', state['active'], report)
    return report
