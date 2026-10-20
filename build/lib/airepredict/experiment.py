"""A fixed temporal experiment; test outcomes never select models or weights."""
import json
import platform
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import ROOT, digest
from .features import FEATURES, make_features, temporal_split


def candidates(seed):
    for alpha in [1.0, 100.0]:
        yield ('ridge', {'alpha': alpha}, Pipeline([('scale', StandardScaler()), ('model', Ridge(alpha=alpha))]))
    for leaves in [7, 15]:
        params = {'max_leaf_nodes': leaves, 'max_iter': 120, 'learning_rate': 0.05,
                  'l2_regularization': 5.0, 'min_samples_leaf': 20, 'early_stopping': False}
        yield ('hist_gradient_boosting', params, HistGradientBoostingRegressor(**params, random_state=seed))
    for leaf in [5, 15]:
        params = {'n_estimators': 100, 'min_samples_leaf': leaf, 'max_depth': 10, 'max_features': 1.0}
        yield ('random_forest', params, RandomForestRegressor(**params, random_state=seed, n_jobs=2))


def training_data(source, target, mode, budget):
    if mode == 'solo_oefa':
        return source.reset_index(drop=True), np.ones(len(source))
    if mode == 'solo_campo_marte':
        return target.reset_index(drop=True), np.ones(len(target))
    frame = pd.concat([source, target], ignore_index=True)
    # budget is the aggregate OEFA weight relative to aggregate target weight.
    weights = np.r_[np.full(len(source), budget*len(target)/len(source)), np.ones(len(target))]
    return frame, weights


def fit(model, frame, weights):
    delta = frame['y']-frame['pm25_now']
    if isinstance(model, Pipeline):
        model.fit(frame[FEATURES], delta, scale__sample_weight=weights, model__sample_weight=weights)
    else:
        model.fit(frame[FEATURES], delta, sample_weight=weights)
    return model


def predict(model, frame):
    # The regressor learns the next-hour change. Public output is concentration.
    delta = np.zeros(len(frame)) if model is None else model.predict(frame[FEATURES])
    return np.maximum(0, frame['pm25_now'].to_numpy()+delta)


def metrics(y, prediction):
    return {'mae': float(mean_absolute_error(y, prediction)),
            'rmse': float(np.sqrt(mean_squared_error(y, prediction))),
            'r2': float(r2_score(y, prediction)),
            'bias': float(np.mean(prediction-np.asarray(y))), 'n': len(y)}


def paired_daily_bootstrap(test, first, second, seed):
    # Resample complete observed days, preserving within-day dependence.
    frame = pd.DataFrame({'day': test['target_time'].dt.tz_convert('Etc/GMT+5').dt.date,
                          'difference': np.abs(test['y'].to_numpy()-first)-np.abs(test['y'].to_numpy()-second)})
    daily = frame.groupby('day')['difference'].agg(['sum', 'count'])
    rng = np.random.default_rng(seed)
    choices = rng.integers(0, len(daily), size=(2000, len(daily)))
    differences = daily['sum'].to_numpy()[choices].sum(axis=1)/daily['count'].to_numpy()[choices].sum(axis=1)
    return {'mae_difference_first_minus_second': float(frame['difference'].mean()),
            'ci95_daily_bootstrap': [float(x) for x in np.quantile(differences, [0.025, 0.975])],
            'observed_days': len(daily), 'replications': 2000,
            'interpretation': 'Negativo favorece al primer modelo; un intervalo que contiene cero no respalda una mejora concluyente.'}


def coverage(frame):
    stats = []
    for (source, station), group in frame.groupby(['source', 'station']):
        stamps = pd.to_datetime(group['timestamp'], utc=True)
        local = stamps.dt.tz_convert('Etc/GMT+5')
        period = local.dt.strftime('%Y-%m')
        for month, block in group.groupby(period):
            times = pd.to_datetime(block['timestamp'], utc=True)
            stats.append({'source': source, 'station': station, 'month': month,
                          'observations': len(block), 'first_utc': str(times.min()), 'last_utc': str(times.max()),
                          'zeros': int(block['pm25'].eq(0).sum()), 'mean_pm25': float(block['pm25'].mean())})
    return stats


def run(config, source_measurements, target_measurements, source_stats, target_stats, manifest):
    source = make_features(source_measurements)
    target = make_features(target_measurements)
    train, validation, test = temporal_split(target, config['validation_start'], config['test_start'])
    if len(source) < 300 or len(train) < 300 or min(len(validation), len(test)) < 100:
        raise ValueError(f'Ejemplos insuficientes: OEFA={len(source)}, entrenamiento={len(train)}, validación={len(validation)}, prueba={len(test)}')
    cutoff = pd.Timestamp(config['validation_start'], tz='Etc/GMT+5').tz_convert('UTC')
    if not (source['target_time'] < cutoff).all():
        raise ValueError('El histórico fuente contiene objetivos posteriores al corte de entrenamiento')
    print(f'Ejemplos: OEFA={len(source)}, Campo de Marte train={len(train)}, val={len(validation)}, test={len(test)}', flush=True)
    output = ROOT / 'reports' / config['experiment_id']
    models = ROOT / 'models' / config['experiment_id']
    output.mkdir(parents=True, exist_ok=True)
    models.mkdir(parents=True, exist_ok=True)
    all_candidates, chosen = [], {}
    for mode in ['solo_oefa', 'solo_campo_marte', 'combinado']:
        best = None
        budgets = config['source_weight_budgets'] if mode == 'combinado' else [None]
        for budget in budgets:
            fitting, weights = training_data(source, train, mode, budget)
            for family, params, estimator in candidates(config['random_seed']):
                fit(estimator, fitting, weights)
                score = metrics(validation['y'], predict(estimator, validation))
                entry = {'mode': mode, 'family': family, 'params': params, 'source_weight_budget': budget,
                         'validation': score, 'training_rows': len(fitting)}
                all_candidates.append(entry)
                if best is None or score['mae'] < best[0]['validation']['mae']:
                    best = entry, clone(estimator)
        chosen[mode] = best
        print(f'{mode}: MAE validación={best[0]["validation"]["mae"]:.4f}, {best[0]["family"]}, presupuesto={best[0]["source_weight_budget"]}', flush=True)
    persistence_validation = metrics(validation['y'], predict(None, validation))
    # Freeze the champion choice using validation only, before inspecting test metrics.
    validation_scores = {'persistencia': persistence_validation['mae'],
                         **{mode: pair[0]['validation']['mae'] for mode, pair in chosen.items()}}
    champion = min(validation_scores, key=validation_scores.get)
    train_validation = pd.concat([train, validation], ignore_index=True)
    summary, predictions = {}, {'persistencia': predict(None, test)}
    summary['persistencia'] = {'validation': persistence_validation,
                              'test': metrics(test['y'], predictions['persistencia'])}
    for mode, (selection, estimator) in chosen.items():
        fitting, weights = training_data(source, train_validation, mode, selection['source_weight_budget'])
        fit(estimator, fitting, weights)
        predictions[mode] = predict(estimator, test)
        bundle = {'model': estimator, 'features': FEATURES, 'predicts': 'delta_pm25_t_plus_1',
                  'clip_output_at_zero': True, 'config': config, 'selection': selection,
                  'status': 'experimental_no_promovido', 'sklearn_version': sklearn.__version__}
        joblib.dump(bundle, models / f'{mode}.joblib')
        # Verify the persisted estimator reproduces the exact predictions.
        restored = joblib.load(models / f'{mode}.joblib')
        np.testing.assert_allclose(predict(restored['model'], test), predictions[mode], rtol=0, atol=1e-12)
        summary[mode] = {**selection, 'refit_rows': len(fitting), 'test': metrics(test['y'], predictions[mode])}
    test_output = test[['timestamp', 'target_time', 'station', 'y']].copy()
    for mode, values in predictions.items():
        test_output['prediction_'+mode] = values
    test_output.to_csv(output / 'predicciones_prueba.csv', index=False)
    comparisons = {f'combinado_vs_{other}': paired_daily_bootstrap(test, predictions['combinado'], predictions[other], config['random_seed'])
                   for other in ['solo_campo_marte', 'persistencia']}
    result = {
        'experiment_id': config['experiment_id'], 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'config': config, 'features': FEATURES, 'target_definition': 'PM2.5 de t+1 hora; el regresor estima el cambio respecto a t',
        'evaluation': 'walk-forward a una hora con observaciones reales disponibles en cada emisión; no es pronóstico recursivo de todo el mes',
        'selection': 'MAE en validación; prueba reservada; modelos elegidos se reentrenan con train+val antes de la prueba',
        'champion_selected_on_validation': champion, 'status': 'experimental_no_desplegado',
        'rows': {'source_features': len(source), 'target_features': len(target), 'train': len(train), 'validation': len(validation), 'test': len(test)},
        'split_ranges': {name: {'first_outcome_utc': str(frame['target_time'].min()), 'last_outcome_utc': str(frame['target_time'].max())}
                         for name, frame in [('train', train), ('validation', validation), ('test', test)]},
        'summary': summary, 'comparisons': comparisons, 'candidates': all_candidates,
        'data_quality': {'source': source_stats, 'target': target_stats, 'monthly_observations': coverage(pd.concat([source_measurements, target_measurements]))},
        'provenance': {'manifest_sha256': digest(ROOT / f'data/raw/openaq/{config["target_location_id"]}/manifest.json'),
                       'oefa_processed_sha256': digest(ROOT / 'data/processed/oefa_hourly.csv'),
                       'target_processed_sha256': digest(ROOT / 'data/processed/campo_marte_hourly.csv')},
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__, 'sklearn': sklearn.__version__, 'joblib': joblib.__version__}}
    (output / 'resultados.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    pd.DataFrame([{'mode': mode, **record['test']} for mode, record in summary.items()]).to_csv(output / 'metricas_prueba.csv', index=False)
    write_report(result, output)
    print(json.dumps({'champion_validation': champion, 'test': {k: v['test'] for k, v in summary.items()}, 'comparisons': comparisons}, ensure_ascii=False, indent=2), flush=True)


def write_report(result, output):
    rows = []
    for mode, record in result['summary'].items():
        score = record['test']
        rows.append(f'| {mode} | {score["mae"]:.4f} | {score["rmse"]:.4f} | {score["r2"]:.4f} |')
    difference = result['comparisons']['combinado_vs_solo_campo_marte']
    low, high = difference['ci95_daily_bootstrap']
    if high < 0:
        conclusion = 'El combinado mejora al modelo entrenado solo con Campo de Marte en esta prueba; el intervalo por días también favorece la combinación.'
    elif low > 0:
        conclusion = 'El combinado empeora al modelo entrenado solo con Campo de Marte en esta prueba. No se justifica incorporar OEFA al modelo operativo con esta configuración.'
    else:
        conclusion = 'La prueba no demuestra una mejora concluyente al agregar OEFA: el intervalo por días de la diferencia de MAE incluye cero.'
    source_stats = result['data_quality']['source']
    target_stats = result['data_quality']['target']
    text = f'''# Experimento OEFA + Campo de Marte

## Resultado

{conclusion}

La elección por validación fue **{result['champion_selected_on_validation']}**. Ningún modelo se ha desplegado o promovido automáticamente. La prueba mide concentraciones reales y conserva los mismos ejemplos para todos los modelos.

| Entrenamiento / referencia | MAE (µg/m³) | RMSE (µg/m³) | R² |
|---|---:|---:|---:|
{chr(10).join(rows)}

Diferencia de MAE combinado menos solo Campo de Marte: **{difference['mae_difference_first_minus_second']:.4f} µg/m³**. Intervalo del 95 % mediante remuestreo de días completos: **[{low:.4f}, {high:.4f}]**. Negativo favorece la combinación. Este intervalo evalúa incertidumbre dentro del periodo de prueba; no certifica rendimiento en otras estaciones, estaciones del año o condiciones futuras.

## Datos y separación temporal

- Fuente: {source_stats['accepted']} observaciones horarias OEFA, de La Huaca y Macacará; solo los registros reconstruibles.
- Destino: {target_stats['accepted']} observaciones horarias de Campo de Marte, ubicación 2415, sensor PM2.5 4672, del 01/04/2026 al 15/10/2026.
- Ejemplos supervisados OEFA: {result['rows']['source_features']}.
- Campo de Marte: {result['rows']['train']} ejemplos de entrenamiento, {result['rows']['validation']} de validación y {result['rows']['test']} de prueba.
- Entrenamiento: objetivos anteriores al 16/08/2026. Validación: del 16/08/2026 al 15/09/2026. Prueba: del 16/09/2026 al 15/10/2026, hora peruana.
- Cada ejemplo exige mediciones en t−2, t−1, t y t+1 exactamente separadas una hora y de la misma estación. No se imputan huecos. La evaluación solo representa esos momentos con historial completo y objetivo observado.
- En los 30 días de prueba hay 720 horas de calendario; los {result['rows']['test']} ejemplos evaluables representan {result['rows']['test']/720:.1%} de esas horas. Esto limita la disponibilidad demostrada y debe distinguirse de la precisión sobre ejemplos completos.
- Un objetivo de validación nunca forma parte del entrenamiento inicial. Tras congelar hiperparámetros y ponderaciones, se reentrena con entrenamiento y validación antes de evaluar la prueba reservada.

## Adaptación aplicada

Se normalizaron nombres, unidades y referencias temporales. Se conservaron procedencia, estación e identificador de sensor. La Huaca y Macacará no se renombraron como Campo de Marte.

El regresor aprende el cambio de PM2.5 de t a t+1; la salida suma ese cambio al valor actual y limita la concentración mínima a cero. Las entradas usan el valor actual, dos retardos horarios, promedio de tres observaciones, cambio reciente y representaciones cíclicas de hora y día de la semana. No se usan meteorología ni datos futuros como entradas.

Se compararon Ridge, Random Forest e HistGradientBoosting con seis configuraciones por régimen de ponderación. En el combinado se probaron presupuestos totales OEFA de 0,1, 0,5 y 1,0 respecto al peso total de Campo de Marte. Así, el mayor tamaño del CSV OEFA no domina automáticamente el entrenamiento. Esta ponderación por procedencia es una adaptación empírica; no es una corrección de calibración ni una estimación formal del cociente de densidades.

La selección usa MAE en validación y considera también persistencia. El conjunto de prueba no selecciona el modelo, sus hiperparámetros, las fuentes ni sus pesos. Los resultados completos y las configuraciones candidatas están en [resultados.json](resultados.json); las predicciones individuales están en [predicciones_prueba.csv](predicciones_prueba.csv).

## Límites que siguen abiertos

1. OEFA no explicita zona horaria en el CSV. Se asumió UTC−05; la fecha base 1899-12-31 se interpretó como medianoche. La equivalencia exacta entre la etiqueta de inicio de intervalo OEFA y la etiqueta OpenAQ necesita el diccionario original.
2. Los archivos OpenAQ no proporcionan aquí una certificación de calibración o todos los indicadores instrumentales. Los ceros válidos se conservaron; no se inventaron valores faltantes.
3. Los datos AWS son históricos y tienen retraso publicado de 72 horas. Esta ejecución no constituye una predicción en vivo. Para la aplicación aún se necesita comprobar la API autenticada y la frescura del sensor.
4. La prueba se limita a un periodo de 30 días de una estación. Las ventanas incompletas se excluyen; debe medirse también la disponibilidad de predicciones en producción.
5. Los modelos se guardan como experimentales. Faltan aplicación, registro operacional, ingesta por API, despliegue y pipelines CI/CD para completar el producto del curso.

## Reproducibilidad

Configuración: `config/experiment.json`. Comando: `python -m airepredict experiment`. Los archivos originales se conservan; las descargas se almacenan en caché con SHA-256 y manifiesto. Las versiones efectivas de Python y bibliotecas están en resultados.json. Una repetición sin `--refresh` reutiliza las copias descargadas. Las transformaciones se construyen por estación mediante coincidencias exactas de tiempo, sin desplazar filas a través de huecos.

Referencias: [archivo público OpenAQ](https://docs.openaq.org/aws/about), [mediciones e intervalos OpenAQ](https://docs.openaq.org/resources/measurements), [validación temporal](https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split).
'''
    (output / 'EXPERIMENTO.md').write_text(text, encoding='utf-8')
