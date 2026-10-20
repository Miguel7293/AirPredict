"""Run maintenance in GitHub Actions; publish public air-quality state only."""
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

seed = Path.cwd()
root = Path(os.environ['AIRPREDICT_ROOT'])
root.mkdir(parents=True, exist_ok=True)
for relative in ['config', 'reports/oefa_campo_marte_v1', 'data/processed', 'models/oefa_campo_marte_v1', 'models/station_2402', 'models/station_2351', 'reports/station_2402', 'reports/station_2351']:
    for path in (seed/relative).glob('*'):
        if path.is_file():
            target = root/path.relative_to(seed)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or relative == 'config':
                shutil.copy2(path, target)
shutil.copy2(seed/'requirements.txt', root/'requirements.txt')

from airepredict.registry import Registry, initialize, now_string
from airepredict.operations import maintenance_lock, backup
from airepredict.maintenance import run, demo
from airepredict.monitoring import monitor
from airepredict.live import ingest
from airepredict.data import load_config, download_target, prepare_target, validate_records


def archive_ingestion():
    """Delayed public archive never feeds the live measurement store."""
    import pandas as pd
    config = load_config()
    last = (datetime.now(timezone.utc)-timedelta(days=4)).date()
    path = root/'data/processed/campo_marte_hourly.csv'
    existing = pd.read_csv(path)
    first = max(pd.to_datetime(existing['timestamp'], utc=True).max().date()-timedelta(days=2), last-timedelta(days=14))
    config = {**config, 'target_start': first.isoformat(), 'target_end': last.isoformat()}
    manifest = download_target(config, refresh=True)
    downloaded, _ = prepare_target(config, manifest)
    existing['timestamp'] = pd.to_datetime(existing['timestamp'], utc=True)
    existing['station'] = existing['station'].astype(str)
    downloaded['station'] = downloaded['station'].astype(str)
    combined = pd.concat([existing, downloaded], ignore_index=True).drop_duplicates(['source', 'station', 'timestamp'], keep='last')
    combined, duplicates = validate_records(combined)
    combined.to_csv(path, index=False)
    return {'mode': 'historical_archive', 'live_api_configured': False, 'accepted_rows': len(downloaded),
            'total_rows': len(combined), 'duplicates': duplicates, 'archive_end': last.isoformat(),
            'note': 'Delayed archive; no observations written to the live store.'}


def main():
    action = sys.argv[1]
    registry = Registry()
    initialize(registry)
    try:
        with maintenance_lock():
            base = os.environ.get('APP_BASE_URL', '').rstrip('/')
            if base.startswith('https://'):
                import urllib.request
                try:
                    with urllib.request.urlopen(base+'/api/operations', timeout=20) as response:
                        projection = json.load(response)
                    state = registry.state()
                    if (projection.get('local_recovery') and state['previous']
                            and projection['published_state']['registry']['active'] == state['active']
                            and projection['state']['active'] == state['previous']):
                        registry.rollback(expected_active=state['active'], reason='Persist recovery reported by the read-only web projection', mark_failed=True)
                except (OSError, ValueError, KeyError):
                    pass
            if action == 'ingest':
                result = ingest() if os.environ.get('OPENAQ_API_KEY', '').strip() else archive_ingestion()
                if os.environ.get('OPENAQ_API_KEY', '').strip():
                    result.update(mode='authenticated_openaq', live_api_configured=True)
                    from airepredict.live import read_hours, DEFAULT_DATABASE
                    from airepredict.service import Predictor
                    from airepredict.monitoring import record_forecast
                    observations = read_hours(DEFAULT_DATABASE, limit=3)
                    if len(observations) == 3:
                        try:
                            active = registry.state()['active']
                            predictor = Predictor(registry.validate(active))
                            predictor.version = active
                            inputs = [{'timestamp': r['timestamp'], 'pm25': r['pm25']} for r in observations]
                            forecast = predictor.forecast(inputs, load_config()['target_location_id'], mode='live')
                            record_forecast(forecast, inputs, DEFAULT_DATABASE)
                            result['issued_forecast'] = forecast
                        except ValueError:
                            result['forecast_status'] = 'No fresh consecutive input window'
            elif action == 'retrain':
                result = run(registry)
            elif action == 'monitor':
                result = monitor(registry)
            elif action == 'rollback':
                result = {'restored': registry.rollback(reason='Authenticated GitHub Actions operator')}
            elif action == 'backup':
                result = backup()
            elif action == 'demo':
                report = demo()
                result = {'historical_simulation': True, 'application_registry_modified': False,
                          'first_training': report['first_training']['status'], 'second_training': report['repeated_training']['status'],
                          'restored': report['restored'] == report['initial_baseline']}
            elif action == 'verify':
                result = {'retraining': run(registry), 'monitoring': monitor(registry), 'backup': backup()}
                historical = demo()
                result['historical_simulation'] = {'application_registry_modified': False,
                    'first_training': historical['first_training']['status'],
                    'second_training': historical['repeated_training']['status'],
                    'restored': historical['restored'] == historical['initial_baseline']}
            else:
                raise ValueError('Unsupported maintenance action')
            # The general daily model is frozen. Only explicitly configured
            # live-capable stations participate in automated maintenance.
            if action in ['ingest', 'retrain', 'monitor', 'verify']:
                from airepredict.stations import STATIONS, station_config, station_registry, station_database
                from airepredict.atlas import station_forecast
                station_results={}
                for station in STATIONS[1:]:
                    identifier=station['id']; config=station_config(identifier)
                    local_registry=station_registry(identifier)
                    initialize(local_registry)
                    try:
                        if action=='ingest':
                            if os.environ.get('OPENAQ_API_KEY','').strip():
                                value=ingest(path=station_database(identifier),config=config)
                                try: station_forecast(identifier,'live'); value['forecast_issued']=True
                                except Exception: value['forecast_issued']=False
                            else: value={'status':'skipped','reason':'OpenAQ credential not configured; no fabricated live data'}
                        elif action=='retrain': value=run(local_registry)
                        elif action=='monitor': value=monitor(local_registry,database=station_database(identifier))
                        else: value={'retraining':run(local_registry),'monitoring':monitor(local_registry,database=station_database(identifier))}
                        station_results[str(identifier)]=value
                    except Exception as error:
                        local_registry.event('station_operation_failed',local_registry.state()['active'],{'error_type':type(error).__name__,'action':action})
                        station_results[str(identifier)]={'status':'failed','error_type':type(error).__name__,'active_preserved':local_registry.state()['active']}
                result['station_results']=station_results
        report = {'action': action, 'status': 'completed', 'completed_at': now_string(), 'result': result,
                  'code_commit': os.environ.get('GITHUB_SHA', 'local'), 'registry': registry.state(),
                  'live_api_configured': bool(os.environ.get('OPENAQ_API_KEY', '').strip())}
    except Exception as exc:
        report = {'action': action, 'status': 'failed', 'completed_at': now_string(),
                  'error_type': type(exc).__name__, 'registry': registry.state()}
        raise
    finally:
        (root/'state.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (seed/'artifacts').mkdir(exist_ok=True)
        (seed/f'artifacts/{action}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'action': action, 'registry': report['registry']}))


if __name__ == '__main__':
    main()
