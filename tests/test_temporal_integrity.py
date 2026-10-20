import pandas as pd
from airepredict.data import parse_oefa_hour, validate_records
from airepredict.features import make_features, temporal_split


def observations(hours, station='a', values=None):
    return pd.DataFrame({'source': 'OEFA', 'station': station,
                         'timestamp': pd.to_datetime(hours, utc=True),
                         'pm25': values if values is not None else range(len(hours))})


def test_gaps_are_not_consecutive_observations():
    raw = observations(['2026-01-01T00:00Z', '2026-01-01T01:00Z',
                        '2026-01-01T03:00Z', '2026-01-01T04:00Z'])
    assert make_features(raw).empty


def test_station_boundaries_do_not_supply_lags():
    a = observations(['2026-01-01T00:00Z', '2026-01-01T01:00Z'])
    b = observations(['2026-01-01T02:00Z', '2026-01-01T03:00Z'], 'b')
    assert make_features(pd.concat([a, b])).empty


def test_future_measurement_is_only_the_outcome():
    times = pd.date_range('2026-01-01', periods=4, freq='h', tz='UTC')
    frame = make_features(observations(times, values=[10, 20, 30, 999]))
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row['pm25_now'] == 30 and row['pm25_lag1'] == 20 and row['pm25_lag2'] == 10
    assert row['mean_last3'] == 20 and row['y'] == 999
    assert row['target_time']-row['timestamp'] == pd.Timedelta(hours=1)


def test_split_uses_outcome_time_at_local_midnight():
    f = pd.DataFrame({'target_time': pd.to_datetime(['2026-08-16T04:00Z', '2026-08-16T05:00Z', '2026-09-16T05:00Z'])})
    train, validation, test = temporal_split(f, '2026-08-16', '2026-09-16')
    assert list(train.index) == [0] and list(validation.index) == [1] and list(test.index) == [2]


def test_missing_hour_is_rejected_and_excel_midnight_is_explicit():
    assert parse_oefa_hour('2022-01-01', 'NA') is None
    assert parse_oefa_hour('2022-01-01', '1899-12-31') == '2022-01-01T05:00:00+00:00'


def test_conflicting_duplicate_is_quarantined():
    raw = observations(['2026-01-01T00:00Z', '2026-01-01T00:00Z', '2026-01-01T01:00Z'], values=[5, 9, 7])
    clean, stats = validate_records(raw)
    assert len(clean) == 1 and clean.iloc[0]['pm25'] == 7
    assert stats['conflicting_rows_removed'] == 2
