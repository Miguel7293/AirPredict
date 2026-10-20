"""Authenticated, serialized maintenance jobs and consistent SQLite backups."""
import json
import os
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .data import ROOT, digest
from .registry import Registry, now_string


@contextmanager
def maintenance_lock():
    folder = ROOT/'data/live'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'maintenance.lock').open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def backup():
    """Caller holds maintenance lock; SQLite online backups avoid copying WAL state."""
    identifier = now_string().replace(':', '-')+'-'+uuid.uuid4().hex[:6]
    destination = ROOT/'backups'/identifier
    destination.mkdir(parents=True)
    checksums = {}
    for source in [ROOT/'models/registry', ROOT/'data/live']:
        if not source.exists():
            continue
        for path in source.rglob('*'):
            if not path.is_file() or path.suffix in ['.lock', '.tmp'] or path.name.endswith(('-wal', '-shm')):
                continue
            relative = path.relative_to(ROOT)
            target = destination/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == '.sqlite':
                with sqlite3.connect(path) as src, sqlite3.connect(target) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Backup integrity check failed')
            else:
                shutil.copy2(path, target)
            checksums[str(relative)] = digest(target)
    (destination/'manifest.json').write_text(json.dumps(checksums, indent=2), encoding='utf-8')
    archive = Path(shutil.make_archive(str(destination), 'zip', destination))
    return {'backup_id': identifier, 'files': len(checksums), 'archive': archive.name, 'sha256': digest(archive)}


def dispatch(action):
    from .live import ingest
    from .maintenance import run, demo
    from .monitoring import monitor
    from .registry import initialize
    registry = Registry()
    initialize(registry)
    if action == 'ingest':
        return ingest()
    if action == 'retrain':
        return run(registry)
    if action == 'monitor':
        return monitor(registry)
    if action == 'rollback':
        return {'restored': registry.rollback(reason='Authenticated operator workflow')}
    if action == 'backup':
        return backup()
    if action == 'demo':
        report = demo()
        return {'historical_simulation': True, 'application_registry_modified': False,
                'first_training': report['first_training']['status'], 'second_training': report['repeated_training']['status'],
                'restored': report['restored'] == report['initial_baseline']}
    raise ValueError('Unsupported operation')


class Jobs:
    """One process serves HTTP; a kernel lock also excludes concurrent processes."""
    def __init__(self):
        self.guard = threading.Lock()
        self.io = threading.RLock()

    @property
    def folder(self):
        path = ROOT/'data/live/jobs'
        path.mkdir(parents=True, exist_ok=True)
        return path

    def read(self, identifier):
        if not identifier.isalnum() or len(identifier) != 32:
            raise FileNotFoundError('Unknown job')
        with self.io:
            return json.loads((self.folder/(identifier+'.json')).read_text(encoding='utf-8'))

    def write(self, job):
        path = self.folder/(job['id']+'.json')
        temporary = path.with_suffix('.tmp')
        with self.io:
            temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)

    def recover(self):
        for path in self.folder.glob('*.json'):
            job = json.loads(path.read_text(encoding='utf-8'))
            if job['status'] in ['queued', 'running']:
                job.update(status='interrupted', completed_at=now_string(), error='Service restarted; inspect registry before retrying.')
                self.write(job)

    def start(self, action):
        if not self.guard.acquire(blocking=False):
            raise RuntimeError('Another maintenance job is running')
        identifier = uuid.uuid4().hex
        job = {'id': identifier, 'action': action, 'status': 'queued', 'created_at': now_string()}
        self.write(job)

        def worker():
            try:
                with maintenance_lock():
                    job.update(status='running', started_at=now_string())
                    self.write(job)
                    result = dispatch(action)
                    job.update(status='completed', result=result)
            except Exception as exc:
                # Do not expose exception strings that could include credentials or request URLs.
                job.update(status='failed', error_type=type(exc).__name__, error='Operation failed; inspect server-side configuration and registry audit.')
                Registry().event('operation_failed', detail={'action': action, 'job': identifier, 'error_type': type(exc).__name__})
            finally:
                job['completed_at'] = now_string()
                self.write(job)
                self.guard.release()

        threading.Thread(target=worker, daemon=True).start()
        return job.copy()
