# Aplicación local y servicio de predicción

## Demostración histórica

Desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m airepredict serve
```

Abre [la aplicación](http://127.0.0.1:8000) o [la documentación de la API](http://127.0.0.1:8000/docs). Para detenerla desde una terminal propia, usa Ctrl+C.

La aplicación muestra la última ventana completa disponible de Campo de Marte, la última concentración medida y la concentración estimada para la siguiente hora. La fecha histórica aparece en la pantalla; el resultado no se presenta como calidad del aire actual. Los huecos de observación se muestran como cortes del gráfico.

No necesita clave de OpenAQ para esta demostración. Usa el modelo combinado ya entrenado y las mediciones locales preparadas. Los artefactos se generan con `python -m airepredict experiment` si se ejecuta en un equipo nuevo.

## Contrato de predicción

| Ruta | Comportamiento |
|---|---|
| GET /health | Comprueba que el servicio responde |
| GET /api/status | Estado del modelo, disponibilidad de datos y preparación para reentrenar |
| GET /api/demo | Predicción histórica con la última ventana completa del archivo local |
| POST /api/predict | Predicción histórica o de escenario a partir de tres observaciones explícitas |
| GET /api/forecast | Predicción actual únicamente desde observaciones ingresadas por el proceso de ingesta |

POST /api/predict recibe `location_id=2415` y exactamente tres observaciones, cada una con `timestamp` ISO-8601 con zona horaria y `pm25` numérico no negativo en µg/m³. Las observaciones deben corresponder a tres horas exactas consecutivas. Este acceso no acredita procedencia y siempre etiqueta su resultado como histórico, nunca como observación actual verificada.

Todas las respuestas de predicción contienen la fecha de la última medición, la hora objetivo, el modo y la versión experimental del modelo. La construcción de características se comparte con el entrenamiento. La inferencia no necesita conocer el objetivo futuro.

GET /api/forecast exige tres horas consecutivas en el almacén de ingesta. Rechaza observaciones futuras y rechaza como actual cualquier predicción cuya hora objetivo ya haya pasado. No utiliza silenciosamente la demostración histórica cuando faltan datos actuales.

## Conexión en vivo, pendiente de una clave propia

La credencial se lee exclusivamente desde `OPENAQ_API_KEY` en el entorno del proceso de ingesta. El archivo `.env.example` es una plantilla; la aplicación no carga archivos `.env` automáticamente.

Después de configurar la variable localmente:

```powershell
.\.venv\Scripts\python.exe -m airepredict ingest
.\.venv\Scripts\python.exe -m airepredict readiness
```

La ingesta comprueba que el sensor 4672 pertenece a la ubicación 2415 y mide PM2.5. Consulta las últimas 72 horas mediante `/sensors/4672/hours`, con paginación y revisita de registros antiguos para recibir correcciones. Utiliza `period.datetimeTo.utc` como etiqueta de la hora completada. Esta equivalencia con el histórico debe confirmarse con metadatos del proveedor antes de aprobar producción.

Se aceptan intervalos de una hora completos, unidades equivalentes a µg/m³, valores finitos no negativos y cobertura declarada de al menos 75 %. Se excluyen registros marcados por el proveedor y periodos futuros o incompletos. Las respuestas se validaron con pruebas controladas; todavía no se ha confirmado su comportamiento frente a una clave real de OpenAQ.

Los registros se almacenan en `data/live/airepredict.sqlite`. Repetir una ingesta no duplica horas; las correcciones actualizan el valor existente. Si falla una página no se escribe un lote parcial. Los valores contradictorios para una misma hora dentro de un lote se excluyen. El resumen operativo se guarda en `data/live/last_ingestion.json` sin incluir la credencial.

`readiness` exige al menos 168 ejemplos supervisados completos posteriores al periodo de prueba original. Es un indicador de suficiencia de datos; no es una evaluación de calidad predictiva y **no ejecuta reentrenamiento ni promoción**.

## Comprobaciones realizadas

- La suite actual contiene 45 casos, incluyendo registro, recuperación, respaldo y sincronización de modelos: integridad temporal, fronteras de estaciones, inferencia sin objetivo futuro, etiquetas históricas, rechazo de datos antiguos, paginación fallida, duplicados y correcciones.
- La aplicación local se probó con el modelo combinado real y las observaciones históricas preparadas.
- El servicio de salud, las rutas de API y los recursos de interfaz respondieron localmente.
- La conexión autenticada de OpenAQ y la disponibilidad en vivo no se probaron, según la elección de continuar sin clave.

## Integración y despliegue

`.github/workflows/ci.yml` instala el entorno y ejecuta las pruebas en cada push, solicitud de cambios o ejecución manual. El archivo está preparado, pero no se ha ejecutado en GitHub desde esta carpeta.

El `Dockerfile` empaqueta la aplicación, el modelo combinado y los datos de demostración, usa un usuario sin privilegios y escucha en el puerto indicado por `PORT`. `AIRPREDICT_ROOT=/app` señala la carpeta externa de configuración y artefactos. Para construirlo en un equipo con Docker:

```powershell
docker build -t airepredict:demo .
docker run --rm -p 8000:8000 airepredict:demo
```

La imagen no se construyó en este equipo porque Docker no está disponible. El despliegue remoto requiere elegir una plataforma y configurar almacenamiento persistente para los datos de ingesta. La API web no expone una ruta pública para suministrar credenciales ni modificar modelos.

Referencias de contrato: [OpenAQ, mediciones](https://docs.openaq.org/resources/measurements) y [paginación](https://docs.openaq.org/using-the-api/pagination).

## Mantenimiento de modelos

El registro local permite evaluar y activar candidatos, conservar una versión anterior y recuperarla ante fallas o degradación comprobada. La aplicación consulta la versión activa del registro. Procedimiento, controles y límites: [MLOPS.md](MLOPS.md). El registro inicial sigue siendo experimental.

## Actualización del MVP

La aplicación se publica en https://airpredict-4u3c.onrender.com/ con una proyección de estado administrada por GitHub Actions. El contenedor y las pruebas de arranque ya se ejecutan en GitHub. La conexión autenticada sigue dependiendo de una clave propia. Véase [INFORME_TECNICO_MVP.md](INFORME_TECNICO_MVP.md) para la arquitectura actual; las instrucciones locales anteriores conservan su utilidad.

La ingesta autenticada ya se verificó desde GitHub Actions (34 horas aceptadas). En el despliegue gratuito la credencial reside en el trabajo de ingesta, no en el servicio web. `/api/observations` permite consultar las mediciones ingresadas aun cuando falta una ventana fresca para predecir.


## Consulta con últimos datos disponibles

`GET /api/stations/{id}/forecast?mode=latest` ejecuta el modelo con las tres últimas mediciones horarias consecutivas del almacén recibido. Devuelve valor, fecha de entrada, hora objetivo y `target_in_past`; no rechaza una ventana válida solo por antigüedad. `is_current_forecast` únicamente es verdadero si la hora objetivo aún es futura. No registra estimaciones de horas pasadas como pronósticos operativos. El contrato estricto `mode=live` permanece para monitor, widget y notificaciones. Sin tres horas válidas no se inventa una entrada.
