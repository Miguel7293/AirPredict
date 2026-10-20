"""Seed a persistent deployment from the immutable image, then drop privileges."""
import os
import shutil
from pathlib import Path


def main():
    seed = Path(os.environ.get('AIRPREDICT_SEED', '/app'))
    root = Path(os.environ.get('AIRPREDICT_ROOT', str(seed)))
    root.mkdir(parents=True, exist_ok=True)
    if root.resolve() != seed.resolve():
        for relative in ['config', 'reports/oefa_campo_marte_v1', 'data/processed', 'models/oefa_campo_marte_v1']:
            source, target = seed/relative, root/relative
            if source.exists():
                shutil.copytree(source, target, dirs_exist_ok=True)
        shutil.copy2(seed/'requirements.txt', root/'requirements.txt')
    for relative in ['models/registry', 'data/live', 'backups']:
        (root/relative).mkdir(parents=True, exist_ok=True)
    if os.name != 'nt' and os.getuid() == 0:
        import pwd
        user = pwd.getpwnam('appuser')
        for path in [root, *root.rglob('*')]:
            if not path.is_symlink():
                os.chown(path, user.pw_uid, user.pw_gid)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    from .registry import initialize
    initialize()
    import uvicorn
    uvicorn.run('airepredict.service:app', host=os.environ.get('AIRPREDICT_HOST', '0.0.0.0'), port=int(os.environ.get('PORT', '8000')), workers=1)


if __name__ == '__main__':
    main()
