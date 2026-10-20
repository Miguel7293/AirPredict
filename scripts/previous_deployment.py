"""Capture only a public, validated SHA; never copy request text to shell output."""
import json
import os
import re
import urllib.request

try:
    base = os.environ['APP_BASE_URL'].rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('HTTPS required')
    with urllib.request.urlopen(base+'/ready', timeout=60) as response:
        previous = json.load(response).get('commit', '')
    if re.fullmatch('[0-9a-f]{40}', previous) and previous != os.environ['GITHUB_SHA']:
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as handle:
            handle.write('PREVIOUS_COMMIT='+previous+'\n')
except (OSError, ValueError):
    print('Previous healthy deployment could not be identified; automatic software recovery will not be attempted.')
