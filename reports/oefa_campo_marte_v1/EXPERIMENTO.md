# Experimento OEFA + Campo de Marte

## Resultado

La prueba no demuestra una mejora concluyente al agregar OEFA: el intervalo por días de la diferencia de MAE incluye cero.

La elección por validación fue **combinado**. Ningún modelo se ha desplegado o promovido automáticamente. La prueba mide concentraciones reales y conserva los mismos ejemplos para todos los modelos.

| Entrenamiento / referencia | MAE (µg/m³) | RMSE (µg/m³) | R² |
|---|---:|---:|---:|
| persistencia | 2.0699 | 2.9319 | 0.6040 |
| solo_oefa | 2.0119 | 2.7127 | 0.6610 |
| solo_campo_marte | 2.0849 | 2.9509 | 0.5988 |
| combinado | 2.0177 | 2.8815 | 0.6175 |

Diferencia de MAE combinado menos solo Campo de Marte: **-0.0672 µg/m³**. Intervalo del 95 % mediante remuestreo de días completos: **[-0.1338, 0.0005]**. Negativo favorece la combinación. Este intervalo evalúa incertidumbre dentro del periodo de prueba; no certifica rendimiento en otras estaciones, estaciones del año o condiciones futuras.

## Datos y separación temporal

- Fuente: 15684 observaciones horarias OEFA, de La Huaca y Macacará; solo los registros reconstruibles.
- Destino: 3315 observaciones horarias de Campo de Marte, ubicación 2415, sensor PM2.5 4672, del 01/04/2026 al 15/10/2026.
- Ejemplos supervisados OEFA: 15587.
- Campo de Marte: 2200 ejemplos de entrenamiento, 282 de validación y 270 de prueba.
- Entrenamiento: objetivos anteriores al 16/08/2026. Validación: del 16/08/2026 al 15/09/2026. Prueba: del 16/09/2026 al 15/10/2026, hora peruana.
- Cada ejemplo exige mediciones en t−2, t−1, t y t+1 exactamente separadas una hora y de la misma estación. No se imputan huecos. La evaluación solo representa esos momentos con historial completo y objetivo observado.
- En los 30 días de prueba hay 720 horas de calendario; los 270 ejemplos evaluables representan 37.5% de esas horas. Esto limita la disponibilidad demostrada y debe distinguirse de la precisión sobre ejemplos completos.
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
