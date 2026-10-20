"""Scan the entire initial OEFA file; train only valid daily PM2.5 outcomes.

Run explicitly after adding data. The fixed general model is not retrained by
the hourly station workflow. Test outcomes never select a recipe.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from pyproj import Transformer
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from airepredict.data import ROOT, digest, finite_nonnegative
from airepredict.experiment import metrics

FEATURES = ['pm25_now', 'pm25_lag1', 'latitude', 'longitude', 'altitude', 'month_sin', 'month_cos', 'weekday_sin', 'weekday_cos']


def daily_features(frame):
    blocks=[]
    for station, rows in frame.groupby('site_id'):
        rows=rows.sort_values('date').copy().set_index('date')
        rows['pm25_now']=rows.pm25
        rows['pm25_lag1']=rows.pm25.reindex(rows.index-pd.Timedelta(days=1)).to_numpy()
        rows['y']=rows.pm25.reindex(rows.index+pd.Timedelta(days=1)).to_numpy()
        for name, value, period in [('month',rows.index.month,12),('weekday',rows.index.dayofweek,7)]:
            rows[name+'_sin']=np.sin(2*np.pi*value/period)
            rows[name+'_cos']=np.cos(2*np.pi*value/period)
        rows['target_date']=rows.index+pd.Timedelta(days=1)
        blocks.append(rows.reset_index())
    return pd.concat(blocks,ignore_index=True)


def main():
    source=next((ROOT/'Dataset').glob('*.csv'))
    output=ROOT/'models/general_v1'; output.mkdir(parents=True,exist_ok=True)
    folder=ROOT/'reports/general_v1'; folder.mkdir(parents=True,exist_ok=True)
    records=[]; counts=Counter(); inventory={}; transformers={}; raw_stats=defaultdict(Counter)
    with source.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream,delimiter=';'):
            counts['scanned_rows']+=1
            key='|'.join(row[k].strip() for k in ['NOMBRE_PUNTO','ESTE','NORTE','ZONA','DATUM'])
            site_id=hashlib.sha256(key.encode()).hexdigest()[:12]
            if site_id not in inventory:
                lat=lon=None
                try:
                    zone=int(row['ZONA']); assert row['DATUM'].strip().upper()=='WGS84' and zone in [17,18,19]
                    transform=transformers.setdefault(zone,Transformer.from_crs(32700+zone,4326,always_xy=True))
                    lon,lat=transform.transform(float(row['ESTE']),float(row['NORTE']))
                    assert -19<lat<1 and -82<lon<-68
                except (ValueError,AssertionError,KeyError): lat=lon=None
                clean=lambda name: row[name].strip().title() if row[name].strip() not in ['NA',''] else 'Sin especificar'
                inventory[site_id]={'id':site_id,'code':row['NOMBRE_PUNTO'].strip(),'district':clean('DISTRITO'),'region':clean('DEPARTAMENTO'),'province':clean('PROVINCIA'),'latitude':lat,'longitude':lon,'altitude':finite_nonnegative(row['ALTITUD']), 'source':'OEFA','description':row['DESCRIPCION_UBICACION'].strip()}
            raw_stats[site_id]['rows']+=1
            value=finite_nonnegative(row['PM2.5'])
            if value is None: counts['no_valid_pm25']+=1; continue
            counts['valid_pm25_rows']+=1
            if row['UNIDAD_MEDIDA'].strip() not in ['ug/m3','µg/m³','μg/m³']: counts['unknown_units']+=1; continue
            # Missing clock times cannot identify an hourly outcome. Daily rows
            # explicitly provided by OEFA preserve the original observation scale.
            if row['PERIODO'].strip().lower()!='24 horas': counts['not_explicit_daily']+=1; continue
            try: day=datetime.strptime(row['FECHA_INICIO'].strip(),'%Y-%m-%d').date().isoformat()
            except ValueError: counts['invalid_date']+=1; continue
            records.append({'site_id':site_id,'date':day,'pm25':value})
    frame=pd.DataFrame(records)
    conflict=frame.groupby(['site_id','date']).pm25.transform('nunique').gt(1)
    counts['conflicting_daily_rows_removed']=int(conflict.sum())
    frame=frame.loc[~conflict].drop_duplicates(['site_id','date'])
    frame=frame.merge(pd.DataFrame(inventory.values()).rename(columns={'id':'site_id'})[['site_id','latitude','longitude','altitude']],on='site_id',validate='many_to_one')
    counts['accepted_daily_observations']=len(frame)
    frame.to_csv(ROOT/'data/processed/oefa_daily.csv',index=False)
    frame['date']=pd.to_datetime(frame.date)
    features=daily_features(frame); examples=features.dropna(subset=['y']).copy()
    # Global calendar boundaries: no later station can leak into an earlier test.
    dates=sorted(examples.target_date.unique())
    validation=pd.Timestamp(dates[int(len(dates)*.70)]); test=pd.Timestamp(dates[int(len(dates)*.85)])
    train=examples.loc[examples.target_date<validation]; val=examples.loc[(examples.target_date>=validation)&(examples.target_date<test)]; holdout=examples.loc[examples.target_date>=test]
    trials=[]
    with threadpool_limits(limits=2):
        for leaves in [7,15]:
            estimator=HistGradientBoostingRegressor(max_leaf_nodes=leaves,max_iter=160,learning_rate=.05,l2_regularization=10,min_samples_leaf=25,early_stopping=False,random_state=2026)
            estimator.fit(train[FEATURES],train.y-train.pm25_now)
            predicted=np.maximum(0,val.pm25_now+estimator.predict(val[FEATURES]))
            trials.append((metrics(val.y,predicted)['mae'],estimator))
        selected=min(trials,key=lambda item:item[0])[1]
        fitting=pd.concat([train,val]); selected.fit(fitting[FEATURES],fitting.y-fitting.pm25_now)
        predicted=np.maximum(0,holdout.pm25_now+selected.predict(holdout[FEATURES]))
    performance=metrics(holdout.y,predicted); baseline=metrics(holdout.y,holdout.pm25_now)
    version='general-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    joblib.dump({'model':selected,'features':FEATURES,'version':version,'sklearn_version':sklearn.__version__,'predicts':'delta_daily_pm25_next_day'},output/'general.joblib')
    # Final model deliberately excludes the held-out test. "Whole dataset" means
    # every site is considered, not sacrificing a credible unseen-time evaluation.
    summary={'version':version,'created_at':datetime.now(timezone.utc).isoformat(),'source_sha256':digest(source),'counts':dict(counts),'target':'PM2.5 diario del día siguiente, µg/m³','features':FEATURES,'validation_start':validation.date().isoformat(),'test_start':test.date().isoformat(),'split_counts':{'train':len(train),'validation':len(val),'test':len(holdout),'final_fitting':len(fitting)},'test':performance,'persistence':baseline,'validation_trials_mae':[v for v,_ in trials],'fitted_through':fitting.target_date.max().date().isoformat(),'evaluated_through':holdout.target_date.max().date().isoformat(),'training_sites':int(fitting.site_id.nunique()),'evaluated_sites':int(holdout.site_id.nunique()),'limitations':['Predicción diaria; no equivale a una predicción horaria.','Solo se usan valores diarios explícitos de PM2.5; no se inventan horas ni contaminantes.','Los puntos del mapa no representan cobertura continua del país.','La evaluación temporal no valida ubicaciones nuevas fuera de las estaciones observadas.','El modelo es experimental: no es un índice oficial de calidad del aire.']}
    for site in inventory.values():
        subset=frame.loc[frame.site_id==site['id']]
        site.update(total_rows=raw_stats[site['id']]['rows'],daily_count=len(subset),first_date=subset.date.min().date().isoformat() if len(subset) else None,last_date=subset.date.max().date().isoformat() if len(subset) else None,mean_pm25=float(subset.pm25.mean()) if len(subset) else None,trained=int((fitting.site_id==site['id']).sum())>0)
    summary['inventory']=list(inventory.values())
    (folder/'training.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    holdout.assign(predicted=predicted).to_csv(folder/'test_predictions.csv',index=False)
    print(json.dumps({k:summary[k] for k in ['counts','split_counts','test','persistence','training_sites','evaluated_sites']},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
