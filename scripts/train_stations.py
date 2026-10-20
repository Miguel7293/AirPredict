"""Train district-specific models on disjoint chronological outcomes."""
import json
import joblib
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits
from airepredict.data import ROOT, download_target, prepare_target
from airepredict.features import FEATURES, make_features, temporal_split
from airepredict.experiment import candidates, fit, predict, metrics
from airepredict.stations import STATIONS, station_config


def main():
    for station in STATIONS[1:]:
        config=station_config(station['id'])
        manifest=download_target(config)
        frame, stats=prepare_target(config,manifest)
        features=make_features(frame)
        features=features.sort_values('target_time')
        validation=features.target_time.iloc[int(len(features)*.70)].floor('D')
        testing=features.target_time.iloc[int(len(features)*.85)].floor('D')
        train=features.loc[features.target_time<validation]
        val=features.loc[(features.target_time>=validation)&(features.target_time<testing)]
        test=features.loc[features.target_time>=testing]
        if min(len(train),len(val),len(test))<50:
            raise ValueError(f'Insufficient temporal coverage for {station["id"]}: {[len(x) for x in [train,val,test]]}')
        trials=[]
        with threadpool_limits(limits=2):
            for name,params,model in candidates(2026):
                fit(model,train,np.ones(len(train)))
                trials.append((metrics(val.y,predict(model,val))['mae'],name,params,model))
            # Persistence is a genuine candidate; keep it if local ML has no gain.
            persistence=metrics(val.y,val.pm25_now)['mae']
            score,name,params,selected=min(trials,key=lambda x:x[0])
            if persistence<=score: selected=None; name='persistencia'; params={}; score=persistence
            fitting=pd.concat([train,val],ignore_index=True)
            if selected is not None: fit(selected,fitting,np.ones(len(fitting)))
            predictions=predict(selected,test)
        bundle={'model':selected,'features':FEATURES,'predicts':'delta_pm25_t_plus_1','sklearn_version':sklearn.__version__,'config':config,'selection':{'source_weight_budget':0,'family':name,'parameters':params,'validation_mae':score}}
        folder=ROOT/f'models/{config["experiment_id"]}'; folder.mkdir(parents=True,exist_ok=True)
        joblib.dump(bundle,folder/'combinado.joblib')
        report={'station':station,'observations':len(frame),'features':len(features),'split_counts':{key:len(value) for key,value in [('train',train),('validation',val),('test',test)]},'split_ranges':{key:{'first_outcome_utc':value.target_time.min().isoformat(),'last_outcome_utc':value.target_time.max().isoformat()} for key,value in [('train',train),('validation',val),('test',test)]},'summary':{'combinado':{'test':metrics(test.y,predictions)},'persistencia':{'test':metrics(test.y,test.pm25_now)}},'selection':bundle['selection'],'source_stats':stats}
        destination=ROOT/f'reports/{config["experiment_id"]}'; destination.mkdir(parents=True,exist_ok=True)
        (destination/'resultados.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'station':station['name'],'counts':report['split_counts'],'metrics':report['summary'],'family':name},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
