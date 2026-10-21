"""Isolated experimental surrogate of CAMS forecasts, never local measurements."""
import hashlib
import json
import math
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
from fastapi import HTTPException
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import ROOT

SOURCE_URL = 'https://api-aire-puno.onrender.com/api/puno/forecast'
SOURCE = 'CAMS global vía API Aire Puno / Open-Meteo'
LIMA = timezone(timedelta(hours=-5))
NOTE = ('Modelo experimental de Puno entrenado para reproducir estimaciones de CAMS. '
        'No utiliza mediciones locales ni demuestra precisión frente al aire real. '
        'No activa alertas de salud ni notificaciones de estaciones reales.')


def stamp(value):
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return date.replace(tzinfo=LIMA) if date.tzinfo is None else date.astimezone(LIMA)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def storage(root=ROOT):
    return Path(root)/'models/puno_experimental'


def seed_path(relative, root=ROOT):
    path = Path(root)/relative
    if path.exists():
        return path
    return Path(os.environ.get('AIRPREDICT_SEED', Path(__file__).resolve().parents[2]))/relative


def validate_payload(payload, issued=None):
    if (payload.get('site_id') != 'puno_city' or payload.get('is_measurement') is not False
            or payload.get('timezone') != 'America/Lima'
            or payload.get('units') not in ['µg/m³', 'μg/m³']
            or 'CAMS' not in payload.get('source', '')
            or abs(float(payload.get('latitude', 0)) + 15.8) > .2
            or abs(float(payload.get('longitude', 0)) + 70) > .2):
        raise ValueError('La fuente no cumple el contrato experimental de Puno.')
    issued = issued or datetime.now(timezone.utc).isoformat()
    rows = []
    for row in payload.get('history', []):
        time = stamp(row['timestamp'])
        value = row['pm25']
        if (isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or not 0 <= value <= 3000
                or time.minute or time.second):
            raise ValueError('Valor o fecha no válido en la fuente de Puno.')
        rows.append({'timestamp': time.isoformat(), 'pm25': float(value), 'first_seen_at': issued})
    rows.sort(key=lambda row: row['timestamp'])
    if len(rows) < 12 or len({r['timestamp'] for r in rows}) != len(rows):
        raise ValueError('La serie debe contener horas distintas y suficientes.')
    return rows


def ingest(root=ROOT, payload=None, now=None):
    now = now or datetime.now(timezone.utc)
    if payload is None:
        request = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'AirePredict-Puno-experiment'})
        with urllib.request.urlopen(request, timeout=65) as response:
            data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError('Respuesta de Puno demasiado grande.')
        payload = json.loads(data)
    rows = validate_payload(payload, now.isoformat())
    path = Path(root)/'data/processed/puno_forecasts.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'rows': []}
    merged = {r['timestamp']: r for r in previous['rows']}
    accepted = 0
    for row in rows:
        # Revisions of a forecast are not new training examples. Preserve provenance.
        if row['timestamp'] not in merged:
            merged[row['timestamp']] = row
            accepted += 1
    value = {'source': SOURCE, 'is_measurement': False, 'fetched_at': now.isoformat(),
             'latest_curve': rows, 'rows': sorted(merged.values(), key=lambda r: r['timestamp'])}
    write(path, value)
    return {'accepted_new_targets': accepted, 'total_targets': len(merged), 'is_measurement': False}


def examples(rows):
    result = []
    for i in range(3, len(rows)):
        window = rows[i-3:i+1]
        times = [stamp(r['timestamp']) for r in window]
        if any(b-a != timedelta(hours=1) for a, b in zip(times, times[1:])):
            continue
        a, b, c = [r['pm25'] for r in window[:3]]
        hour = times[-1].hour
        result.append({'timestamp': rows[i]['timestamp'],
                       'x': [c, c-b, b-a, math.sin(hour*math.pi/12), math.cos(hour*math.pi/12)],
                       'y': rows[i]['pm25'], 'baseline': c})
    return result


def metrics(y, values):
    values = np.maximum(0, values)
    return {'n': len(y), 'mae': float(mean_absolute_error(y, values)),
            'rmse': float(math.sqrt(mean_squared_error(y, values))),
            'r2': float(r2_score(y, values)) if len(y) > 1 and np.var(y) > 0 else None}


def registry(root=ROOT, use_seed=True):
    path = seed_path('models/puno_experimental/registry.json', root) if use_seed else storage(root)/'registry.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'active': None, 'previous': None, 'events': []}


def load_model(version, root=ROOT):
    if not version or len(version) != 16 or any(c not in '0123456789abcdef' for c in version):
        raise ValueError('Versión experimental no válida.')
    path = seed_path(f'models/puno_experimental/{version}.joblib', root)
    if hashlib.sha256(path.read_bytes()).hexdigest()[:16] != version:
        raise ValueError('El modelo experimental no supera la verificación de integridad.')
    return joblib.load(path)


def rollback(root=ROOT):
    state = registry(root, use_seed=False)
    if not state['previous']:
        return {'status': 'skipped', 'reason': 'No hay una versión previa compatible.'}
    load_model(state['previous'], root)
    state['active'], state['previous'] = state['previous'], state['active']
    state['events'].append({'action': 'rollback', 'at': datetime.now(timezone.utc).isoformat(), 'active': state['active']})
    write(storage(root)/'registry.json', state)
    return {'status': 'restored', 'active': state['active']}


def train(root=ROOT):
    dataset = json.loads((Path(root)/'data/processed/puno_forecasts.json').read_text(encoding='utf-8'))
    records = examples(dataset['rows'])
    state = registry(root, use_seed=False)
    new = [r for r in records if r['timestamp'] > state.get('evaluated_through', '')]
    if state['active'] and len(new) < 168:
        result = {'status': 'skipped', 'new_targets': len(new), 'minimum_new_targets': 168,
                  'reason': 'Se conserva el modelo activo hasta reunir 168 horas objetivo nuevas.'}
        state['last_attempt'] = result
        write(storage(root)/'registry.json', state)
        return result
    if len(records) < 30:
        raise ValueError('No hay al menos 30 ejemplos horarios consecutivos para la demostración.')
    # Select hyperparameters on validation, never on the final test window.
    split1, split2 = int(len(records)*.6), int(len(records)*.8)
    if state['active']:
        split2 = len(records)-max(24, int(len(new)*.2))
        split1 = int(split2*.75)
    fitting, validation, test = records[:split1], records[split1:split2], records[split2:]
    if state['active'] and test[0]['timestamp'] <= state.get('evaluated_through', ''):
        return {'status': 'skipped', 'reason': 'La evaluación necesita un periodo nuevo sin reutilizar.'}
    x = lambda rows: np.array([r['x'] for r in rows])
    y = lambda rows: np.array([r['y'] for r in rows])
    options = []
    for alpha in [.1, 1., 10.]:
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        model.fit(x(fitting), y(fitting))
        options.append((mean_absolute_error(y(validation), np.maximum(0, model.predict(x(validation)))), alpha, model))
    _, alpha, model = min(options, key=lambda option: option[0])
    candidate = metrics(y(test), model.predict(x(test)))
    baseline = metrics(y(test), [r['baseline'] for r in test])
    incumbent = metrics(y(test), load_model(state['active'], root)['model'].predict(x(test))) if state['active'] else None
    accepted = incumbent is None or (candidate['mae'] < incumbent['mae']*.99
                                    and candidate['mae'] <= baseline['mae']
                                    and candidate['rmse'] <= incumbent['rmse'])
    report = {'source': SOURCE, 'is_measurement': False, 'scope': 'Reproducción experimental de la curva CAMS; sin validación local',
              'algorithm': 'StandardScaler + Ridge', 'alpha': alpha, 'train_n': len(fitting),
              'validation_n': len(validation), 'test': candidate, 'baseline': baseline,
              'incumbent_on_same_test': incumbent, 'train_end': fitting[-1]['timestamp'],
              'validation_end': validation[-1]['timestamp'], 'test_start': test[0]['timestamp'],
              'test_end': test[-1]['timestamp'], 'fitted_at': datetime.now(timezone.utc).isoformat(),
              'small_sample': len(records) < 168, 'note': NOTE}
    report['training_origin'] = 'Curvas de pronóstico publicadas por la API; no observaciones. El arranque puede incluir horas futuras ya estimadas por CAMS.'
    bundle = {'model': model, 'report': report}
    folder = storage(root)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder/'candidate.tmp'
    joblib.dump(bundle, temporary)
    version = hashlib.sha256(temporary.read_bytes()).hexdigest()[:16]
    os.replace(temporary, folder/f'{version}.joblib')
    write(folder/f'{version}.json', report)
    if accepted:
        state['previous'], state['active'] = state['active'], version
    state['evaluated_through'] = test[-1]['timestamp']
    result = {'status': 'promoted' if accepted else 'rejected', 'candidate': version,
              'active': state['active'], 'test': candidate, 'baseline': baseline,
              'initial_demo': incumbent is None}
    state['last_attempt'] = result
    state['events'].append({**result, 'at': report['fitted_at']})
    write(folder/'registry.json', state)
    return result


def view(root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    state = registry(root)
    try:
        try:
            bundle = load_model(state['active'], root)
            recovery = False
        except (ValueError, OSError):
            bundle = load_model(state['previous'], root)
            recovery = True
        dataset = json.loads(seed_path('data/processed/puno_forecasts.json', root).read_text(encoding='utf-8'))
        curve = dataset['latest_curve']
        windows = examples(curve)
        future = [r for r in windows if stamp(r['timestamp']) > now]
        available = (now-stamp(dataset['fetched_at'])).total_seconds() <= 10800 and bool(future)
        first = future[0] if available else None
        value = float(max(0, bundle['model'].predict([first['x']])[0])) if first else None
        if value is not None and not math.isfinite(value):
            raise ValueError('Predicción experimental no válida.')
        return {'site_id': 'puno_city', 'name': 'Puno · modelo experimental', 'latitude': -15.84, 'longitude': -70.02,
                'mode': 'experimental', 'is_measurement': False, 'is_current_forecast': False,
                'available': available, 'predicted_pm25': value, 'units': 'µg/m³',
                'target_time': first['timestamp'] if first else None, 'source_reference_pm25': first['y'] if first else None,
                'source': SOURCE, 'source_url': SOURCE_URL, 'fetched_at': dataset['fetched_at'],
                'history': curve, 'model_version': state['previous'] if recovery else state['active'],
                'local_recovery': recovery, 'report': bundle['report'], 'mlops': state,
                'note': NOTE, 'health_alerts_enabled': False}
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise HTTPException(503, 'El experimento de Puno no está disponible; las estaciones reales siguen funcionando.') from error


def maintain(root=ROOT, action='ingest'):
    if action == 'rollback':
        return rollback(root)
    result = {'ingestion': ingest(root)}
    if action == 'retrain' or not registry(root, use_seed=False)['active']:
        result['training'] = train(root)
    return result


def install(app):
    @app.get('/api/puno/experiment')
    def experiment():
        return view()
