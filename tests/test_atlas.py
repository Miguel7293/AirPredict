"""Validate geographic scope, historical dates and station isolation."""
from datetime import datetime, timezone
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from airepredict.atlas import general_assets, general_history
from airepredict.data import ROOT
from airepredict.live import save_hours, read_hours
from airepredict.service import create_app
from airepredict.stations import station_config


def test_general_training_keeps_a_future_test_period():
    report,frame,bundle=general_assets()
    assert report['counts']['scanned_rows']==2883877
    assert report['split_counts']['final_fitting']==report['split_counts']['train']+report['split_counts']['validation']
    assert report['fitted_through'] < report['test_start'] <= report['evaluated_through']
    assert len(frame)==report['counts']['accepted_daily_observations']
    assert bundle['predicts']=='delta_daily_pm25_next_day'
    assert report['test']['n']>1000


def test_general_forecast_is_historical_and_dated():
    report,_,_=general_assets()
    site=next(s for s in report['inventory'] if s['daily_count']>300)
    result=general_history(site['id'])
    assert result['mode']=='historical' and result['prediction']['historical']
    assert result['prediction']['target_date']>result['prediction']['observed_date']
    assert np.isfinite(result['prediction']['value']) and result['prediction']['value']>=0
    empty=general_history(site['id'],2099)
    assert empty['history']==[] and empty['prediction'] is None


def test_live_sensor_isolation(tmp_path):
    database=tmp_path/'sensors.sqlite'
    now=datetime.now(timezone.utc)
    for identifier,value in [(2415,10),(2402,20),(2351,30)]:
        save_hours(database,[{'timestamp':'2026-01-01T00:00:00+00:00','pm25':value,'coverage':100}],station_config(identifier),now)
    for identifier,value in [(2415,10),(2402,20),(2351,30)]:
        assert read_hours(database,config=station_config(identifier))[0]['pm25']==value


def test_atlas_api_never_accepts_unknown_station_or_location():
    with TestClient(create_app()) as client:
        assert client.get('/api/stations/999999/forecast').status_code==404
        assert client.get('/api/atlas/sites/not-a-point').status_code==404
        assert client.get('/api/atlas').status_code==200
        assert client.get('/stations').status_code==200
