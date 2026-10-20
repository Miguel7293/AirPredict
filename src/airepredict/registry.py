"""Immutable local releases and transactional, compare-and-swap activation."""
import json
import platform
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from .data import ROOT, digest, load_config
from .features import FEATURES


def now_string():
    return datetime.now(timezone.utc).isoformat()


def environment():
    return {'python': '.'.join(platform.python_version().split('.')[:2]), 'sklearn': sklearn.__version__,
            'numpy': np.__version__, 'pandas': pd.__version__, 'joblib': joblib.__version__}


class Registry:
    def __init__(self, root=None, *, sandbox=False):
        self.root = Path(root or ROOT/'models/registry')
        self.sandbox = sandbox

    @contextmanager
    def connection(self):
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.root/'registry.sqlite', timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript('''
              CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
              CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL, release_id TEXT, detail TEXT NOT NULL);
            ''')
            stored = connection.execute("SELECT value FROM state WHERE key='sandbox'").fetchone()
            if stored and stored['value'] != str(self.sandbox):
                raise ValueError('Registry environment mismatch: a sandbox cannot be opened as the application registry.')
            connection.execute("INSERT OR IGNORE INTO state VALUES ('sandbox', ?)", (str(self.sandbox),))
            connection.commit()
            yield connection
        finally:
            connection.close()

    def event(self, action, release_id=None, detail=None):
        with self.connection() as connection:
            connection.execute('INSERT INTO events(at,action,release_id,detail) VALUES (?,?,?,?)',
                               (now_string(), action, release_id, json.dumps(detail or {}, ensure_ascii=False)))
            connection.commit()

    def state(self):
        if not (self.root/'registry.sqlite').exists():
            return {'active': None, 'previous': None}
        with self.connection() as connection:
            values = dict(connection.execute('SELECT key,value FROM state').fetchall())
        return {'active': values.get('active'), 'previous': values.get('previous')}

    def manifest(self, identifier):
        with self.connection() as connection:
            row = connection.execute('SELECT manifest FROM releases WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise ValueError('Unknown release identifier')
        return json.loads(row['manifest'])

    def register(self, bundle, metadata):
        if bundle.get('sklearn_version') != sklearn.__version__:
            raise ValueError('Training library version differs from the current runtime')
        if bundle['features'] != FEATURES or bundle.get('predicts') != 'delta_pm25_t_plus_1':
            raise ValueError('Incompatible feature/output contract')
        config = load_config()
        if any(bundle['config'][key] != config[key] for key in ['target_location_id', 'target_sensor_id']):
            raise ValueError('Incompatible location or sensor')
        identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:10]
        folder = self.root/'releases'/identifier
        folder.mkdir(parents=True)
        joblib.dump(bundle, folder/'model.joblib')
        # Preserve the source and configuration of the release; never overwrite a release.
        for name in ['features.py', 'experiment.py', 'service.py', 'data.py']:
            shutil.copy2(Path(__file__).parent/name, folder/name)
        shutil.copy2(ROOT/'requirements.txt', folder/'requirements.txt')
        manifest = {'id': identifier, 'created_at': now_string(), 'sandbox': self.sandbox,
                    'model_sha256': digest(folder/'model.joblib'), 'feature_sha256': digest(folder/'features.py'),
                    'environment': environment(), 'config': bundle['config'], 'metadata': metadata}
        (folder/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        with self.connection() as connection:
            connection.execute('INSERT INTO releases VALUES (?,?)', (identifier, json.dumps(manifest, ensure_ascii=False)))
            connection.execute('INSERT INTO events(at,action,release_id,detail) VALUES (?,?,?,?)',
                               (now_string(), 'registered', identifier, json.dumps(metadata, ensure_ascii=False)))
            connection.commit()
        self.validate(identifier)
        return identifier

    def validate(self, identifier):
        with self.connection() as connection:
            if connection.execute('SELECT value FROM state WHERE key=?', ('blocked:'+identifier,)).fetchone():
                raise ValueError('This release was marked faulty and cannot be reactivated')
        manifest = self.manifest(identifier)
        path = self.root/'releases'/identifier/'model.joblib'
        if digest(path) != manifest['model_sha256']:
            raise ValueError('Release checksum mismatch')
        if manifest['environment'] != environment():
            raise ValueError('Release requires a different runtime; restore its application environment first.')
        if manifest['feature_sha256'] != digest(Path(__file__).parent/'features.py'):
            raise ValueError('Release requires a different feature implementation; restore its application release first.')
        bundle = joblib.load(path)
        if bundle['features'] != FEATURES or bundle.get('predicts') != 'delta_pm25_t_plus_1':
            raise ValueError('Release feature/output contract mismatch')
        from .experiment import predict
        smoke = pd.DataFrame([[12, 11, 10, 11, 1, 0, 1, 0, 1]], columns=FEATURES)
        value = predict(bundle['model'], smoke)
        if len(value) != 1 or not np.isfinite(value).all() or (value < 0).any():
            raise ValueError('Release prediction smoke test failed')
        return path

    def activate(self, identifier, *, expected_active, reason, evaluation=None, administrative=False):
        self.validate(identifier)
        manifest = self.manifest(identifier)
        if expected_active is not None and not administrative:
            if not evaluation or not evaluation.get('approved'):
                raise ValueError('Promotion requires an approved candidate evaluation')
            if evaluation.get('champion_id') != expected_active or evaluation.get('candidate_id') != identifier:
                raise ValueError('Evaluation belongs to a different champion/candidate pair')
            if evaluation.get('historical_demo') and not self.sandbox:
                raise ValueError('Historical demonstration cannot authorize application promotion')
        with self.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute("SELECT value FROM state WHERE key='active'").fetchone()
            current = row['value'] if row else None
            if current != expected_active:
                raise ValueError('Active release changed concurrently; evaluate again against the new active release.')
            connection.execute("INSERT OR REPLACE INTO state VALUES ('previous',?)", (current,))
            connection.execute("INSERT OR REPLACE INTO state VALUES ('active',?)", (identifier,))
            detail = {'reason': reason, 'previous': current, 'administrative': administrative, 'evaluation': evaluation}
            connection.execute('INSERT INTO events(at,action,release_id,detail) VALUES (?,?,?,?)',
                               (now_string(), 'activated', identifier, json.dumps(detail, ensure_ascii=False)))
            connection.commit()

    def rollback(self, *, expected_active=None, reason='Manual rollback', mark_failed=False):
        state = self.state()
        if expected_active is not None and state['active'] != expected_active:
            raise ValueError('Active release changed; rollback cancelled')
        previous = state['previous']
        if not previous:
            raise ValueError('There is no previous release to restore')
        self.validate(previous)
        with self.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            current = connection.execute("SELECT value FROM state WHERE key='active'").fetchone()
            if not current or current['value'] != state['active']:
                raise ValueError('Active release changed; rollback cancelled')
            connection.execute("UPDATE state SET value=? WHERE key='active'", (previous,))
            connection.execute("UPDATE state SET value=NULL WHERE key='previous'")
            if mark_failed:
                connection.execute('INSERT OR REPLACE INTO state VALUES (?,?)', ('blocked:'+state['active'], reason))
            connection.execute('INSERT INTO events(at,action,release_id,detail) VALUES (?,?,?,?)',
                               (now_string(), 'rolled_back', previous, json.dumps({'failed_or_replaced': state['active'], 'reason': reason, 'marked_faulty': mark_failed})))
            connection.commit()
        return previous

    def history(self, limit=30):
        with self.connection() as connection:
            rows = connection.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [{**dict(row), 'detail': json.loads(row['detail'])} for row in rows]


def initialize(registry=None):
    registry = registry or Registry()
    if registry.state()['active']:
        return registry.state()['active']
    config = load_config()
    result = json.loads((ROOT/f'reports/{config["experiment_id"]}/resultados.json').read_text(encoding='utf-8'))
    bundle = joblib.load(ROOT/f'models/{config["experiment_id"]}/combinado.joblib')
    reserved_end = (pd.Timestamp(config['target_end'], tz='Etc/GMT+5')+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)).tz_convert('UTC').isoformat()
    identifier = registry.register(bundle, {'origin': 'original_experimental_run', 'trained_until': result['split_ranges']['validation']['last_outcome_utc'],
                                          'evaluated_until': reserved_end, 'initial_metrics': result['summary']['combinado']['test'],
                                          'status': 'experimental', 'promotion_policy_passed': False})
    registry.activate(identifier, expected_active=None, reason='Register existing experimental application model; not production certification')
    return identifier
