"""Exact time joins prevent shifts across gaps, stations or future observations."""
import numpy as np
import pandas as pd

FEATURES = ['pm25_now', 'pm25_lag1', 'pm25_lag2', 'mean_last3', 'change_last1',
            'hour_sin', 'hour_cos', 'weekday_sin', 'weekday_cos']


def make_features(measurements, *, require_target=True):
    blocks = []
    for (source, station), group in measurements.groupby(['source', 'station']):
        series = group.copy()
        series['timestamp'] = pd.to_datetime(series['timestamp'], utc=True)
        series = series.set_index('timestamp')['pm25'].sort_index()
        if not series.index.is_unique:
            raise ValueError('Duplicate timestamps must be resolved before features')
        block = pd.DataFrame({'timestamp': series.index, 'pm25_now': series.to_numpy()})
        for lag in [1, 2]:
            block[f'pm25_lag{lag}'] = series.reindex(series.index-pd.Timedelta(hours=lag)).to_numpy()
        block['y'] = series.reindex(series.index+pd.Timedelta(hours=1)).to_numpy()
        block['mean_last3'] = block[['pm25_now', 'pm25_lag1', 'pm25_lag2']].mean(axis=1)
        block['change_last1'] = block['pm25_now']-block['pm25_lag1']
        local = block['timestamp'].dt.tz_convert('Etc/GMT+5')
        for name, values, period in [('hour', local.dt.hour, 24), ('weekday', local.dt.dayofweek, 7)]:
            block[name+'_sin'] = np.sin(2*np.pi*values/period)
            block[name+'_cos'] = np.cos(2*np.pi*values/period)
        block['target_time'] = block['timestamp']+pd.Timedelta(hours=1)
        block['source'], block['station'] = source, station
        blocks.append(block.dropna(subset=FEATURES+(['y'] if require_target else [])))
    if not blocks:
        return pd.DataFrame(columns=['timestamp', 'target_time', 'source', 'station', *FEATURES, 'y'])
    return pd.concat(blocks, ignore_index=True).sort_values(['station', 'timestamp']).reset_index(drop=True)


def temporal_split(frame, validation_start, test_start):
    validation = pd.Timestamp(validation_start, tz='Etc/GMT+5').tz_convert('UTC')
    test = pd.Timestamp(test_start, tz='Etc/GMT+5').tz_convert('UTC')
    # Split on the outcome timestamp so the last training outcome precedes validation.
    return (frame.loc[frame['target_time'] < validation].copy(),
            frame.loc[(frame['target_time'] >= validation) & (frame['target_time'] < test)].copy(),
            frame.loc[frame['target_time'] >= test].copy())
