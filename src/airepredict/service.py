"""A local experimental prediction service with explicit historical/live modes."""
import json
import os
import threading
import hmac
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .data import ROOT, digest, load_config
from .experiment import predict
from .features import FEATURES, make_features
from .live import DEFAULT_DATABASE, read_hours, retraining_readiness, utc_stamp
from .registry import Registry


class ModelExecutionError(RuntimeError):
    pass


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    timestamp: AwareDatetime
    pm25: float = Field(ge=0)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    location_id: int = 2415
    observations: list[Observation] = Field(min_length=3, max_length=3)

    @model_validator(mode='after')
    def validate_hours(self):
        times = sorted(o.timestamp.astimezone(timezone.utc) for o in self.observations)
        if any(t.minute or t.second or t.microsecond for t in times):
            raise ValueError('Observations must use exact hourly timestamps.')
        if any(b-a != timedelta(hours=1) for a, b in zip(times, times[1:])):
            raise ValueError('Three consecutive, distinct hourly observations are required.')
        return self


class Predictor:
    def __init__(self, model_path=None):
        config = load_config()
        path = Path(model_path or ROOT / f'models/{config["experiment_id"]}/combinado.joblib')
        if not path.exists():
            raise FileNotFoundError('Experimental model is missing. Run the experiment first.')
        self.bundle = joblib.load(path)
        self.version = digest(path)[:16]
        self.config = config
        if self.bundle['features'] != FEATURES or self.bundle.get('predicts') != 'delta_pm25_t_plus_1':
            raise ValueError('The model feature or output contract is incompatible.')
        model_config = self.bundle['config']
        if (model_config['target_location_id'], model_config['target_sensor_id']) != (config['target_location_id'], config['target_sensor_id']):
            raise ValueError('The model belongs to a different station or sensor.')

    def forecast(self, observations, location_id, mode='historical', now=None):
        if location_id != self.config['target_location_id']:
            raise ValueError('This model only supports Campo de Marte, location 2415.')
        request = PredictionRequest(location_id=location_id, observations=observations)
        frame = pd.DataFrame([{'source': 'OpenAQ', 'station': str(location_id), 'timestamp': o.timestamp, 'pm25': o.pm25} for o in request.observations])
        inputs = make_features(frame, require_target=False)
        if len(inputs) != 1:
            raise ValueError('The latest three hours do not form a complete feature window.')
        latest = inputs.iloc[0]['timestamp'].to_pydatetime()
        now = now or datetime.now(timezone.utc)
        horizon = latest+timedelta(hours=1)
        if latest > now:
            raise ValueError('Future observations cannot be used as measured inputs.')
        if mode == 'live' and horizon <= now:
            raise ValueError('The latest measurements are stale: their next-hour horizon has already passed.')
        try:
            value = float(predict(self.bundle['model'], inputs)[0])
            if not np.isfinite(value):
                raise ValueError('Non-finite model output')
        except Exception as exc:
            raise ModelExecutionError('The model could not produce a valid prediction.') from exc
        return {'location_id': location_id, 'station': self.config['target_name'], 'mode': mode,
                'model_status': 'experimental', 'model_version': self.version, 'units': 'µg/m³',
                'last_observation_utc': latest.isoformat(), 'target_time_utc': horizon.isoformat(),
                'last_observed_pm25': float(inputs.iloc[0]['pm25_now']), 'predicted_pm25': value,
                'data_age_hours': (now-latest).total_seconds()/3600,
                'is_current_forecast': mode == 'live', 'generated_at_utc': now.isoformat()}


def create_app(predictor=None, database=DEFAULT_DATABASE, demo_path=None, registry=None):
    from .operations import Jobs
    jobs = Jobs()
    @asynccontextmanager
    async def lifespan(app):
        jobs.recover()
        yield
    app = FastAPI(title='AirePredict Perú', version='0.3.0', lifespan=lifespan,
                  description='Experimental next-hour PM2.5 forecasts for Campo de Marte. Historical demonstrations are explicitly labelled.')
    state = {'predictor': predictor, 'error': None}
    injected = predictor is not None
    registry = registry or Registry()
    lock = threading.RLock()
    demo_path = Path(demo_path or ROOT / 'data/processed/campo_marte_hourly.csv')
    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')
    bearer = HTTPBearer(auto_error=False)

    def administrator(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        expected = os.environ.get('AIRPREDICT_ADMIN_TOKEN', '')
        if len(expected) < 32:
            raise HTTPException(503, 'Administrative access is not configured.')
        if not credentials or not hmac.compare_digest(credentials.credentials, expected):
            raise HTTPException(401, 'Administrative authentication required.', headers={'WWW-Authenticate': 'Bearer'})

    @app.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def model():
        if injected:
            return state['predictor']
        with lock:
            desired = registry.state()['active']
            if state['predictor'] is not None and (desired is None or state['predictor'].version == desired):
                return state['predictor']
            try:
                path = registry.validate(desired) if desired else None
                current = Predictor(path)
                if desired:
                    current.version = desired
                state['predictor'], state['error'] = current, None
            except Exception:
                if desired:
                    try:
                        restored = registry.rollback(expected_active=desired, reason='Service could not load activated model', mark_failed=True)
                        current = Predictor(registry.validate(restored))
                        current.version = restored
                        state['predictor'], state['error'] = current, None
                        return current
                    except Exception:
                        pass
                state['error'] = 'No compatible model is available.'
                raise HTTPException(503, state['error']) from None
            return state['predictor']

    def forecast(observations, location_id, mode):
        current = model()
        try:
            return current.forecast(observations, location_id, mode=mode)
        except ModelExecutionError:
            if not injected:
                try:
                    registry.rollback(expected_active=current.version, reason='Model failed while producing a prediction', mark_failed=True)
                    return model().forecast(observations, location_id, mode=mode)
                except Exception:
                    pass
            raise HTTPException(503, 'Prediction failed; no compatible fallback is available.') from None

    @app.get('/', include_in_schema=False)
    def home():
        return FileResponse(static / 'index.html')

    @app.get('/sw.js', include_in_schema=False)
    def service_worker():
        return FileResponse(static/'sw.js', media_type='application/javascript', headers={'Cache-Control': 'no-cache'})

    @app.get('/widget', include_in_schema=False)
    def widget_page():
        return FileResponse(static/'widget.html')

    @app.get('/admin', include_in_schema=False)
    def admin_page():
        return FileResponse(static/'admin.html')

    @app.get('/api/model')
    def model_information():
        config = load_config()
        path = ROOT/f'reports/{config["experiment_id"]}/resultados.json'
        report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        active = registry.state()['active']
        manifest = registry.manifest(active) if active else None
        return {'version': model().version, 'status': 'experimental', 'features': FEATURES,
                'initial_experiment': report.get('summary', {}),
                'active_metadata': manifest['metadata'] if manifest else {},
                'limitations': ['Modest improvement; historical confidence interval includes zero.',
                                'Historical evaluation covers 37.5% of test hours.',
                                'Forecast is experimental and does not replace official measurements.']}

    @app.get('/api/admin/overview', dependencies=[Depends(administrator)])
    def administrative_overview():
        return {'state': registry.state(), 'events': registry.history(40),
                'jobs': [jobs.read(path.stem) for path in sorted(jobs.folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]]}

    @app.post('/api/admin/jobs/{action}', status_code=202, dependencies=[Depends(administrator)])
    def start_job(action: str):
        if os.environ.get('STATE_SYNC_REPOSITORY'):
            raise HTTPException(409, 'This deployment is read-only. Run maintenance from the authenticated GitHub Actions workflows.')
        if action not in ['ingest', 'retrain', 'monitor', 'backup', 'rollback', 'demo']:
            raise HTTPException(404, 'Unknown operation')
        try:
            return jobs.start(action)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get('/api/admin/jobs/{identifier}', dependencies=[Depends(administrator)])
    def read_job(identifier: str):
        try:
            return jobs.read(identifier)
        except FileNotFoundError:
            raise HTTPException(404, 'Unknown job') from None

    @app.get('/api/admin/backups/{identifier}', dependencies=[Depends(administrator)])
    def download_backup(identifier: str):
        if not identifier.endswith('.zip') or '/' in identifier or '\\' in identifier or '..' in identifier:
            raise HTTPException(404, 'Unknown backup')
        path = ROOT/'backups'/identifier
        if not path.is_file():
            raise HTTPException(404, 'Unknown backup')
        return FileResponse(path, filename=path.name)

    @app.get('/ready')
    def readiness():
        return {'status': 'ready', 'model_version': model().version, 'commit': os.environ.get('RENDER_GIT_COMMIT', os.environ.get('APP_COMMIT', 'local'))}

    @app.get('/api/operations')
    def public_operations():
        path = ROOT/'state.json'
        published = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        local_state = registry.state()
        expected_active = published.get('registry', {}).get('active')
        return {'managed_by_github': bool(os.environ.get('STATE_SYNC_REPOSITORY')),
                'workflows_url': 'https://github.com/Miguel7293/AirPredict/actions',
                'published_state': published, 'state': local_state,
                'local_recovery': bool(expected_active and local_state['active'] != expected_active)}

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'airepredict'}

    @app.get('/api/status')
    def status():
        try:
            current = model()
            version, available = current.version, True
        except HTTPException:
            version, available = None, False
        hours = read_hours(database, limit=72)
        latest = hours[-1]['timestamp'] if hours else None
        now = datetime.now(timezone.utc)
        fresh = bool(latest and utc_stamp(latest) <= now < utc_stamp(latest)+timedelta(hours=1))
        return {'station': load_config()['target_name'], 'location_id': 2415, 'model_available': available,
                'model_version': version, 'model_status': 'experimental', 'api_key_configured': bool(os.environ.get('OPENAQ_API_KEY', '').strip()),
                'historical_demo_available': demo_path.exists(), 'latest_live_observation_utc': latest,
                'live_data_fresh': fresh, 'retraining': retraining_readiness(database)}

    @app.post('/api/predict')
    def manual_prediction(request: PredictionRequest):
        try:
            return forecast([o.model_dump() for o in request.observations], request.location_id, mode='historical')
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get('/api/demo')
    def demo():
        if not demo_path.exists():
            raise HTTPException(503, 'Historical demonstration data is missing. Run preparation first.')
        frame = pd.read_csv(demo_path)
        frame = frame.loc[frame['station'].astype(str) == '2415']
        frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True)
        features = make_features(frame, require_target=False)
        if features.empty:
            raise HTTPException(503, 'No complete historical window is available.')
        latest = features['timestamp'].max()
        selected = frame.loc[frame['timestamp'].isin([latest-pd.Timedelta(hours=i) for i in [2, 1, 0]])].sort_values('timestamp')
        observations = [{'timestamp': r.timestamp.to_pydatetime(), 'pm25': float(r.pm25)} for r in selected.itertuples()]
        result = forecast(observations, 2415, mode='historical')
        tail = frame.loc[(frame['timestamp'] <= latest) & (frame['timestamp'] > latest-pd.Timedelta(hours=24))].sort_values('timestamp')
        result['history'] = [{'timestamp': r.timestamp.isoformat(), 'pm25': float(r.pm25)} for r in tail.itertuples()]
        return result

    @app.get('/api/forecast')
    def current_forecast():
        hours = read_hours(database, limit=3)
        if len(hours) < 3:
            raise HTTPException(409, 'Three ingested hourly measurements are not yet available.')
        try:
            observations = [{'timestamp': row['timestamp'], 'pm25': row['pm25']} for row in hours]
            result = forecast(observations, 2415, mode='live')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        result['history'] = read_hours(database, limit=24)
        from .monitoring import record_forecast
        record_forecast(result, observations, database)
        return result

    return app


app = create_app()
