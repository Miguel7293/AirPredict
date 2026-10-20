"""Explicit station identities and independent hourly model registries."""
from .data import ROOT, load_config
from .registry import Registry

STATIONS = [
    {'id':2415,'name':'Jesús María','region':'Lima','latitude':-12.070544,'longitude':-77.043214,'sensor_id':4672},
    {'id':2402,'name':'San Borja','region':'Lima','latitude':-12.108872,'longitude':-77.007689,'sensor_id':4492},
    {'id':2351,'name':'San Martín de Porres','region':'Lima','latitude':-12.008889,'longitude':-77.084472,'sensor_id':4319},
]


def station_config(identifier):
    station=next((s for s in STATIONS if s['id']==identifier),None)
    if station is None: raise ValueError('Punto de monitoreo desconocido.')
    base=load_config()
    if identifier==2415: return {**base,'target_name':station['name']}
    return {**base,'target_name':station['name'],'target_location_id':identifier,'target_sensor_id':station['sensor_id'],
            'experiment_id':f'station_{identifier}','target_file':f'station_{identifier}_hourly.csv',
            'live_database':f'data/live/station_{identifier}.sqlite','use_source':False}


def station_registry(identifier):
    config=station_config(identifier)
    return Registry(None if identifier==2415 else ROOT/f'models/stations/{identifier}',config=config)


def station_database(identifier):
    return ROOT/station_config(identifier).get('live_database','data/live/airepredict.sqlite')
