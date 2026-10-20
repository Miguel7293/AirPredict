# AirePredict 0.4 — mapa, modelo general y modelos por distrito

## Qué se entrenó realmente

Se recorrieron los **2.883.877 registros** del CSV OEFA original (SHA-256 `1f09a8064ee0aed0b3a9a0a90b96f63ce226b45a969dace49f73e45134f26d92`). Hay 94.371 filas con PM2.5 numérico válido; la mayoría son horarias y muchas no identifican su hora. Para ampliar el alcance geográfico sin inventar horas se usan **3.879 observaciones explícitas de 24 horas**. No se tratan contaminantes distintos como etiquetas de PM2.5 ni valores ausentes como ceros.

El inventario conserva 34 emplazamientos, identificados por código **y coordenadas** para evitar mezclar lugares con el mismo código. 26 emplazamientos tienen ejemplos en el ajuste del modelo general. Los puntos sin PM2.5 diario permanecen identificados como puntos sin predicción. Los valores del mapa no cubren el espacio entre estaciones ni representan un índice sanitario oficial.

## Modelo general: horizonte diario

`scripts/train_general.py` reproduce la extracción y el entrenamiento. Predice el cambio del PM2.5 diario del día siguiente usando concentración del día observado, concentración del día anterior cuando existe, ubicación, altitud y calendario. Solo se une la etiqueta si corresponde exactamente al día siguiente del mismo emplazamiento. El primer retardo puede ser ausente y se maneja como tal por HistGradientBoosting; la etiqueta nunca se imputa.

Las coordenadas WGS84/UTM de zonas 17S, 18S y 19S se transforman con pyproj a longitud/latitud. Una coordenada de datum desconocido no se convierte por suposición. La biblioteca usa `Transformer.from_crs(..., always_xy=True)`: [documentación de pyproj](https://pyproj4.github.io/pyproj/stable/api/transformer.html).

Se comparan dos configuraciones de HistGradientBoosting (7 y 15 hojas, 160 iteraciones, tasa 0,05, regularización 10, mínimo 25 ejemplos por hoja, semilla 2026, sin parada temprana). Se selecciona únicamente con validación cronológica. El modelo final se ajusta con entrenamiento y validación y **conserva el test sin entrenar**; usar todo el CSV no significa eliminar la evaluación independiente.

| Partición | Ejemplos | Periodo de etiquetas |
|---|---:|---|
| Entrenamiento | 1.627 | anterior al 30/10/2021 |
| Validación | 1.001 | 30/10/2021 a 15/06/2022 |
| Prueba | 1.138 | 16/06/2022 a 31/12/2022 |

El ajuste final contiene 2.628 ejemplos. En prueba: **MAE 2,670 µg/m³, RMSE 3,963, R² 0,692**. Repetir el último valor obtiene MAE 2,770, RMSE 4,074 y R² 0,674. La mejora de MAE es del 3,61% y sigue siendo modesta. No se afirma significancia estadística ni validación en ubicaciones nuevas. En el periodo de prueba solo existen etiquetas de seis emplazamientos: no debe generalizarse esa métrica a todos los puntos del inventario.

Artefactos: `models/general_v1/general.joblib`, `reports/general_v1/training.json`, `reports/general_v1/test_predictions.csv`, `data/processed/oefa_daily.csv`. El modelo general se mantiene congelado en esta versión. Una actualización del dataset requiere ejecutar y revisar un nuevo experimento; el flujo horario no lo reentrena.

## Modelos por estación: horizonte de una hora

Se muestran nombres de distritos: **Jesús María**, **San Borja** y **San Martín de Porres**. La identidad interna OpenAQ y sus sensores se conserva para que cambiar el nombre visible no mezcle series. Son puntos de medición en esos distritos, no cobertura completa de todo el distrito.

| Punto | Location / sensor OpenAQ | MAE test | RMSE | R² | n |
|---|---|---:|---:|---:|---:|
| Jesús María | 2415 / 4672 | 2,018 | 2,881 | 0,617 | 270 |
| San Borja | 2402 / 4492 | 2,733 | 3,883 | 0,805 | 407 |
| San Martín de Porres | 2351 / 4319 | 2,142 | 3,231 | 0,752 | 456 |

Jesús María conserva el experimento combinado original documentado en `INFORME_TECNICO_MVP.md`. Los otros dos modelos se entrenan por separado con observaciones OpenAQ de abril a octubre de 2026. `scripts/train_stations.py` descarga, valida y construye retardos horarios exactos; selecciona entre Ridge, RandomForest, HistGradientBoosting y persistencia usando validación. Se usan cortes cronológicos de aproximadamente 70/15/15 de los ejemplos disponibles, con fronteras en días completos. No se mezclan series ni se completan horas inexistentes.

San Borja seleccionó RandomForest; San Martín de Porres, HistGradientBoosting. Frente a persistencia (MAE 2,768 y 2,157, respectivamente), las mejoras son reducidas. Las métricas son históricas, de periodos y escalas distintas: no se deben comparar directamente con el MAE del modelo diario general.

## MLOps solo para estaciones disponibles

GitHub Actions conserva los horarios de ingestión cada hora, monitorización diaria, evaluación semanal y respaldo diario. Cada sensor tiene base de observaciones, registro de versiones, ejemplos consumidos y métricas independientes. La ingestión usa `/sensors/{id}/hours`, verifica pertenencia del sensor al punto y aplica filtros de unidad, cobertura, flags, intervalos completos y horas futuras. [Documentación de mediciones OpenAQ](https://docs.openaq.org/resources/measurements).

Un reentrenamiento necesita 168 ejemplos completos posteriores al último periodo evaluado o reservado. Se congela la receta, se entrena con datos anteriores y se evalúa en datos posteriores. Se consumen las ventanas incluso si el candidato se rechaza. Se reutilizan los controles de mejora de MAE, persistencia, RMSE, sesgo, concentraciones altas, cobertura e incertidumbre; el modelo anterior permanece activo si los controles fallan. El registro verifica hashes y compatibilidad y permite restaurar una versión anterior.

La monitorización requiere predicciones actuales realmente emitidas y después observadas (50 ejemplos y siete días). Solo restaura automáticamente una versión anterior si se cumplen las reglas de degradación y el respaldo compatible mejora el desempeño en los mismos datos guardados. Nunca se utilizan ejemplos históricos como predicciones actuales para aparentar monitorización en producción.

La rama pública `runtime-state` almacena el estado durable. El servicio gratuito carga instantáneas verificadas cada diez minutos; no guarda la clave OpenAQ. Se conserva la recuperación de la aplicación a un commit anterior validado. Las nuevas comprobaciones del despliegue verifican el mapa y una predicción histórica de cada punto, además de la salud del servicio.

## Web y Android

La web añade inicio con identidad y lema **«El aire, en perspectiva»**, mapa interactivo con filtros, inventario, análisis de series diarias y horarias, selector de año, métricas de concentración, predicciones con fecha y comparación de modelos. El color representa concentración; no una clasificación sanitaria. La aplicación Android añade Inicio, Mapa, Estaciones y Ajustes; el mapa usa la misma interfaz web dentro de un WebView sin acceso a archivos, contenido local ni puentes JavaScript nativos.

La URL pública ya viene configurada. La consulta admite el arranque en frío del servicio gratuito (20 s de conexión y 70 s de lectura), usa solicitudes sin caché y separa los errores de conexión de la ausencia de datos recientes. Una respuesta de datos antiguos ya no se presenta como un fallo de URL. Ajustes permite comprobar `/health`. La caché y las notificaciones separan los distritos; el widget usa el distrito elegido. Las respuestas antiguas de una pantalla no pueden sobrescribir otra selección.

Un toque en «Actualizar» vuelve a consultar el último estado publicado; no obliga al proveedor a entregar datos nuevos. La consulta histórica está identificada como tal y no reemplaza automáticamente la predicción actual cuando falta información reciente.

## Cartografía y dependencias

Se incluye [Leaflet 1.9.4](https://leafletjs.com/download.html) con su licencia BSD. El mapa usa geometría vectorial local de [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) y [geoBoundaries PER ADM1](https://www.geoboundaries.org/api/current/gbOpen/PER/ADM1/) (revisión `90a1d52`, geometría de referencia declarada de dominio público). Los límites departamentales son referenciales y no se usan para determinar la etiqueta o la evaluación del modelo. No se depende de servidores públicos de teselas para mostrar el mapa.
