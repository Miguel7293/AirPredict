# AirePredict Perú

Base experimental para predecir PM2.5 de Campo de Marte a una hora, aprovechando histórico OEFA de La Huaca y Macacará mediante entrenamiento ponderado.

## Estado actual

Se implementaron la aplicación web local, el servicio de predicción, la demostración histórica, la descarga y validación de datos, y la comparación temporal de modelos. La interfaz está en inglés para la exposición del curso. **La demostración usa datos históricos; no se ha desplegado en producción ni verificado la conexión autenticada de OpenAQ.**

Para abrir la aplicación:

```powershell
.\.venv\Scripts\python.exe -m airepredict serve
```

Después visita [http://127.0.0.1:8000](http://127.0.0.1:8000). Instrucciones del servicio y la ingesta: [docs/SERVICIO.md](docs/SERVICIO.md).

El experimento combinado tiene MAE de **2,0177 µg/m³** sobre 270 ejemplos de prueba. Solo Campo de Marte obtiene 2,0849 y persistencia 2,0699. La mejora observada de la combinación es aproximadamente 3,22 % frente al entrenamiento solo con Campo de Marte, pero el intervalo del 95 % por días incluye cero. No se presenta como una mejora demostrada. El registro inicial conserva su condición experimental; los nuevos candidatos deben superar controles antes de activarse.

Informe del experimento: [EXPERIMENTO.md](reports/oefa_campo_marte_v1/EXPERIMENTO.md). Auditoría previa: [COMPATIBILIDAD.md](audit/COMPATIBILIDAD.md).

Reporte detallado del entrenamiento, con hiperparámetros, selección, métricas y gráficos: [REPORTE_ENTRENAMIENTO.md](reports/oefa_campo_marte_v1/REPORTE_ENTRENAMIENTO.md).

## Ejecución en Windows

Desde la carpeta del proyecto, con Python 3.11 o posterior:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m airepredict experiment
```

Las versiones de requirements.txt corresponden al entorno de la ejecución inicial. En este equipo ya está preparado `.venv`.

Comandos disponibles:

```powershell
# Descarga y comprueba los archivos públicos de Campo de Marte.
.\.venv\Scripts\python.exe -m airepredict download

# Prepara ambas fuentes sin entrenar.
.\.venv\Scripts\python.exe -m airepredict prepare

# Reproduce entrenamiento y evaluación con las copias almacenadas.
.\.venv\Scripts\python.exe -m airepredict experiment

# Consulta nuevamente los archivos; puede incorporar correcciones del proveedor.
.\.venv\Scripts\python.exe -m airepredict download --refresh
```

La configuración está en [config/experiment.json](config/experiment.json). El histórico OEFA original debe conservarse en `Dataset/`; no se modifica. La descarga pública de OpenAQ no necesita credenciales. Para la ingesta por API habrá que configurar una clave propia fuera del código.

## Organización

| Ubicación | Función |
|---|---|
| Dataset/ | CSV original del usuario |
| audit/ | Auditoría inicial, cruces de estaciones y muestras verificadas |
| config/experiment.json | Estación, sensor, fechas, fuentes, cortes y ponderaciones |
| src/airepredict/data.py | Descarga con caché, manifiesto, hashes y preparación de registros |
| src/airepredict/features.py | Características por hora exacta y estación; separación por fecha del objetivo |
| src/airepredict/experiment.py | Búsqueda de hiperparámetros, comparación, incertidumbre y persistencia de modelos |
| src/airepredict/service.py | API de predicción y comprobación de frescura |
| src/airepredict/live.py | Ingesta autenticada, deduplicación y almacenamiento SQLite |
| src/airepredict/static/ | Interfaz en inglés y gráfico de observaciones |
| tests/ | Comprobaciones de separación temporal, huecos, estaciones y duplicados |
| data/raw/ | Copias comprimidas y manifiesto de OpenAQ; excluidas del control de versiones |
| data/processed/ | Mediciones normalizadas y estadísticas de limpieza |
| models/ | Modelos experimentales y registro local de versiones con activación controlada |
| reports/ | Métricas, predicciones reservadas e informe reproducible |

Los modelos guardados se verificaron comparando sus predicciones tras volver a cargarlos.

## Diseño del experimento

- Destino: Campo de Marte, ubicación OpenAQ 2415, sensor PM2.5 4672.
- Horizonte: una hora, con PM2.5 numérico en µg/m³.
- Fuente: segmentos horarios reconstruibles de CA-MAC-01 y CA-HUA-01, en 2021–2022.
- Destino descargado: 198 días, del 01/04/2026 al 15/10/2026. Se obtuvieron 181 archivos y 17 fechas respondieron 404; las ausencias permanecen visibles en el manifiesto.
- Entrenamiento: antes del 16/08/2026. Validación: 16/08–15/09. Prueba: 16/09–15/10, hora peruana.
- Entradas: PM2.5 actual, dos retardos, promedio de tres horas, cambio reciente, hora y día de semana cíclicos.
- Modelos: Ridge, Random Forest e HistGradientBoosting. Cada uno estima el cambio horario y la salida se convierte de nuevo en concentración.
- Regímenes: solo OEFA, solo Campo de Marte y combinación con presupuesto total OEFA de 0,1, 0,5 o 1 respecto al peso de destino.
- Referencia: persistencia, que mantiene el último valor medido.
- Selección: MAE de validación. Después se reentrenan las configuraciones elegidas con entrenamiento y validación, y se evalúan una vez en la prueba reservada.

La combinación fue elegida por validación. En prueba, solo OEFA obtuvo un MAE ligeramente menor; ese resultado no se utilizó para cambiar la selección a posteriori. Una siguiente iteración de ajuste necesita un nuevo periodo de confirmación o una validación temporal anidada; la prueba actual ya fue consultada.

## Límites y siguiente etapa del producto

El archivo público AWS tiene retraso documentado de 72 horas. Sirve para entrenamiento histórico y esta evaluación retrospectiva, pero no alimenta por sí solo una predicción actual a una hora. La ingesta por API debe comprobar la frescura específica del sensor.

La preparación usa supuestos explícitos de hora peruana, medianoche Excel y etiqueta horaria OEFA. Falta contrastar el diccionario original. No se rellenan horas desconocidas ni se convierten promedios diarios en observaciones horarias.

La aplicación y el servicio funcionan localmente. La ingesta por API está implementada y probada con respuestas controladas; falta verificarla con una clave propia. Se incluyó un flujo CI para pruebas en GitHub y un contenedor para el despliegue. Este equipo no dispone de Docker para comprobar la imagen y el flujo CI todavía no se ha ejecutado en GitHub.

Se implementaron el registro local de versiones, el reentrenamiento con evaluación de candidatos y la reversión. Véase [docs/MLOPS.md](docs/MLOPS.md). Faltan la conexión real de ingesta, la ejecución periódica y el despliegue remoto con almacenamiento persistente. El comando `readiness` solo informa si hay suficientes ejemplos nuevos: no entrena ni promueve un modelo. Los modelos actuales permanecen experimentales.
