"""Validate measurements without inventing hours, values or station identities."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get('AIRPREDICT_ROOT', Path(__file__).resolve().parents[2])).absolute()
FIXED_LIMA = timezone(timedelta(hours=-5))
COLUMNS = ['source', 'station', 'sensor_id', 'timestamp', 'pm25']


def load_config():
    return json.loads((ROOT / 'config/experiment.json').read_text(encoding='utf-8'))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def download_target(config, refresh=False):
    folder = ROOT / 'data/raw/openaq' / str(config['target_location_id'])
    folder.mkdir(parents=True, exist_ok=True)
    first, last = date.fromisoformat(config['target_start']), date.fromisoformat(config['target_end'])
    days = [first + timedelta(days=i) for i in range((last-first).days+1)]

    def fetch(day):
        identifier = config['target_location_id']
        path = folder / f'{day.isoformat()}.csv.gz'
        url = (f'https://openaq-data-archive.s3.amazonaws.com/records/csv.gz/locationid={identifier}'
               f'/year={day:%Y}/month={day:%m}/location-{identifier}-{day:%Y%m%d}.csv.gz')
        record = {'day': day.isoformat(), 'url': url, 'path': str(path.relative_to(ROOT))}
        for attempt in range(3):
            try:
                if path.exists() and not refresh:
                    payload = path.read_bytes()
                    record['cached'] = True
                else:
                    with urllib.request.urlopen(url, timeout=30) as response:
                        payload = response.read()
                        record['http_date'] = response.headers.get('Date')
                    # Check integrity before committing the cache file.
                    gzip.decompress(payload).decode('utf-8-sig')
                    temp = path.with_suffix('.tmp')
                    temp.write_bytes(payload)
                    temp.replace(path)
                text = gzip.decompress(payload).decode('utf-8-sig')
                rows = list(csv.DictReader(io.StringIO(text)))
                record.update(status=200, sha256=hashlib.sha256(payload).hexdigest(),
                              total_rows=len(rows), pm25_rows=sum(r.get('parameter') == 'pm25' for r in rows))
                return record
            except urllib.error.HTTPError as exc:
                record.update(status=exc.code, error=str(exc))
                if exc.code == 404:
                    return record
            except (OSError, ValueError, EOFError) as exc:
                record.update(status='error', error=str(exc))
            if attempt < 2:
                time.sleep(2 ** attempt)
        return record

    with ThreadPoolExecutor(max_workers=config['workers']) as executor:
        records = list(executor.map(fetch, days))
    manifest = {'location_id': config['target_location_id'], 'sensor_id': config['target_sensor_id'],
                'start': config['target_start'], 'end': config['target_end'], 'files': records,
                'archive_lag': '72 horas tras terminar el día local, según documentación OpenAQ'}
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = Counter(r['status'] for r in records)
    print(f'OpenAQ: {len(records)} días, estados {dict(counts)}', flush=True)
    transient = [r for r in records if r['status'] not in [200, 404]]
    if transient:
        raise RuntimeError(f'{len(transient)} descargas fallaron; se guardó el manifiesto. Reejecutar antes de entrenar.')
    return manifest


def finite_nonnegative(raw):
    try:
        value = float(str(raw).strip().replace(',', '.'))
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_oefa_hour(day, raw_time):
    raw_time = raw_time.strip()
    if raw_time == '1899-12-31':
        clock = '00:00:00'
    else:
        match = re.search(r'\d{2}:\d{2}:\d{2}', raw_time)
        if not match:
            return None
        clock = match.group()
    try:
        stamp = datetime.fromisoformat(day + 'T' + clock)
    except ValueError:
        return None
    if stamp.minute or stamp.second:
        return None
    return stamp.replace(tzinfo=FIXED_LIMA).astimezone(timezone.utc).isoformat()


def prepare_source(config):
    path = next((ROOT / 'Dataset').glob('*.csv'))
    destination = ROOT / 'data/processed/oefa_hourly.csv'
    stats_path = destination.with_suffix('.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    signature = {'size': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns,
                 'stations': config['source_stations'], 'parser_version': 1}
    if destination.exists() and stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding='utf-8'))
        if stats.get('cache_signature') == signature and stats.get('output_sha256') == digest(destination):
            return pd.read_csv(destination), stats
    records, counts = [], Counter()
    with path.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle, delimiter=';'):
            counts['source_rows_scanned'] += 1
            if row['NOMBRE_PUNTO'] not in config['source_stations']:
                continue
            if row['PERIODO'].strip().lower() != '1 hora':
                continue
            counts['candidate_hourly_rows'] += 1
            if row['UNIDAD_MEDIDA'].strip() not in ['ug/m3', 'µg/m³', 'μg/m³']:
                counts['unknown_unit'] += 1
                continue
            value = finite_nonnegative(row['PM2.5'])
            if value is None:
                counts['missing_or_invalid_pm25'] += 1
                continue
            stamp = parse_oefa_hour(row['FECHA_INICIO'].strip(), row['HORA_INICIO'])
            if stamp is None:
                counts['invalid_time'] += 1
                continue
            if row['HORA_INICIO'].strip() == '1899-12-31':
                counts['midnight_interpretation'] += 1
            records.append(['OEFA', row['NOMBRE_PUNTO'], '', stamp, value])
    frame, duplicate_stats = validate_records(pd.DataFrame(records, columns=COLUMNS))
    frame.to_csv(destination, index=False)
    stats = {'cache_signature': signature, 'source_path': str(path.relative_to(ROOT)), 'source_sha256': digest(path),
             'counts': dict(counts), 'duplicates': duplicate_stats, 'accepted': len(frame),
             'output_sha256': digest(destination),
             'assumptions': {k: v for k, v in config.items() if k.startswith('source_') and 'assumption' in k}}
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'OEFA: {len(frame)} observaciones horarias preparadas', flush=True)
    return frame, stats


def validate_records(frame):
    frame = frame.copy()
    if frame.empty:
        return frame, {'identical_duplicates': 0, 'conflicting_rows_removed': 0}
    frame['station'] = frame['station'].astype(str).str.strip()
    frame['source'] = frame['source'].astype(str).str.strip()
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True, format='mixed')
    # Conflicting observations are quarantined instead of arbitrarily averaged.
    keys = ['source', 'station', 'timestamp']
    conflict = frame.groupby(keys)['pm25'].transform('nunique').gt(1)
    conflicts = int(conflict.sum())
    frame = frame.loc[~conflict]
    before = len(frame)
    frame = frame.drop_duplicates(keys).sort_values(keys).reset_index(drop=True)
    return frame, {'identical_duplicates': before-len(frame), 'conflicting_rows_removed': conflicts}


def prepare_target(config, manifest):
    records, counts = [], Counter()
    for item in manifest['files']:
        if item['status'] != 200:
            continue
        path = ROOT / item['path']
        if digest(path) != item['sha256']:
            raise ValueError(f'Cambió un archivo desde la descarga: {path.name}')
        with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                if row.get('parameter') != 'pm25':
                    continue
                counts['pm25_rows'] += 1
                if str(row.get('location_id')) != str(config['target_location_id']) or str(row.get('sensors_id')) != str(config['target_sensor_id']):
                    counts['different_sensor_or_station'] += 1
                    continue
                if row.get('units') not in ['ug/m3', 'µg/m³', 'μg/m³']:
                    counts['unknown_unit'] += 1
                    continue
                value = finite_nonnegative(row.get('value'))
                try:
                    stamp = datetime.fromisoformat(row['datetime'])
                except (ValueError, KeyError):
                    counts['invalid_time'] += 1
                    continue
                if stamp.tzinfo is None or stamp.minute or stamp.second:
                    counts['non_hourly_or_naive_time'] += 1
                    continue
                if value is None:
                    counts['invalid_value'] += 1
                    continue
                local_day = stamp.astimezone(FIXED_LIMA).date().isoformat()
                if not config['target_start'] <= local_day <= config['target_end']:
                    counts['outside_interval'] += 1
                    continue
                records.append(['OpenAQ', str(config['target_location_id']), str(config['target_sensor_id']), stamp.isoformat(), value])
    frame, duplicates = validate_records(pd.DataFrame(records, columns=COLUMNS))
    output = ROOT / 'data/processed'
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / 'campo_marte_hourly.csv', index=False)
    stats = {'counts': dict(counts), 'duplicates': duplicates, 'accepted': len(frame),
             'output_sha256': digest(output / 'campo_marte_hourly.csv')}
    (output / 'campo_marte_hourly.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    return frame, stats
