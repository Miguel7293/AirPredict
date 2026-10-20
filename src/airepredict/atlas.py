"""Historical geographic exploration, separated from current station forecasts."""
import json
import os
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta, timezone

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from datetime import date
from threadpoolctl import threadpool_limits

from .data import ROOT
from .features import make_features
from .live import read_hours, utc_stamp
from .registry import initialize
from .stations import STATIONS, station_config, station_registry, station_database

# General research assets are immutable application assets. Runtime state holds
# only the mutable station registries, measurements and consumed eval windows.
SEED=Path(os.environ.get('AIRPREDICT_SEED',Path(__file__).resolve().parents[2]))


class GeneralScenario(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    site_id:str
    observed_date:date
    pm25:float=Field(ge=0,le=3000)
    previous_pm25:float|None=Field(default=None,ge=0,le=3000)


def estimate_day(site,day,value,previous,bundle):
    record={'pm25_now':value,'pm25_lag1':previous,'latitude':site['latitude'],'longitude':site['longitude'],'altitude':site['altitude']}
    for name,calendar,period in [('month',day.month,12),('weekday',day.dayofweek,7)]:
        record[name+'_sin']=np.sin(2*np.pi*calendar/period); record[name+'_cos']=np.cos(2*np.pi*calendar/period)
    with threadpool_limits(limits=2):
        return max(0,float(value+bundle['model'].predict(pd.DataFrame([record])[bundle['features']])[0]))


@lru_cache(maxsize=1)
def general_assets():
    report=json.loads((SEED/'reports/general_v1/training.json').read_text(encoding='utf-8'))
    daily=pd.read_csv(SEED/'data/processed/oefa_daily.csv')
    model=joblib.load(SEED/'models/general_v1/general.joblib')
    return report,daily,model


def general_history(identifier, year=None):
    report,daily,bundle=general_assets()
    site=next((s for s in report['inventory'] if s['id']==identifier),None)
    if not site: raise HTTPException(404,'Punto histórico desconocido.')
    frame=daily.loc[daily.site_id==identifier].sort_values('date')
    if year is not None: frame=frame.loc[frame.date.str.startswith(str(year))]
    history=[{'date':str(r.date),'pm25':float(r.pm25)} for r in frame.itertuples()]
    result={'site':site,'history':history,'mode':'historical','units':'µg/m³','model_version':bundle['version'],'prediction':None}
    if history:
        latest=history[-1]; day=pd.Timestamp(latest['date']); previous=next((h['pm25'] for h in history if h['date']==(day-pd.Timedelta(days=1)).date().isoformat()),np.nan)
        # Inference on held-out-time points is explicitly historical evaluation;
        # it never modifies the frozen general model or its test metrics.
        value=estimate_day(site,day,latest['pm25'],previous,bundle)
        result['prediction']={'value':value,'target_date':(day+pd.Timedelta(days=1)).date().isoformat(),'observed_date':latest['date'],'observed':latest['pm25'],'historical':True,'trained_site':site['trained']}
    return result


def available_station(identifier):
    try: return station_config(identifier)
    except ValueError as exc: raise HTTPException(404,str(exc)) from None


def station_forecast(identifier,mode='live'):
    from .service import Predictor
    config=available_station(identifier)
    registry=station_registry(identifier)
    identifier_version=initialize(registry)
    try:
        engine=Predictor(registry.validate(identifier_version),config=config)
    except Exception:
        restored=registry.rollback(expected_active=identifier_version,reason='Station loading failed',mark_failed=True)
        engine=Predictor(registry.validate(restored),config=config); identifier_version=restored
    engine.version=identifier_version
    if mode=='historical':
        frame=pd.read_csv(ROOT/'data/processed'/config.get('target_file','campo_marte_hourly.csv'))
        frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
        features=make_features(frame,require_target=False)
        if features.empty: raise HTTPException(409,'No hay tres horas consecutivas en el histórico de este punto.')
        latest=features.timestamp.max()
        selected=frame.loc[frame.timestamp.isin([latest-pd.Timedelta(hours=i) for i in [2,1,0]])]
        hours=[{'timestamp':r.timestamp.isoformat(),'pm25':float(r.pm25)} for r in selected.sort_values('timestamp').itertuples()]
        history=[{'timestamp':r.timestamp.isoformat(),'pm25':float(r.pm25)} for r in frame.loc[(frame.timestamp<=latest)&(frame.timestamp>latest-pd.Timedelta(hours=48))].itertuples()]
    elif mode=='live':
        history=read_hours(station_database(identifier),limit=72,config=config)
        hours=[{'timestamp':h['timestamp'],'pm25':h['pm25']} for h in history[-3:]]
        if len(hours)<3: raise HTTPException(409,'Aún no hay tres mediciones recientes para este punto. Puedes ver el histórico.')
    else: raise HTTPException(422,'El modo debe ser live o historical.')
    try:
        with threadpool_limits(limits=2): result=engine.forecast(hours,identifier,mode=mode)
    except ValueError: raise HTTPException(409,'Los datos recibidos están retrasados o no forman tres horas consecutivas. No se emite una predicción actual.') from None
    except Exception:
        if registry.state()['previous']:
            registry.rollback(expected_active=identifier_version,reason='Invalid station prediction',mark_failed=True)
        raise HTTPException(503,'El modelo no pudo responder. Se revisó la versión de respaldo; vuelve a intentarlo.') from None
    result.update(station=config['target_name'],history=history)
    if mode=='live':
        from .monitoring import record_forecast
        record_forecast(result,hours,station_database(identifier))
    return result


def install(app):
    @app.post('/api/general/predict')
    def scenario(request:GeneralScenario):
        report,_,bundle=general_assets()
        site=next((s for s in report['inventory'] if s['id']==request.site_id),None)
        if not site or not site['trained']: raise HTTPException(422,'Selecciona un punto representado en el entrenamiento del modelo general.')
        today=datetime.now(timezone(timedelta(hours=-5))).date()
        if request.observed_date>today: raise HTTPException(422,'La observación introducida no puede estar en el futuro.')
        day=pd.Timestamp(request.observed_date)
        value=estimate_day(site,day,request.pm25,request.previous_pm25 if request.previous_pm25 is not None else np.nan,bundle)
        return {'mode':'scenario','is_current_forecast':False,'site_id':site['id'],'model_version':bundle['version'],'units':'µg/m³',
                'predicted_pm25':value,'observed_date':request.observed_date.isoformat(),'target_date':(day+pd.Timedelta(days=1)).date().isoformat(),
                'input_origin':'user_unverified','outside_training_period':request.observed_date.isoformat()>report['fitted_through'],
                'note':'Simulación con datos introducidos por el usuario, sin verificar. No representa las condiciones actuales. El modelo se evaluó en el histórico OEFA; una fecha nueva no implica validación actual.'}

    @app.get('/api/atlas')
    def atlas():
        report,daily,_=general_assets()
        return {'general_model':{k:v for k,v in report.items() if k!='inventory'},'sites':report['inventory'],'years':sorted({int(d[:4]) for d in daily.date}), 'note':'Mapa de puntos observados. Sin cobertura predictiva continua entre puntos. Las fechas históricas no representan condiciones actuales.'}

    @app.get('/api/atlas/sites/{identifier}')
    def history(identifier:str,year:int|None=None):
        if year is not None and not 2018<=year<=2100: raise HTTPException(422,'Año no válido.')
        return general_history(identifier,year)

    @app.get('/api/stations')
    def station_list():
        values=[]
        now=datetime.now(timezone.utc)
        for station in STATIONS:
            config=station_config(station['id']); registry=station_registry(station['id'])
            hours=read_hours(station_database(station['id']),limit=72,config=config)
            latest=hours[-1] if hours else None
            report_path=ROOT/f'reports/{config["experiment_id"]}/resultados.json'
            report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
            state=registry.state(); manifest=registry.manifest(state['active']) if state['active'] else None
            last=utc_stamp(latest['timestamp']) if latest else None
            values.append({**station,'latest':latest,'data_age_hours':(now-last).total_seconds()/3600 if last else None,'fresh':bool(last and last<=now<last+timedelta(hours=1)), 'metrics':report.get('summary',{}),'model_version':state['active'],'active_metadata':manifest['metadata'] if manifest else None,'mlops':{'enabled':report_path.exists(),'scope':'Solo este sensor y distrito','previous_available':bool(state['previous']),'minimum_new_examples':168}})
        return {'stations':values,'generated_at':now.isoformat(),'refresh_note':'Actualizar consulta el último estado publicado. El proveedor puede entregar observaciones con retraso.'}

    @app.get('/api/stations/{identifier}/forecast')
    def forecast(identifier:int,mode:str='live'):
        available_station(identifier)
        try: return station_forecast(identifier,mode)
        except (FileNotFoundError,KeyError): raise HTTPException(503,'El modelo de este punto aún no está disponible.') from None

    @app.get('/api/stations/{identifier}/observations')
    def observations(identifier:int):
        config=available_station(identifier)
        return {'history':read_hours(station_database(identifier),limit=72,config=config),'units':'µg/m³'}
