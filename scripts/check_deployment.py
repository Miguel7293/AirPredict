import json
import math
import os
import time
import urllib.request

base = os.environ['APP_BASE_URL'].rstrip('/')
if not base.startswith('https://'):
    raise SystemExit('A public HTTPS APP_BASE_URL is required')
expected = os.environ.get('EXPECTED_COMMIT')
for attempt in range(90):
    try:
        with urllib.request.urlopen(base+'/ready', timeout=20) as response:
            ready = json.load(response)
        if expected and ready['commit'] != expected:
            raise ValueError('Deployment is not serving the expected commit yet')
        with urllib.request.urlopen(base+'/api/demo', timeout=20) as response:
            data = json.load(response)
        assert data['mode'] == 'historical' and not data['is_current_forecast']
        assert math.isfinite(data['predicted_pm25']) and data['predicted_pm25'] >= 0
        if os.environ.get('CHECK_ATLAS','1')=='1':
            with urllib.request.urlopen(base+'/api/atlas', timeout=30) as response:
                atlas=json.load(response)
            assert atlas['general_model']['training_sites']>=20
            for station in [2415,2402,2351]:
                with urllib.request.urlopen(base+f'/api/stations/{station}/forecast?mode=historical', timeout=30) as response:
                    prediction=json.load(response)
                assert prediction['location_id']==station and prediction['mode']=='historical'
                assert math.isfinite(prediction['predicted_pm25']) and prediction['predicted_pm25']>=0
        print(json.dumps({'status': 'verified', 'commit': ready['commit'], 'model': ready['model_version']}))
        break
    except Exception:
        if attempt == 89:
            raise SystemExit('Deployment failed verification. Inspect Render and restore the prior application release if necessary.') from None
        time.sleep(10)
