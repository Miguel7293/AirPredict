"""Read-only source audit; outputs derived summaries, never changes the CSV."""
import csv
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = next((ROOT / 'Dataset').glob('*.csv'))
MISSING = {'', '-', 'NA', 'N/A', 'NULL', 'NAN'}


def numeric(value):
    try:
        n = float(value.strip().replace(',', '.'))
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def run():
    stations = {}
    dates = Counter()
    cutoffs = Counter()
    count = 0
    with SOURCE.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        columns = reader.fieldnames
        for row in reader:
            count += 1
            key = '|'.join(row[k] for k in ['NOMBRE_PUNTO', 'ESTE', 'NORTE', 'ZONA'])
            if key not in stations:
                stations[key] = {
                    'metadata': {k: row[k] for k in ['NOMBRE_PUNTO', 'ESTE', 'NORTE', 'ZONA', 'DATUM', 'ALTITUD', 'DEPARTAMENTO', 'PROVINCIA', 'DISTRITO', 'DESCRIPCION_UBICACION']},
                    'rows': 0, 'dates': Counter(), 'pm25_periods': Counter(),
                    'pm25_units': Counter(), 'pm25_non_numeric': Counter(),
                    'pm25_numeric': 0, 'pm25_negative': 0,
                    'pm25_hourly_times': [], 'pm25_hourly_values': [],
                    'pm25_samples': [], 'pm25_dates': Counter(),
                    'pm25_hour_strings': Counter(),
                }
            station = stations[key]
            station['rows'] += 1
            date = row['FECHA_INICIO'].strip()
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
                station['dates'][date] += 1
                dates[date] += 1
            cutoffs[row['FECHA_CORTE']] += 1
            raw = row['PM2.5'].strip()
            if raw.upper() in MISSING:
                continue
            station['pm25_periods'][row['PERIODO']] += 1
            station['pm25_units'][row['UNIDAD_MEDIDA']] += 1
            value = numeric(raw)
            if value is None:
                station['pm25_non_numeric'][raw] += 1
                continue
            station['pm25_numeric'] += 1
            station['pm25_negative'] += value < 0
            station['pm25_dates'][date] += 1
            if len(station['pm25_samples']) < 2:
                station['pm25_samples'].append({k: row[k] for k in ['FECHA_INICIO', 'HORA_INICIO', 'FECHA_FIN', 'HORA_FIN', 'PERIODO', 'UNIDAD_MEDIDA', 'PM2.5']})
            if row['PERIODO'].strip().lower() == '1 hora' and value >= 0:
                raw_time = row['HORA_INICIO'].strip()
                station['pm25_hour_strings'][raw_time] += 1
                match = re.search(r'\d{2}:\d{2}:\d{2}', raw_time)
                # Excel serial-time epoch without a time component represents midnight.
                # Keep this explicit assumption in the output for review.
                time = match.group() if match else ('00:00:00' if raw_time == '1899-12-31' else raw_time)
                try:
                    stamp = datetime.fromisoformat(date + 'T' + time)
                except ValueError:
                    continue
                station['pm25_hourly_times'].append(stamp)
                station['pm25_hourly_values'].append(value)
    result = {'source': str(SOURCE), 'bytes': SOURCE.stat().st_size,
              'rows': count, 'columns': columns, 'date_min': min(dates),
              'date_max': max(dates), 'cutoffs': cutoffs, 'stations': []}
    for station in stations.values():
        times = station.pop('pm25_hourly_times')
        values = station.pop('pm25_hourly_values')
        unique = sorted(set(times))
        gaps = Counter(int((b-a).total_seconds()) for a, b in zip(unique, unique[1:]))
        longest = current = 1 if unique else 0
        for a, b in zip(unique, unique[1:]):
            current = current + 1 if (b-a).total_seconds() == 3600 else 1
            longest = max(longest, current)
        by_time = {}
        for stamp, value in zip(times, values):
            by_time.setdefault(stamp, set()).add(value)
        coverage = ((unique[-1]-unique[0]).total_seconds()/3600+1) if unique else 0
        station['pm25_hourly'] = {
            'rows_nonnegative': len(times), 'unique_timestamps': len(unique),
            'duplicate_timestamps': len(times)-len(unique),
            'conflicting_timestamps': sum(len(v)>1 for v in by_time.values()),
            'min_local_unconfirmed': str(unique[0]) if unique else None,
            'max_local_unconfirmed': str(unique[-1]) if unique else None,
            'longest_consecutive_hours': longest,
            'consecutive_one_hour_pairs': gaps[3600],
            'coverage_of_full_span': len(unique)/coverage if coverage else None,
            'largest_gap_hours': max(gaps)/3600 if gaps else None,
            'gap_seconds_counts': dict(gaps.most_common(8)),
            'min_value': min(values) if values else None,
            'max_value': max(values) if values else None,
        }
        for name in ['dates', 'pm25_dates']:
            counter = station.pop(name)
            valid = sorted(k for k in counter if re.fullmatch(r'\d{4}-\d{2}-\d{2}', k))
            station[name + '_range'] = [valid[0], valid[-1]] if valid else None
        result['stations'].append(station)
    result['stations'].sort(key=lambda s: s['pm25_numeric'], reverse=True)
    output = ROOT / 'audit'
    output.mkdir(exist_ok=True)
    target = output / 'historico_oefa_resumen.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ['columns', 'stations']}, ensure_ascii=False))
    for s in result['stations']:
        print(json.dumps({'station': s['metadata'], 'pm25_numeric': s['pm25_numeric'], 'pm25_periods': s['pm25_periods'], 'units': s['pm25_units'], 'dates': s['dates_range'], 'hourly': s['pm25_hourly'], 'non_numeric': s['pm25_non_numeric']}, ensure_ascii=False))


if __name__ == '__main__':
    run()
