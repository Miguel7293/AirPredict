import json
import sqlite3
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from airepredict import operations
from airepredict.registry import Registry
from airepredict.service import create_app


@pytest.fixture
def operational_client(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'ROOT', tmp_path)
    monkeypatch.setattr(operations, 'Registry', lambda: Registry(tmp_path/'registry'))
    monkeypatch.setenv('AIRPREDICT_ADMIN_TOKEN', 'a'*40)
    with TestClient(create_app()) as client:
        yield client


def test_admin_requires_authentication(operational_client):
    assert operational_client.get('/api/admin/overview').status_code == 401
    assert operational_client.post('/api/admin/jobs/backup').status_code == 401
    assert operational_client.get('/api/admin/backups/a.zip').status_code == 401


def test_admin_disabled_without_strong_token(operational_client, monkeypatch):
    monkeypatch.setenv('AIRPREDICT_ADMIN_TOKEN', 'short')
    assert operational_client.get('/api/admin/overview', headers={'Authorization': 'Bearer short'}).status_code == 503


def test_job_runs_and_reports_failure_without_secrets(operational_client, monkeypatch):
    def fail(action):
        raise RuntimeError('https://example.com?key=secret-credential')
    monkeypatch.setattr(operations, 'dispatch', fail)
    headers = {'Authorization': 'Bearer '+'a'*40}
    response = operational_client.post('/api/admin/jobs/ingest', headers=headers)
    assert response.status_code == 202
    identifier = response.json()['id']
    for _ in range(100):
        status = operational_client.get('/api/admin/jobs/'+identifier, headers=headers).json()
        if status['status'] == 'failed':
            break
        time.sleep(.01)
    assert status['status'] == 'failed'
    assert 'secret-credential' not in json.dumps(status)


def test_pwa_resources_and_cache_policy(operational_client):
    for route in ['/', '/widget', '/admin', '/sw.js', '/static/manifest.webmanifest', '/static/icon.svg']:
        assert operational_client.get(route).status_code == 200
    assert operational_client.get('/api/status').headers['cache-control'] == 'no-store'
    assert '/api/' in operational_client.get('/sw.js').text


def test_backup_restores_sqlite_and_checksums(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'ROOT', tmp_path)
    folder = tmp_path/'data/live'
    folder.mkdir(parents=True)
    (tmp_path/'requirements.txt').write_text('example==1.0')
    processed = tmp_path/'data/processed'
    processed.mkdir()
    (processed/'measurements.csv').write_text('timestamp,pm25\n2026-01-01,12.5\n')
    with sqlite3.connect(folder/'airepredict.sqlite') as connection:
        connection.execute('CREATE TABLE observations(value REAL)')
        connection.execute('INSERT INTO observations VALUES (12.5)')
    with operations.maintenance_lock():
        report = operations.backup()
    archive = tmp_path/'backups'/report['archive']
    restored = tmp_path/'restore'
    with zipfile.ZipFile(archive) as z:
        z.extractall(restored)
    assert (restored/'requirements.txt').read_text() == 'example==1.0'
    assert (restored/'data/processed/measurements.csv').is_file()
    with sqlite3.connect(restored/'data/live/airepredict.sqlite') as connection:
        assert connection.execute('SELECT value FROM observations').fetchone()[0] == 12.5
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    manifest = json.loads((restored/'manifest.json').read_text())
    for relative, checksum in manifest.items():
        assert operations.digest(restored/relative) == checksum


def test_cross_process_lock_excludes_overlapping_maintenance(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'ROOT', tmp_path)
    with operations.maintenance_lock():
        with pytest.raises(OSError):
            with operations.maintenance_lock():
                pytest.fail('Concurrent writer entered maintenance')


def test_interrupted_jobs_are_not_silently_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'ROOT', tmp_path)
    jobs = operations.Jobs()
    identifier = 'a'*32
    jobs.write({'id': identifier, 'status': 'running', 'action': 'retrain'})
    jobs.recover()
    assert jobs.read(identifier)['status'] == 'interrupted'
