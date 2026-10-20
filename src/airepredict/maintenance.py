"""Train candidates, evaluate on later outcomes, and promote only after gates pass."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

from .data import ROOT, load_config, validate_records, digest
from .experiment import fit, metrics, paired_daily_bootstrap, predict, training_data
from .features import FEATURES, make_features
from .live import DEFAULT_DATABASE, read_hours
from .registry import Registry, initialize, now_string


def load_policy():
    return json.loads((ROOT/'config/promotion_policy.json').read_text(encoding='utf-8'))


def evaluate(candidate, champion, evaluation, policy):
    if evaluation.empty:
        return {'approved': False, 'reasons': ['No evaluable outcomes'], 'n': 0}
    candidate_predictions = predict(candidate['model'], evaluation)
    champion_predictions = predict(champion['model'], evaluation)
    if not (np.isfinite(candidate_predictions).all() and np.isfinite(champion_predictions).all()):
        raise ValueError('Non-finite predictions during evaluation')
    c = metrics(evaluation['y'], candidate_predictions)
    a = metrics(evaluation['y'], champion_predictions)
    p = metrics(evaluation['y'], predict(None, evaluation))
    local = evaluation['target_time'].dt.tz_convert('Etc/GMT+5')
    expected_hours = int(((local.max().normalize()+pd.Timedelta(days=1))-local.min().normalize()).total_seconds()/3600)
    coverage = len(evaluation)/expected_hours
    days = int(local.dt.date.nunique())
    relative = (a['mae']-c['mae'])/a['mae'] if a['mae'] > 0 else 0
    uncertainty = paired_daily_bootstrap(evaluation, candidate_predictions, champion_predictions, 2026)
    high = evaluation['y'].ge(evaluation['y'].quantile(.90)).to_numpy()
    high_c = float(np.sqrt(np.mean((candidate_predictions[high]-evaluation['y'].to_numpy()[high])**2)))
    high_a = float(np.sqrt(np.mean((champion_predictions[high]-evaluation['y'].to_numpy()[high])**2)))
    checks = {
        'enough_examples': len(evaluation) >= policy['minimum_examples'],
        'enough_observed_days': days >= policy['minimum_observed_days'],
        'sufficient_coverage': coverage >= policy['minimum_evaluable_coverage'],
        'mae_improves_active': relative >= policy['minimum_relative_mae_improvement'] and c['mae'] < a['mae'],
        'beats_persistence': c['mae'] < p['mae'],
        'rmse_acceptable': c['rmse'] <= a['rmse']*policy['maximum_rmse_ratio'],
        'bias_acceptable': abs(c['bias']) <= policy['maximum_absolute_bias'],
        'high_concentrations_acceptable': high_c <= high_a*policy['maximum_high_concentration_rmse_ratio'],
        'uncertainty_acceptable': not policy['require_negative_daily_bootstrap_upper_bound'] or uncertainty['ci95_daily_bootstrap'][1] < 0,
    }
    return {'approved': all(checks.values()), 'checks': checks, 'reasons': [name for name, ok in checks.items() if not ok],
            'candidate': c, 'active': a, 'persistence': p, 'relative_mae_improvement': relative,
            'n': len(evaluation), 'observed_days': days, 'evaluable_coverage': coverage,
            'high_concentration_rmse': {'candidate': high_c, 'active': high_a, 'n': int(high.sum())},
            'uncertainty': uncertainty, 'policy': policy,
            'evaluation_start': evaluation['target_time'].min().isoformat(),
            'evaluation_end': evaluation['target_time'].max().isoformat()}


def run(registry=None, *, historical_demo=False):
    registry = registry or Registry()
    if historical_demo and not registry.sandbox:
        raise ValueError('Historical replay must use a separate sandbox registry')
    active_id = initialize(registry)
    try:
        config = load_config()
        manifest = registry.manifest(active_id)
        champion = joblib.load(registry.validate(active_id))
        raw = pd.read_csv(ROOT/'data/processed/campo_marte_hourly.csv')
        if not historical_demo:
            fresh = read_hours(DEFAULT_DATABASE, limit=100000)
            if fresh:
                appended = pd.DataFrame(fresh).assign(source='OpenAQ', station=str(config['target_location_id']), sensor_id=config['target_sensor_id'])
                raw = pd.concat([raw, appended], ignore_index=True)
        target, _ = validate_records(raw)
        target = make_features(target)
        if historical_demo:
            evaluation_start = pd.Timestamp(config['test_start'], tz='Etc/GMT+5').tz_convert('UTC')
        else:
            cutoff = pd.Timestamp(manifest['metadata']['evaluated_until'])
            with registry.connection() as connection:
                reservations = connection.execute("SELECT detail FROM events WHERE action='evaluation_reserved'").fetchall()
            for reservation in reservations:
                cutoff = max(cutoff, pd.Timestamp(json.loads(reservation['detail'])['evaluation_end']))
            novel = target.loc[target['target_time'] > cutoff]
            if len(novel) < 168:
                result = {'status': 'skipped', 'active_unchanged': active_id, 'reason': 'Fewer than 168 complete examples after the last reserved evaluation period.', 'new_examples': len(novel)}
                registry.event('retraining_skipped', active_id, result)
                return result
            evaluation_start = max((novel['target_time'].max().tz_convert('Etc/GMT+5').normalize()-pd.Timedelta(days=6)).tz_convert('UTC'), cutoff+pd.Timedelta(microseconds=1))
        train = target.loc[target['target_time'] < evaluation_start]
        evaluation = target.loc[target['target_time'] >= evaluation_start]
        if len(train) < 300 or evaluation.empty:
            raise ValueError('Insufficient training or evaluation examples')
        if train['target_time'].max() >= evaluation['target_time'].min():
            raise ValueError('Training outcomes overlap the evaluation period')
        if not historical_demo:
            registry.event('evaluation_reserved', active_id, {'evaluation_start': evaluation['target_time'].min().isoformat(),
                                                           'evaluation_end': evaluation['target_time'].max().isoformat(),
                                                           'reason': 'Consumed even if training fails or the candidate is rejected; no repeated selection on this window.'})
        source = make_features(pd.read_csv(ROOT/'data/processed/oefa_hourly.csv'))
        source = source.loc[source['target_time'] < evaluation_start]
        # Freeze the recipe; do not tune hyperparameters against the approval window.
        reference = joblib.load(ROOT/f'models/{config["experiment_id"]}/combinado.joblib')
        estimator = clone(reference['model'])
        fitting, weights = training_data(source, train, 'combinado', reference['selection']['source_weight_budget'])
        fit(estimator, fitting, weights)
        candidate = {**reference, 'model': estimator, 'status': 'candidate_unapproved'}
        identifier = registry.register(candidate, {'origin': 'historical_replay' if historical_demo else 'retraining',
            'trained_until': train['target_time'].max().isoformat(), 'evaluated_until': evaluation['target_time'].max().isoformat(),
            'training_examples': len(fitting), 'target_training_examples': len(train),
            'source_weight_budget': reference['selection']['source_weight_budget'], 'historical_demo': historical_demo})
        policy = load_policy()
        if historical_demo:
            # Demonstrates transitions on reused historical data; never grants production approval.
            policy = {**policy, 'require_negative_daily_bootstrap_upper_bound': False,
                      'maximum_high_concentration_rmse_ratio': 1.5,
                      'note': 'SANDBOX ONLY: historical demonstration with relaxed statistical and high-tail controls.'}
        assessment = evaluate(candidate, champion, evaluation, policy)
        assessment.update(champion_id=active_id, candidate_id=identifier, historical_demo=historical_demo)
        release = registry.root/'releases'/identifier
        fitting.to_csv(release/'training_features.csv', index=False)
        evaluation.to_csv(release/'evaluation_features.csv', index=False)
        provenance = {'training_sha256': digest(release/'training_features.csv'),
                      'evaluation_sha256': digest(release/'evaluation_features.csv'),
                      'feature_names': FEATURES, 'sample_weights': {'source_weight_budget': reference['selection']['source_weight_budget']}}
        (release/'data_provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
        (release/'evaluation.json').write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding='utf-8')
        registry.event('candidate_evaluated', identifier, assessment)
        if not assessment['approved']:
            registry.event('candidate_rejected', identifier, {'reasons': assessment['reasons']})
            return {'status': 'rejected', 'candidate': identifier, 'active_unchanged': active_id, 'evaluation': assessment}
        registry.activate(identifier, expected_active=active_id, reason='Candidate passed temporal evaluation', evaluation=assessment)
        try:
            registry.validate(identifier)
        except Exception:
            registry.rollback(expected_active=identifier, reason='Post-activation smoke test failed')
            raise
        return {'status': 'promoted', 'candidate': identifier, 'previous': active_id, 'evaluation': assessment}
    except Exception as exc:
        registry.event('retraining_failed', active_id, {'error_type': type(exc).__name__, 'message': str(exc), 'active_after_failure': registry.state()['active']})
        raise


def demo():
    config = load_config()
    registry = Registry(ROOT/'models/mlops_demo'/now_string().replace(':', '-'), sandbox=True)
    baseline = joblib.load(ROOT/f'models/{config["experiment_id"]}/combinado.joblib')
    baseline = {**baseline, 'model': None, 'status': 'sandbox_persistence'}
    baseline_id = registry.register(baseline, {'origin': 'sandbox_persistence_baseline', 'trained_until': None, 'evaluated_until': None})
    registry.activate(baseline_id, expected_active=None, reason='Historical sandbox baseline, not application model')
    first = run(registry, historical_demo=True)
    second = run(registry, historical_demo=True)
    restored = None
    if first['status'] == 'promoted':
        # Restore only after the no-improvement candidate has been rejected.
        registry.event('simulated_post_deployment_failure', first['candidate'], {'simulation': True})
        restored = registry.rollback(expected_active=first['candidate'], reason='SIMULATED failure in historical sandbox')
    report = {'historical_simulation': True, 'application_registry_modified': False, 'registry_path': str(registry.root),
              'initial_baseline': baseline_id, 'first_training': first, 'repeated_training': second,
              'restored': restored, 'final_state': registry.state(), 'events': registry.history(30)}
    output = ROOT/'reports/mlops_demo.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
