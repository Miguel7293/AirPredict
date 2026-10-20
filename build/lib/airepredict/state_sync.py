"""Read-only projection of the public runtime-state branch for free hosting.

Only the configured source repository supplies model artifacts. GitHub Actions is
the single writer; the web service switches complete snapshots atomically.
"""
import io
import json
import os
import shutil
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


def synchronize(root, repository):
    if repository != 'Miguel7293/AirPredict':
        raise ValueError('Untrusted state repository')
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(f'https://api.github.com/repos/{repository}/git/ref/heads/runtime-state', headers={'User-Agent': 'AirePredict-state-sync', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        sha = json.load(response)['object']['sha']
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Invalid state revision')
    if root.is_symlink() and root.resolve().name == sha:
        return False
    request = urllib.request.Request(f'https://codeload.github.com/{repository}/zip/{sha}', headers={'User-Agent': 'AirePredict-state-sync'})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = response.read(25*1024*1024+1)
    if len(payload) > 25*1024*1024:
        raise ValueError('State snapshot exceeds download limit')
    destination = parent/sha
    destination.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 100*1024*1024:
            raise ValueError('Expanded state exceeds size limit')
        for item in archive.infolist():
            relative = PurePosixPath(item.filename)
            parts = relative.parts[1:]
            if not parts or item.is_dir():
                continue
            if '..' in parts or any('\\' in p for p in parts) or parts[0] not in ['models', 'data', 'config', 'reports', 'requirements.txt', 'state.json']:
                continue
            path = destination.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(item))
    if not (destination/'state.json').is_file():
        raise ValueError('State has not been published by a successful workflow')
    # Validate the downloaded registry before exposing the snapshot to requests.
    import sqlite3
    import hashlib
    database = destination/'models/registry/registry.sqlite'
    with sqlite3.connect(database) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Invalid state registry')
        active = connection.execute("SELECT value FROM state WHERE key='active'").fetchone()[0]
        manifest = json.loads(connection.execute('SELECT manifest FROM releases WHERE id=?', (active,)).fetchone()[0])
    model = destination/'models/registry/releases'/active/'model.joblib'
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest['model_sha256']:
        raise ValueError('Downloaded model checksum mismatch')
    pointer = parent/'current.next'
    pointer.unlink(missing_ok=True)
    pointer.symlink_to(destination, target_is_directory=True)
    os.replace(pointer, root)
    return True


def start(root, repository):
    def loop():
        while True:
            time.sleep(600)
            try:
                synchronize(root, repository)
            except Exception as exc:
                print('State refresh failed; keeping last complete snapshot: '+type(exc).__name__, flush=True)
    threading.Thread(target=loop, daemon=True).start()
