"""Collect public Explorer metadata, compare coordinates, and probe public archives."""
import csv
import gzip
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(os.environ['TEMP']) / 'codex-air-audit-deps'))
from pyproj import Geod, Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit'
OUT.mkdir(exist_ok=True)


def location(identifier):
    url = f'https://explore.openaq.org/locations/{identifier}'
    try:
        response = urllib.request.urlopen(url, timeout=25)
        html = response.read().decode('utf-8')
        start = html.find(f'id:{identifier},name:')
        if start < 0:
            return {'id': identifier, 'url': url, 'error': 'No metadata in public page'}
        raw = html[start:].split('</script>')[0]
        def capture(pattern):
            match = re.search(pattern, raw)
            return match.group(1) if match else None
        data = {
            'id': identifier, 'url': url, 'response_date': response.headers.get('Date'),
            'name': capture(r'^id:\d+,name:"([^"]+)"'),
            'provider': capture(r'provider:.*?name:"([^"]+)"'),
            'timezone': capture(r'timezone:"([^"]+)"'),
            'latitude': float(capture(r'latitude:([\d.-]+)')),
            'longitude': float(capture(r'longitude:([\d.-]+)')),
            'datetime_first_utc': capture(r'datetimeFirst:.*?utc:"([^"]+)"'),
            'datetime_last_utc': capture(r'datetimeLast:.*?utc:"([^"]+)"'),
            'datetime_last_local': capture(r'datetimeLast:.*?local:"([^"]+)"'),
            'pm25_sensors': [{'id': int(i), 'name': name, 'units': units} for i, name, units in re.findall(r'id:(\d+),name:"(pm25 [^"]+)",parameter:.*?units:"([^"]+)"', raw)],
            'raw_public_metadata': raw,
        }
        return data
    except Exception as exc:
        return {'id': identifier, 'url': url, 'error': str(exc)}


def archive_probe(pair):
    identifier, day = pair
    y, m, d = day.split('-')
    m, d = m.zfill(2), d.zfill(2)
    url = f'https://openaq-data-archive.s3.amazonaws.com/records/csv.gz/locationid={identifier}/year={y}/month={m}/location-{identifier}-{y}{m}{d}.csv.gz'
    result = {'id': identifier, 'day': day, 'url': url}
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            text = gzip.decompress(response.read()).decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        pm25 = [r for r in rows if r.get('parameter') == 'pm25']
        result.update(status=200, columns=reader.fieldnames, rows=len(rows),
                      parameters=dict(Counter(r.get('parameter') for r in rows)),
                      pm25_rows=len(pm25), pm25_sample=pm25[:3])
        (OUT / f'openaq_{identifier}_{y}{m}{d}.csv').write_text(text, encoding='utf-8')
    except urllib.error.HTTPError as exc:
        result.update(status=exc.code, error=exc.read().decode('utf-8', errors='replace')[:500])
    except Exception as exc:
        result['error'] = str(exc)
    return result


def run():
    ids = list(range(2578954, 2578991)) + [2402, 2351, 2415]
    with ThreadPoolExecutor(max_workers=3) as executor:
        locations = list(executor.map(location, ids))
    local = json.loads((OUT / 'historico_oefa_resumen.json').read_text(encoding='utf-8'))
    geod = Geod(ellps='WGS84')
    oefa = [p for p in locations if not p.get('error') and 'Fiscalizaci' in p['provider']]
    matches = []
    for station in local['stations']:
        meta = station['metadata']
        lon, lat = Transformer.from_crs(32700 + int(meta['ZONA']), 4326, always_xy=True).transform(float(meta['ESTE']), float(meta['NORTE']))
        distances = [(abs(geod.inv(lon, lat, p['longitude'], p['latitude'])[2]), p) for p in oefa]
        distance, closest = min(distances, key=lambda p: p[0])
        matches.append({'local_station': meta['NOMBRE_PUNTO'], 'local_coordinates': {'latitude': lat, 'longitude': lon},
                        'local_zone': meta['ZONA'], 'nearest_openaq_id': closest['id'], 'nearest_openaq_name': closest['name'],
                        'distance_m': distance, 'coordinate_match_under_1m': distance < 1,
                        'pm25_numeric_local': station['pm25_numeric'],
                        'pm25_sensors_openaq': closest['pm25_sensors']})
    report = {'audit_date_local': '2026-10-19', 'method': 'Public Explorer HTML metadata; known regional ID range is a candidate inventory, not an exhaustive API catalogue.',
              'locations': locations, 'coordinate_matches': matches,
              'api_probe': {'url': 'https://api.openaq.org/v3/locations/2578972', 'status': 401, 'authenticated': False},
              'metadata_scope': 'datetimeLast is for the location, not necessarily the PM2.5 sensor.'}
    (OUT / 'openaq_metadatos_y_cruce.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for p in locations:
        if not p.get('error'):
            print(json.dumps({k: v for k, v in p.items() if k != 'raw_public_metadata'}, ensure_ascii=False))
    print('MATCHES', json.dumps([m for m in matches if m['distance_m'] < 100], ensure_ascii=False))
    probes = [(2402, d) for d in ['2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15']]
    probes += [(i, '2025-12-03') for i in [2578976, 2578979]]
    with ThreadPoolExecutor(max_workers=3) as executor:
        archives = list(executor.map(archive_probe, probes))
    (OUT / 'openaq_archivo_muestras.json').write_text(json.dumps(archives, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ARCHIVES', json.dumps(archives, ensure_ascii=False))
    probes = [(i, f'2026-10-{day:02d}') for i in [2402, 2351, 2415] for day in range(9, 16)]
    probes += [(i, '2022-10-15') for i in [2402, 2351, 2415]]
    probes += [(i, '2026-10-15') for i in [2578976, 2578979]]
    with ThreadPoolExecutor(max_workers=3) as executor:
        recent = list(executor.map(archive_probe, probes))
    (OUT / 'openaq_muestras_recientes.json').write_text(json.dumps(recent, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run()
