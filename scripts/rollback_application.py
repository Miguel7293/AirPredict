"""Redeploy a commit that previously passed the delivery workflow."""
import json
import os
import re
import subprocess
import sys
import urllib.request

target = os.environ['TARGET_COMMIT']
if not re.fullmatch('[0-9a-f]{40}', target):
    raise SystemExit('A complete lowercase commit SHA is required')
repository = os.environ['GITHUB_REPOSITORY']
request = urllib.request.Request(
    f'https://api.github.com/repos/{repository}/actions/runs?head_sha={target}&status=success&per_page=100',
    headers={'Authorization': 'Bearer '+os.environ['GITHUB_TOKEN'], 'User-Agent': 'AirePredict-rollback'})
with urllib.request.urlopen(request, timeout=30) as response:
    runs = json.load(response)['workflow_runs']
if not any(run['path'] == '.github/workflows/deploy.yml' and run['conclusion'] == 'success' for run in runs):
    raise SystemExit('Target commit has no successful delivery workflow; rollback refused')
hook = os.environ['RENDER_DEPLOY_HOOK']
if not hook.startswith('https://api.render.com/deploy/'):
    raise SystemExit('Render deployment hook is missing or invalid')
with urllib.request.urlopen(urllib.request.Request(hook+'&ref='+target, method='POST'), timeout=60) as response:
    if response.status not in [200, 202]:
        raise SystemExit('Render did not accept the recovery deployment')
subprocess.run([sys.executable, 'scripts/check_deployment.py'], check=True,
               env={**os.environ, 'EXPECTED_COMMIT': target})
