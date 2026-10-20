from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from airepredict.data import load_config
from airepredict.live import ingest, normalize_hour, read_hours, save_hours

NOW = datetime(2026, 10, 19, 17, 30, tzinfo=timezone.utc)


def measurement(end='2026-10-19T17:00:00Z', value=12, coverage=100):
    end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
    return {'value': value, 'parameter': {'name': 'pm25', 'units': 'µg/m³'},
            'flagInfo': {'hasFlags': False}, 'period': {'interval': '01:00:00',
            'datetimeFrom': {'utc': (end_time-timedelta(hours=1)).isoformat()}, 'datetimeTo': {'utc': end}},
            'coverage': {'percentComplete': coverage}}


def test_coverage_flags_and_unfinished_hours_are_rejected():
    assert normalize_hour(measurement(coverage=74), NOW)[1] == 'insufficient_or_unknown_coverage'
    flagged = measurement()
    flagged['flagInfo']['hasFlags'] = True
    assert normalize_hour(flagged, NOW)[1] == 'provider_quality_flag'
    assert normalize_hour(measurement(end='2026-10-19T18:00:00Z'), NOW)[1] == 'unfinished_or_future_hour'
    assert normalize_hour(measurement(value=float('nan')), NOW)[1] == 'invalid_value'


def test_ingestion_is_idempotent_and_accepts_corrections(tmp_path):
    path = tmp_path/'live.sqlite'
    hours = [{'timestamp': '2026-10-19T17:00:00+00:00', 'pm25': 12, 'coverage': 100}]
    assert save_hours(path, hours, load_config(), NOW)['inserted'] == 1
    assert save_hours(path, hours, load_config(), NOW)['unchanged'] == 1
    hours[0]['pm25'] = 13
    assert save_hours(path, hours, load_config(), NOW)['updated'] == 1
    assert len(read_hours(path)) == 1 and read_hours(path)[0]['pm25'] == 13


def metadata():
    return {'results': [{'id': 2415, 'sensors': [{'id': 4672, 'parameter': {'name': 'pm25'}}]}]}


def test_missing_credential_causes_no_network_request(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAQ_API_KEY', raising=False)
    calls = []
    with pytest.raises(RuntimeError, match='not configured'):
        ingest(tmp_path/'live.sqlite', NOW, get=lambda *args: calls.append(args))
    assert not calls and not (tmp_path/'live.sqlite').exists()


def test_wrong_station_metadata_is_not_imported(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAQ_API_KEY', 'test-only')
    with pytest.raises(RuntimeError, match='metadata'):
        ingest(tmp_path/'live.sqlite', NOW, get=lambda *args: {'results': [{'id': 999}]})
    assert not (tmp_path/'live.sqlite').exists()


def test_failed_pagination_does_not_write_partial_observations(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAQ_API_KEY', 'test-only')
    def get(path, params, key):
        if path.startswith('locations/'):
            return metadata()
        if params['page'] == 1:
            return {'results': [measurement() for _ in range(1000)]}
        raise RuntimeError('Simulated upstream outage')
    with pytest.raises(RuntimeError, match='outage'):
        ingest(tmp_path/'live.sqlite', NOW, get=get)
    assert not (tmp_path/'live.sqlite').exists()


def test_conflicting_same_hour_values_are_quarantined(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAQ_API_KEY', 'test-only')
    def get(path, params, key):
        return metadata() if path.startswith('locations/') else {'results': [measurement(value=10), measurement(value=30)]}
    result = ingest(tmp_path/'live.sqlite', NOW, get=get)
    assert result['accepted_unique_hours'] == 0 and not read_hours(tmp_path/'live.sqlite')
