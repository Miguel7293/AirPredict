"""GitHub Actions client. Secrets stay in headers and environment variables."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    base = os.environ['APP_BASE_URL'].rstrip('/')
    token = os.environ['AIRPREDICT_ADMIN_TOKEN']
    action = sys.argv[1]
    if not base.startswith('https://'):
        raise SystemExit('APP_BASE_URL must use HTTPS')

    def request(path, method='GET', binary=False):
        req = urllib.request.Request(base+path, method=method, headers={'Authorization': 'Bearer '+token})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read() if binary else json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Remote operation returned HTTP {exc.code}') from None

    job = request('/api/admin/jobs/'+action, 'POST')
    Path('artifacts').mkdir(exist_ok=True)
    for _ in range(180):
        job = request('/api/admin/jobs/'+job['id'])
        if job['status'] not in ['queued', 'running']:
            break
        time.sleep(5)
    else:
        raise SystemExit('Remote job timed out; inspect its state before retrying.')
    Path('artifacts/'+action+'.json').write_text(json.dumps(job, indent=2), encoding='utf-8')
    print(json.dumps({'job': job['id'], 'action': action, 'status': job['status']}))
    if job['status'] != 'completed':
        raise SystemExit('Maintenance did not complete successfully')
    if action == 'backup':
        filename = job['result']['archive']
        content = request('/api/admin/backups/'+filename, binary=True)
        import hashlib
        if hashlib.sha256(content).hexdigest() != job['result']['sha256']:
            raise SystemExit('Downloaded backup checksum mismatch')
        Path('artifacts/'+filename).write_bytes(content)


if __name__ == '__main__':
    main()
