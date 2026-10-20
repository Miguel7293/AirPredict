import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from airepredict import state_sync
from airepredict.registry import Registry
from test_mlops import bundle


def test_sync_refuses_untrusted_model_repository(tmp_path):
    with pytest.raises(ValueError, match='Untrusted'):
        state_sync.synchronize(tmp_path/'current', 'someone/untrusted')


@pytest.mark.skipif(os.name == 'nt', reason='Deployment uses Linux atomic symlinks')
@pytest.mark.parametrize('corrupt', [False, True])
def test_state_switch_is_atomic_and_checks_artifact_integrity(tmp_path, monkeypatch, corrupt):
    source = tmp_path/'remote'
    registry = Registry(source/'models/registry')
    active = registry.register(bundle(), {})
    registry.activate(active, expected_active=None, reason='Snapshot fixture')
    (source/'state.json').write_text(json.dumps({'registry': registry.state()}))
    if corrupt:
        (registry.root/'releases'/active/'model.joblib').write_bytes(b'corrupted')
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        for path in source.rglob('*'):
            if path.is_file():
                archive.write(path, 'snapshot/'+path.relative_to(source).as_posix())
    sha = 'a'*40
    def urlopen(request, **kwargs):
        if '/git/ref/' in request.full_url:
            return io.BytesIO(json.dumps({'object': {'sha': sha}}).encode())
        return io.BytesIO(content.getvalue())
    monkeypatch.setattr(state_sync.urllib.request, 'urlopen', urlopen)
    parent = tmp_path/'deployment'
    parent.mkdir()
    previous = parent/'previous'
    previous.mkdir()
    current = parent/'current'
    current.symlink_to(previous, target_is_directory=True)
    if corrupt:
        with pytest.raises(ValueError, match='checksum'):
            state_sync.synchronize(current, 'Miguel7293/AirPredict')
        assert current.resolve() == previous
    else:
        assert state_sync.synchronize(current, 'Miguel7293/AirPredict')
        assert current.resolve().name == sha
        assert not state_sync.synchronize(current, 'Miguel7293/AirPredict')
