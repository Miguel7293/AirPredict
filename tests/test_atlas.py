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


@pytest.mark.parametrize('identifier',[2415,2402,2351])
def test_latest_station_mode_keeps_delayed_prediction_and_dates(tmp_path, monkeypatch, identifier):
    import airepredict.atlas as atlas
    database=tmp_path/f'{identifier}.sqlite'
    rows=[{'timestamp':f'2020-01-01T0{h}:00:00+00:00','pm25':10+h,'coverage':100} for h in [1,2,3]]
    save_hours(database,rows,station_config(identifier),datetime.now(timezone.utc))
    monkeypatch.setattr(atlas,'station_database',lambda _:database)
    with TestClient(create_app()) as client:
        assert client.get(f'/api/stations/{identifier}/forecast?mode=live').status_code==409
        data=client.get(f'/api/stations/{identifier}/forecast?mode=latest').json()
        assert data['mode']=='latest' and data['location_id']==identifier
        assert data['predicted_pm25']>=0 and data['target_in_past']
        assert not data['is_current_forecast']
        assert data['target_time_utc']=='2020-01-01T04:00:00+00:00'
        assert data['last_observation_utc']=='2020-01-01T03:00:00+00:00'


def test_atlas_api_never_accepts_unknown_station_or_location():
    with TestClient(create_app()) as client:
        assert client.get('/api/stations/999999/forecast').status_code==404
        assert client.get('/api/atlas/sites/not-a-point').status_code==404
        assert client.get('/api/atlas').status_code==200
        assert client.get('/stations').status_code==200


def test_manual_general_scenario_is_never_presented_as_current():
    report,_,_=general_assets()
    site=next(s for s in report['inventory'] if s['trained'])
    body={'site_id':site['id'],'observed_date':'2022-12-30','pm25':12,'previous_pm25':11}
    with TestClient(create_app()) as client:
        result=client.post('/api/general/predict',json=body)
        assert result.status_code==200
        assert result.json()['target_date']=='2022-12-31'
        assert result.json()['mode']=='scenario' and not result.json()['is_current_forecast']
        assert result.json()['input_origin']=='user_unverified'
        assert client.post('/api/general/predict',json={**body,'pm25':-1}).status_code==422
        assert client.post('/api/general/predict',json={**body,'site_id':'unknown'}).status_code==422
        assert client.post('/api/general/predict',json={**body,'observed_date':'2099-01-01'}).status_code==422
