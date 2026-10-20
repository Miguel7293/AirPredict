"""Validated, paginated OpenAQ ingestion with persistent hourly observations."""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import ROOT, finite_nonnegative, load_config

DEFAULT_DATABASE = ROOT / 'data/live/airepredict.sqlite'


@contextmanager
def connect(path=DEFAULT_DATABASE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('''CREATE TABLE IF NOT EXISTS observations (
        sensor_id INTEGER NOT NULL, timestamp TEXT NOT NULL, pm25 REAL NOT NULL,
        location_id INTEGER NOT NULL, coverage REAL NOT NULL, fetched_at TEXT NOT NULL,
        PRIMARY KEY (sensor_id, timestamp))''')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def utc_stamp(text):
    stamp = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('A timestamp must specify its timezone')
    return stamp.astimezone(timezone.utc)


def normalize_hour(item, now):
    parameter = item.get('parameter') or {}
    if parameter.get('name') != 'pm25' or parameter.get('units') not in ['µg/m³', 'μg/m³', 'ug/m3']:
        return None, 'wrong_parameter_or_unit'
    period = item.get('period') or {}
    if period.get('interval') != '01:00:00':
        return None, 'non_hourly_interval'
    if (item.get('flagInfo') or {}).get('hasFlags'):
        return None, 'provider_quality_flag'
    value = finite_nonnegative(item.get('value'))
    if value is None:
        return None, 'invalid_value'
    coverage = finite_nonnegative((item.get('coverage') or {}).get('percentComplete'))
    if coverage is None or not 75 <= coverage <= 100:
        return None, 'insufficient_or_unknown_coverage'
    try:
        start = utc_stamp(period['datetimeFrom']['utc'])
        end = utc_stamp(period['datetimeTo']['utc'])
    except (KeyError, TypeError, ValueError):
        return None, 'invalid_timestamp'
    if end-start != timedelta(hours=1) or end.minute or end.second or end.microsecond:
        return None, 'invalid_hour_boundaries'
    if end > now:
        return None, 'unfinished_or_future_hour'
    return {'timestamp': end.isoformat(), 'pm25': value, 'coverage': coverage}, None


def save_hours(path, hours, config, now):
    inserted = updated = unchanged = 0
    with connect(path) as connection:
        for hour in hours:
            previous = connection.execute('SELECT pm25, coverage FROM observations WHERE sensor_id=? AND timestamp=?',
                                          (config['target_sensor_id'], hour['timestamp'])).fetchone()
            if previous is None:
                inserted += 1
            elif previous['pm25'] != hour['pm25'] or previous['coverage'] != hour['coverage']:
                updated += 1
            else:
                unchanged += 1
            connection.execute('''INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sensor_id,timestamp) DO UPDATE SET pm25=excluded.pm25,
                coverage=excluded.coverage, fetched_at=excluded.fetched_at''',
                (config['target_sensor_id'], hour['timestamp'], hour['pm25'], config['target_location_id'], hour['coverage'], now.isoformat()))
    return {'inserted': inserted, 'updated': updated, 'unchanged': unchanged}


def read_hours(path=DEFAULT_DATABASE, limit=72, config=None):
    if not Path(path).exists():
        return []
    config = config or load_config()
    with connect(path) as connection:
        rows = connection.execute('''SELECT timestamp, pm25, coverage FROM observations
            WHERE sensor_id=? AND location_id=? ORDER BY timestamp DESC LIMIT ?''',
            (config['target_sensor_id'], config['target_location_id'], limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def api_get(path, params, key):
    url = 'https://api.openaq.org/v3/'+path
    if params:
        url += '?'+urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'X-API-Key': key, 'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in [401, 403]:
                raise RuntimeError('OpenAQ rejected the configured credential; check OPENAQ_API_KEY.') from None
            if exc.code not in [429, 500, 502, 503, 504] or attempt == 2:
                raise RuntimeError(f'OpenAQ request failed with HTTP {exc.code}.') from None
        except OSError:
            if attempt == 2:
                raise RuntimeError('OpenAQ could not be reached; no observations were written.') from None
        time.sleep(2 ** attempt)


def ingest(path=DEFAULT_DATABASE, now=None, get=None, config=None):
    now = now or datetime.now(timezone.utc)
    key = os.environ.get('OPENAQ_API_KEY', '').strip()
    if not key:
        raise RuntimeError('OPENAQ_API_KEY is not configured. Historical demonstration remains available.')
    get = get or api_get
    config = config or load_config()
    # Confirm location/sensor identity before fetching values.
    location = get(f'locations/{config["target_location_id"]}', {}, key)
    records = location.get('results') or []
    if len(records) != 1 or records[0].get('id') != config['target_location_id']:
        raise RuntimeError('Unexpected OpenAQ location metadata.')
    sensors = records[0].get('sensors') or []
    if not any(s.get('id') == config['target_sensor_id'] and (s.get('parameter') or {}).get('name') == 'pm25' for s in sensors):
        raise RuntimeError('The configured PM2.5 sensor is not listed at the configured location.')
    # Revisit 72 hours to receive late data and corrections, not just the latest item.
    start = now-timedelta(hours=72)
    accepted, rejected = [], Counter()
    seen_pages = set()
    for page in range(1, 101):
        payload = get(f'sensors/{config["target_sensor_id"]}/hours',
                      {'datetime_from': start.isoformat(), 'datetime_to': now.isoformat(), 'limit': 1000, 'page': page}, key)
        items = payload.get('results')
        if not isinstance(items, list):
            raise RuntimeError('Unexpected OpenAQ measurements response; no observations were written.')
        signature = json.dumps(items, sort_keys=True)
        if items and signature in seen_pages:
            raise RuntimeError('OpenAQ repeated a pagination page; no observations were written.')
        seen_pages.add(signature)
        for item in items:
            hour, error = normalize_hour(item, now)
            if error:
                rejected[error] += 1
            elif utc_stamp(hour['timestamp']) < start:
                rejected['outside_requested_window'] += 1
            else:
                accepted.append(hour)
        if len(items) < 1000:
            break
    else:
        raise RuntimeError('Pagination limit exceeded; no observations were written.')
    # Conflicts within one fetch are quarantined rather than resolved by page order.
    by_time = {}
    conflicts = set()
    for hour in accepted:
        old = by_time.get(hour['timestamp'])
        if old and (old['pm25'], old['coverage']) != (hour['pm25'], hour['coverage']):
            conflicts.add(hour['timestamp'])
        by_time[hour['timestamp']] = hour
    for stamp in conflicts:
        del by_time[stamp]
    rejected['conflicting_timestamps'] = len(conflicts)
    saved = save_hours(path, list(by_time.values()), config, now)
    report = {'fetched_at_utc': now.isoformat(), 'location_id': config['target_location_id'],
              'sensor_id': config['target_sensor_id'], 'accepted_unique_hours': len(by_time),
              'rejected': dict(rejected), **saved}
    report_path = Path(path).parent / ('last_ingestion.json' if config['target_location_id']==2415 else f'last_ingestion_{config["target_location_id"]}.json')
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def retraining_readiness(path=DEFAULT_DATABASE):
    """Readiness is a data signal, never approval or automatic model promotion."""
    import pandas as pd
    from .features import make_features
    config = load_config()
    hours = read_hours(path, limit=100000)
    if not hours:
        return {'ready': False, 'new_examples': 0, 'reason': 'No live observations have been ingested.'}
    frame = pd.DataFrame(hours).assign(source='OpenAQ', station=str(config['target_location_id']))
    features = make_features(frame)
    old_test_end = pd.Timestamp(config['target_end'], tz='Etc/GMT+5')+pd.Timedelta(days=1)
    fresh = features.loc[features['target_time'] >= old_test_end.tz_convert('UTC')]
    count = len(fresh)
    return {'ready': count >= 168, 'new_examples': count, 'minimum_new_examples': 168,
            'reason': 'New data threshold met; a separate temporal evaluation is still required.' if count >= 168 else 'Not enough new complete examples after the original test period.',
            'automatic_promotion': False}
