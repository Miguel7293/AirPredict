# Guía de estudio: DevOps y MLOps en AirePredict

Documento para estudiar los procesos de integración continua, despliegue, operación y ciclo de vida de modelos de este proyecto. Todo lo descrito aquí está implementado en el código de este repositorio; las referencias a archivos sirven para verificar cada afirmación.

---

## 1. Visión general del sistema

AirePredict es una aplicación que predice PM2.5 (material particulado) una hora adelante. Constado de cuatro piezas:

| Pieza | Tecnología | Rol |
|---|---|---|
| Servicio web | Python 3.12 + FastAPI + uvicorn (1 proceso) | Sirve la interfaz y la API de predicción |
| Infraestructura | Docker + Render (plan gratuito) | Ejecuta el contenedor público en HTTPS |
| Automatización | GitHub Actions (5 workflows) | CI/CD, mantenimiento de modelos, respaldos, Android |
| Estado durable | Rama `runtime-state` del propio repo | Mediciones, registro SQLite de modelos y artefactos |

### Arquitectura (patrón clave: «servicio inmutable + estado externo»)

```
                    ┌────────────────────────────────────────────┐
  push a main ────► │ GitHub Actions                             │
                    │  ci.yml ──► deploy.yml                     │
                    │     │            │ construye imagen GHCR   │
                    │     │            │ despliega en Render     │
                    │     │            │ verifica /ready         │
                    │     ▼            ▼                         │
                    │  operaciones.yml (cron) ──► state_job.py   │
                    │   ingesta / retrain / monitor / backup     │
                    └───────────────┬────────────────────────────┘
                                    │ commit (único escritor)
                                    ▼
                    ┌────────────────────────────────────────────┐
                    │ Rama runtime-state (pública)               │
                    │  data/live/*.sqlite  models/registry/      │
                    │  data/processed/  state.json  reports/     │
                    └───────────────┬────────────────────────────┘
                                    │ descarga ZIP cada 10 min (solo lectura)
                                    ▼
   Usuario ──HTTPS──► ┌────────────────────────────────────────────┐
                      │ Contenedor Render (boot.py)               │
                      │  symlink atómico: current -> snapshot     │
                      │  FastAPI lee el modelo activo del registro│
                      └────────────────────────────────────────────┘
```

Ideas que hay que entender bien:

1. **El servicio web no entrena ni escribe estado.** No tiene credencial de escritura de GitHub; solo consume copias completas publicadas (`src/airepredict/state_sync.py`, docstring inicial).
2. **GitHub Actions es el único escritor** del estado y de la aplicación. Eso elimina condiciones de carrera entre servidor y mantenimiento.
3. **El estado tiene la misma forma que el seed del contenedor** (config, data/processed, modelos, reports), por eso el servidor puede arrancar desde cero y sustituir su copia por la publicada.
4. **La rama `main` es código; `runtime-state` es estado.** La rama de estado es pública: solo datos ambientales y metadatos técnicos, nunca secretos.

---

## 2. DevOps: integración y despliegue continuo

### 2.1 Los cinco workflows (`.github/workflows/`)

| Archivo | Disparador | Qué hace |
|---|---|---|
| `ci.yml` | push, PR, manual, llamada desde deploy | 50 pruebas Python + smoke tests de cliente (Node) + construcción y arranque del contenedor con predicciones reales |
| `deploy.yml` | push a `main`, manual | Valida con CI, publica imagen en GHCR etiquetada por SHA, despliega ese commit en Render y verifica; si falla, recupera la versión anterior |
| `operations.yml` | cron + manual | Mantenimiento del modelo: ingesta, reentrenamiento, monitorización, respaldo, demo, recuperación |
| `rollback.yml` | manual (con SHA) | Recupera una versión de la aplicación que tuvo una entrega previa correcta |
| `android.yml` | cambios en `android/**`, manual | Compila y analiza la APK; con ejecución manual, además prueba en emulador Android 15 |

### 2.2 CI (`ci.yml`) — qué comprueba

1. Instala `requirements.txt` y el paquete con `pip install -e . --no-deps` en Python 3.12.
2. `python -m pytest -q` → 50 pruebas (integridad temporal, registro, recuperación, respaldo, sincronización, etc.).
3. Smoke tests de cliente en Node (`client_smoke.mjs`, `nearby_smoke.mjs`, `atlas_smoke.mjs`).
4. **Prueba el producto empaquetado, no solo el código:**
   - `docker build` con `APP_COMMIT=$GITHUB_SHA` y `docker run`.
   - Espera a que `/ready` responda (hasta 60 s).
   - `/api/demo` debe devolver `mode=historical`, `is_current_forecast=false` y `predicted_pm25 >= 0`.
   - `/api/atlas`, Leaflet (>100 KB), GeoJSON de 26 departamentos, experimento Puno, y las tres estaciones (2415, 2402, 2351) en modo histórico.

Concepto importante: esto es **smoke test de despliegue** — verifica que el artefacto final (contenedor) arranca y predice, no solo que las unitarias pasan.

### 2.3 CD (`deploy.yml`) — el flujo de entrega

```
push a main
  └─► job validate: llama a ci.yml (workflow_call)
  └─► job deploy (solo si validate pasó):
        1. login en ghcr.io con GITHUB_TOKEN
        2. docker/build-push-action: imagen ghcr.io/<repo>:<sha>, caché GHA
        3. previous_deployment.py → consulta GET /ready de la app actual
           y guarda PREVIOUS_COMMIT (el último commit sano público)
        4. Antes de desplegar: si main ya tiene un commit más nuevo que
           este SHA, NO despliega (DEPLOY_SUPERSEDED) — evita que una
           ejecución vieja pise a una más nueva
        5. POST al hook de Render (RENDER_DEPLOY_HOOK) con &ref=<sha>
           → Render despliega exactamente ese commit
        6. check_deployment.py → hasta 90 intentos × 10 s:
           - GET /ready: commit == esperado y modelo cargando
           - GET /api/demo: predicción histórica válida
           - /api/atlas, Leaflet, GeoJSON, 3 estaciones
        7. Si la verificación falla y existe PREVIOUS_COMMIT:
           rollback_application.py re-despliega el commit anterior
```

Detalles de seguridad y robustez que conviene recordar:

- `concurrency: production-deployment` con `cancel-in-progress: false`: entregas y recuperaciones **se serializan**, nunca compiten.
- El entorno de GitHub `production` protege el job con sus variables y secretos.
- El despliegue usa el **mecanismo de deploy hook de Render** con auto-deploy desactivado (`render.yaml: autoDeployTrigger: off`), para que solo un despliegue validado por CI llegue a producción.
- `rollback_application.py` **se niega** a restaurar cualquier SHA: exige que exista un workflow run exitoso de `deploy.yml` para ese commit («solo se recupera lo que se entregó correctamente antes»).

### 2.4 Contenedor (`Dockerfile`)

- Base: `python:3.12-slim`.
- Copia el seed completo: `src/`, `config/`, datos procesados, modelos (combinado, general, estaciones, Puno) y reports.
- `useradd appuser`: corre sin privilegios.
- Variables: `AIRPREDICT_ROOT=/var/data` (estado externo), `AIRPREDICT_SEED=/app` (imagen inmutable), `APP_COMMIT` (identifica el commit dentro del contenedor; lo expone `/ready`).
- `CMD python -m airepredict.boot` — el boot hace la sincronización de estado antes de servir.

### 2.5 Arranque y sincronización de estado (`boot.py` + `state_sync.py`)

`boot.py` (proceso de arranque del contenedor):

1. Si existe `STATE_SYNC_REPOSITORY`, llama a `state_sync.synchronize()`. Si falla, usa la semilla histórica incluida en la imagen (degradación elegida, no error fatal).
2. Copia seeds de estaciones nuevas si el estado publicado es anterior a esta versión de la app (nunca sobrescribe un registro existente).
3. Si no hay estado publicado (`state.json` ausente), copia el seed desde la imagen.
4. Baja de privilegios a `appuser` si corre como root.
5. `initialize()` — registra el modelo inicial si el registro está vacío.
6. Arranca el hilo de sincronización (cada 600 s) y uvicorn con **1 worker** (requisito: un solo proceso para los locks de SQLite).

`state_sync.synchronize()` — la actualización en caliente:

1. Solo acepta el repositorio configurado (`Miguel7293/AirPredict`): repositorio de estado de confianza.
2. `GET https://api.github.com/repos/.../git/ref/heads/runtime-state` → obtiene el SHA de la rama (valida que sean 40 hexadecimales).
3. Si el symlink actual ya apunta a ese SHA, no hace nada (idempotente).
4. Descarga el ZIP del snapshot (`codeload.github.com/.../zip/<sha>`) con límite de 25 MB; al descomprimir, límite de 100 MB; solo acepta rutas bajo `models/`, `data/`, `config/`, `reports/`, `requirements.txt`, `state.json` y bloquea `..` (protección contra path traversal).
5. **Valida antes de exponer**: exige `state.json`, `PRAGMA integrity_check` del SQLite del registro, y que el hash SHA-256 del `model.joblib` activo coincida con su manifiesto.
6. **Conmutación atómica**: crea `current.next` como symlink al nuevo directorio y usa `os.replace` para reemplazar `current`. O se sirve la copia vieja completa o la nueva completa; nunca una mezcla.
7. Si cualquier paso falla, conserva la última copia válida.

### 2.6 Recuperación de la aplicación

Dos niveles distintos (¡no confundir en el examen!):

| Nivel | Mecanismo | Quién |
|---|---|---|
| Recuperación de **software** (versión de la app) | `rollback.yml` o recuperación automática en `deploy.yml` | GitHub Actions + deploy hook de Render |
| Recuperación de **modelo** (versión del predictor) | `registry.rollback()` / monitor por degradación | Registro local SQLite + `state_job.py` |

Procedimiento manual: `rollback.yml` → pides el SHA completo de una entrega anterior → `rollback_application.py` verifica que ese SHA tenga un `deploy.yml` exitoso → llama al hook de Render con ese SHA → verifica `/ready` y `/api/demo`.

### 2.7 Android como parte del pipeline

- `assembleDebug lintDebug` en cada push/PR que toque `android/**` (build + análisis estático con Android Lint).
- APK firmada para pruebas (debug), no publicación en Play Store.
- `APP_BASE_URL` se inyecta en compilación (`buildConfigField`) y se **valida con regex HTTPS** — un origen inseguro rompe la compilación.
- Ejecución manual añade un trabajo con emulador Android 15 (KVM), pruebas instrumentadas (widget, notificaciones, orígenes inseguros) y capturas como evidencia.
- Artefactos con retención de 30 días.

### 2.8 Secretos y configuración

| Nombre | Tipo | Uso |
|---|---|---|
| `APP_BASE_URL` | variable | Origen HTTPS público de la app; validado en la APK y en los scripts de verificación |
| `RENDER_DEPLOY_HOOK` | secreto | Hook de despliegue de Render; jamás se registra en logs (solo se usa en curl interno) |
| `OPENAQ_API_KEY` | secreto (opcional) | Ingesta autenticada; reside solo en los trabajos de Actions, nunca en el contenedor web ni en el APK |
| `GITHUB_TOKEN` | temporal | Token del propio job; permite push a `runtime-state` sin secretos permanentes |

Reglas: credenciales nunca en el código, modelos, APK ni en la rama `runtime-state` (que es pública).

---

## 3. MLOps: ciclo de vida del modelo

### 3.1 Registro de modelos (`src/airepredict/registry.py`)

Base de datos SQLite en `models/registry/registry.sqlite` con tres tablas:

| Tabla | Contenido |
|---|---|
| `releases` | id → manifiesto JSON de cada versión |
| `state` | punteros `active` y `previous` (y bloqueos `blocked:<id>`) |
| `events` | auditoría inmutable: `registered`, `activated`, `candidate_evaluated`, `candidate_rejected`, `evaluation_reserved`, `rolled_back`, `monitoring`, `retraining_failed`, etc. |

Cada release es **inmutable** y vive en `models/registry/releases/<id>/` con:

- `model.joblib` (bundle con modelo, selección y configuración)
- código fuente congelado (`features.py`, `experiment.py`, `service.py`, `data.py`)
- `requirements.txt` (versiones del entorno)
- `manifest.json` con **SHA-256 del modelo y de features.py**, versión de sklearn/numpy/pandas, configuración y metadatos de entrenamiento
- tras un reentrenamiento: `training_features.csv`, `evaluation_features.csv`, `data_provenance.json` (hashes de los datos usados), `evaluation.json`

Contratos verificados en `register()` y `validate()`:

1. Versión de scikit-learn idéntica a la del runtime (si no, «restore its application environment first»).
2. Contrato de características (`FEATURES`) y de salida (`delta_pm25_t_plus_1`) idénticos.
3. Mismo `target_location_id` y `target_sensor_id`.
4. Hash SHA-256 del archivo del modelo == manifiesto.
5. **Smoke test de predicción**: una fila sintética debe producir un valor finito y no negativo.

Activación transaccional con *compare-and-swap*:

```sql
BEGIN IMMEDIATE;
-- solo activa si 'active' sigue siendo el que el evaluador suponía
```

Si otro proceso cambió el activo mientras evaluábamos, la activación falla y hay que reevaluar. Además, `activate()` exige una evaluación aprobada que corresponda exactamente al par (candidato, campeón); una demo histórica (sandbox) **nunca** puede autorizar una promoción real.

El rollback consume el puntero `previous` (queda NULL) para no oscilar automáticamente de vuelta a un modelo fallido, y puede marcar `blocked:<id>` para que un modelo fallido no pueda reactivarse.

### 3.2 Política de promoción (`config/promotion_policy.json`)

Un candidato solo sustituye al activo si pasa **todos** los controles (implementados en `maintenance.evaluate`):

| Control | Umbral | Significado |
|---|---|---|
| `enough_examples` | ≥ 100 | Muestra mínima en la ventana de evaluación |
| `enough_observed_days` | ≥ 7 días | Ventana con días observados suficientes |
| `sufficient_coverage` | ≥ 35 % | Cobertura horaria de la ventana (evita aprobar con huecos) |
| `mae_improves_active` | mejora relativa ≥ 2 % y MAE menor | Debe mejorar al campeón, no empatar |
| `beats_persistence` | MAE < persistencia | Debe ganar al baseline trivial (repite el último valor) |
| `rmse_acceptable` | RMSE ≤ 1,02 × RMSE activo | No puede descontrolar los errores grandes |
| `bias_acceptable` | \|sesgo\| ≤ 1,0 µg/m³ | Sin sesgo sistemático fuerte |
| `high_concentrations_acceptable` | RMSE en percentil 90 ≤ 1,10 × activo | Cuidado especial con picos de contaminación |
| `uncertainty_acceptable` | cota superior del IC bootstrap diario < 0 | La mejora debe ser estadísticamente consistente |

Estos umbrales son **provisionales del prototipo** y así se documenta; no constituyen un estándar ambiental.

### 3.3 Reentrenamiento (`maintenance.run`)

```
1. initialize()  → modelo activo (o registro inicial experimental)
2. Cargar datos históricos (CSV normalizado) + observaciones frescas de data/live/*.sqlite
3. Calcular cutoff = 'evaluated_until' del activo + todas las ventanas reservadas
4. Si hay < 168 ejemplos completos posteriores al cutoff → status 'skipped'
   («faltan datos», el activo se conserva)
5. Reservar la ventana de evaluación (event 'evaluation_reserved')
   ⚠ Se consume aunque luego falle el entrenamiento o se rechace el candidato:
     impide «mirar» la ventana una y otra vez hasta que algo apruebe
6. Entrenar SOLO con datos anteriores a la ventana, con la receta congelada
   (clona el modelo de referencia; NO se ajustan hiperparámetros contra la
   ventana de aprobación — anti data-leakage)
7. Registrar el candidato (inmutable) + guardar hashes de datos (provenance)
8. evaluate(candidato, campeón, ventana, política) → todos los controles
9. Si aprueba: activate(compare-and-swap) + smoke test post-activación
   (si el smoke test falla → rollback automático)
   Si rechaza: event 'candidate_rejected', activo intacto
```

### 3.4 Ingesta de datos (`live.ingest` + `state_job.archive_ingestion`)

Dos modos explícitamente diferenciados:

| Modo | Condición | Efecto |
|---|---|---|
| Autenticado (`authenticated_openaq`) | Existe `OPENAQ_API_KEY` | Consulta las últimas 72 h del sensor 4672 vía API de OpenAQ; re-visita registros antiguos para recibir correcciones; escribe en `data/live/airepredict.sqlite`; emite predicción actual si hay ventana fresca y la registra para monitorización |
| Archivo histórico (`historical_archive`) | Sin clave | Actualiza solo el CSV público **retrasado**; etiqueta explícita de modo; **nunca** alimenta el almacén en vivo ni habilita pronósticos actuales |

Validaciones de la ingesta autenticada: intervalo horario completo, unidades µg/m³, valor finito no negativo, cobertura declarada ≥ 75 %, rechazo de periodos futuros/incompletos; upsert sin duplicados; lote atómico (si falla una página, no se escribe nada parcial); conflictos dentro de un lote se excluyen.

La clave está verificada en producción: se aceptaron 34 horas en una ejecución real de Actions.

### 3.5 Monitorización y rollback automático por degradación (`monitoring.py`)

- Cada predicción «actual» emitida se registra con sus entradas (`record_forecast`); se preserva la **primera** emisión (no se reescribe tras ver el resultado — evitar sesgo de supervivencia).
- `monitor` exige: ≥ 50 predicciones cuyo resultado ya existe, repartidas en ≥ 7 días, dentro de los últimos 14 días.
- Recalcula el desempeño del activo contra lo observado y contra persistencia, y repite la inferencia con la versión anterior usando las entradas guardadas (no datos futuros corregidos).
- **Condiciones de rollback automático** (ambas):
  - degradación: MAE y RMSE del activo > 1,10 × persistencia;
  - el anterior además mejora: MAE(previo) < 0,98 × MAE(activo) y RMSE(previo) ≤ RMSE(activo).
- Si se cumple: `rollback(mark_failed=True)` — el degradado queda bloqueado para futuras activaciones.

### 3.6 Demo aislada del ciclo MLOps (`maintenance.demo`, acción `demo`)

Evidencia reproducible sin tocar el registro de la aplicación:

1. Crea un registro **sandbox** nuevo bajo `models/mlops_demo/<timestamp>/` (la clase Registry impide mezclar sandbox con la app: «a sandbox cannot be opened as the application registry»).
2. Registra un baseline de persistencia.
3. Primer entrenamiento histórico → esperado: `promoted` (aprueba política relajada).
4. Segundo entrenamiento (mismos datos) → esperado: `rejected` por no mejorar.
5. Simula fallo post-despliegue del primero → `rollback` → se restaura el baseline.
6. Escribe `reports/mlops_demo.json` con eventos; relaja explícitamente 2 controles y lo anota en la política sandbox.
7. `application_registry_modified: false` — el registro real de la app no cambió.

### 3.7 Orquestación en la nube (`operations.yml` + `scripts/state_job.py`)

Horarios (UTC):

| Cron | Acción | Sentido |
|---|---|---|
| `17 * * * *` | `ingest` | Datos cada hora |
| `37 8 * * *` | `monitor` | Supervisión diaria |
| `47 9 * * 1` | `retrain` | Reentrenamiento semanal (lunes) |
| `27 7 * * *` | `backup` | Respaldo diario |

`state_job.py` hace, dentro del lock de mantenimiento:

1. Copia el seed de `main` al directorio de estado (solo archivos faltantes; `config` siempre).
2. **Reconciliación de recuperación**: consulta `GET /api/operations` de la app; si la app reporta que su activo difiere del publicado (una recuperación local que aún no se consolidó), aplica el rollback en el estado durable.
3. Ejecuta la acción pedida (ingest/retrain/monitor/backup/rollback/demo/verify/puno).
4. Repite el mantenimiento para las estaciones configuradas (2402 San Borja, 2351 San Martín de Porres); el modelo general diario está congelado; Puno corre aislado como experimento.
5. Escribe `state.json` (reporte de la corrida) y `artifacts/<acción>.json`, y el workflow hace commit/push a `runtime-state` **incluso si el paso falló** (`if: always()`) — así el estado y el fallo quedan publicados para auditar.
6. Sube artefactos (ZIP de respaldos incluido) con retención de 30 días.

Concurrencia: `production-maintenance` serializa todas las escrituras del estado de modelos.

### 3.8 Respaldo y restauración (`operations.backup`)

- SQLite **online backup** (`connection.backup`) — evita copiar archivos WAL inconsistentes — más `PRAGMA integrity_check` en la copia.
- Copia de modelos, datos en vivo y procesados, config, requirements y reports (excluye sandboxes y temporales).
- `manifest.json` con SHA-256 de cada archivo + hash del ZIP final.
- Restauración: verificar hashes → probar en estado aislado → publicar revisión controlada de `runtime-state` → conservar también el commit de código y entorno compatibles.

### 3.9 Comandos locales para practicar (modo consola)

Desde la raíz, con el venv activo: `python -m airepredict <comando>`

| Comando | Qué demuestra |
|---|---|
| `registry-init` | Registro inmutable + activación del modelo experimental inicial |
| `registry-status` | Estado active/previous y auditoría de eventos |
| `retrain` | Ciclo completo: skip si faltan datos, o evaluación de candidato |
| `monitor` | Supervisión (skip si < 50 predicciones reales) |
| `rollback` | Recuperación de la versión anterior |
| `mlops-demo` | Aceptación + rechazo + recuperación en sandbox |
| `ingest` / `readiness` | Ingesta autenticada / indicador de suficiencia de datos |
| `maintenance` | Ingesta + reentrenamiento + monitorización en una llamada |
| `serve` | Servicio web local en `127.0.0.1:8000` |

Endpoints útiles para inspeccionar: `/ready` (commit + versión del modelo), `/api/operations` (estado publicado vs local y bandera `local_recovery`), `/api/status`, `/api/model`, `/docs` (Swagger).

---

## 4. Decisiones de diseño que conviene poder justificar

1. **¿Por qué la app no escribe estado?** Un servicio público sin credenciales de escritura reduce superficie de ataque; Actions concentra la escritura con autenticación de GitHub y serialización por grupos de concurrencia.
2. **¿Por qué rama de Git para el estado en lugar de una base de datos?** Alojamiento gratuito: Git ofrece almacenamiento, versionado, historial y descarga por SHA; el snapshot ZIP da atomicidad simple. Coste cero. La contrapartida: límites de tamaño y disponibilidad del plan gratuito.
3. **¿Por qué symlink con `os.replace`?** Cambio atómico de todo el árbol de estado: nunca se mezcla un modelo viejo con datos nuevos a medias.
4. **¿Por qué reservar la ventana de evaluación aunque falle?** Evita el «p-hacking» operativo: no se puede reintentar hasta que un candidato apruebe mirando siempre el mismo período.
5. **¿Por qué la receta congelada?** Separar selección (hecha en el experimento original con validación temporal) de aprobación (esta ventana). No se ajustan hiperparámetros contra la ventana de decisión.
6. **¿Por qué el smoke test post-activación?** Detecta modelos registrados pero no usables en el runtime real (rollback inmediato).
7. **¿Por qué dos recuperaciones (app vs modelo)?** Son fallas distintas: código/entorno vs artefacto predictivo; cada una tiene su procedimiento y su evidencia.
8. **¿Por qué persistencia como baseline?** Es el benchmark mínimo de sentido común en pronóstico horario: si no le ganas, no aportas.
9. **¿Por qué el modelo inicial es «experimental» y `promotion_policy_passed: false`?** Honestidad de metadatos: el modelo original no fue sometido a la política actual; registrarlo no certifica producción.
10. **¿Por qué `cancel-in-progress: false`?** Serializar es mejor que cancelar a mitad un despliegue o un respaldo.

---

## 5. Límites conocidos (pregunta casi segura)

- Render gratuito se suspende por inactividad: el primer acceso puede tardar; sin SLA.
- La rama de estado es pública: solo datos no sensibles.
- Sin `OPENAQ_API_KEY` no hay pronóstico actual real, solo archivo retrasado etiquetado.
- El intervalo bootstrap del experimento original incluye cero: la mejora observada no acredita la política estricta por sí sola.
- Umbrales de la política y del monitor son provisionales.
- Las ventanas de evaluación ya consumidas no se reutilizan como confirmación independiente.
- Un solo proceso uvicorn: los locks (flock + mutex de thread) asumen ese modelo de despliegue.
- Recuperar modelo puede exigir recuperar también el entorno/código (compatibilidad de sklearn y de `features.py` verificada por hashes).

---

## 6. Glosario rápido

| Término | Significado aquí |
|---|---|
| Release | Versión inmutable de modelo + código + entorno + hashes |
| Campeón (champion) | Modelo actualmente activo en el registro |
| Candidato | Modelo recién entrenado que compite contra el campeón |
| Ventana reservada | Período de evaluación consumido, sin reentrenar sobre él |
| Persistencia | Baseline: predice PM2.5(t+1) = PM2.5(t) |
| CAS | Compare-and-swap: activación condicionada al activo esperado |
| Seed | Copia inmutable dentro de la imagen del contenedor |
| Snapshot | Descarga completa y validada de `runtime-state` |
| Proyección de solo lectura | Vista del estado publicado que ofrece el servidor web |
| Promotion gate | Conjunto de controles que un candidato debe pasar |

---

## 7. Preguntas de repaso

1. Describe el flujo completo desde `git push` hasta la actualización de la app en Render, nombrando los archivos involved.
2. ¿Qué comprueba `check_deployment.py` y por qué tiene reintentos?
3. ¿Bajo qué condiciones `deploy.yml` decide no desplegar su propio commit?
4. ¿Qué protege el sistema contra despliegues concurrentes y contra mantenimiento concurrente?
5. Explica la conmutación atómica de estado y qué pasa si la descarga falla.
6. Nombra los nueve controles de promoción y qué riesgo mitiga cada uno.
7. ¿Por qué se consumen las ventanas de evaluación aunque el entrenamiento falle?
8. Dibuja el ciclo completo de un reentrenamiento: skip, rechazo y promoción, con los eventos del registro.
9. ¿Qué condiciones disparan el rollback automático del monitor y por qué exigen que además el anterior sea mejor?
10. ¿Cómo se evita contaminar el registro de la aplicación con la demo MLOps?
11. ¿Qué diferencia hay entre el modo de ingesta autenticado y el archivo histórico, y por qué importa?
12. ¿Cómo se verifican la integridad y el origen del estado descargado antes de servirlo?
13. ¿Qué es el «local_recovery» que reporta `/api/operations` y quién lo reconcilia?
14. ¿Cómo funciona el respaldo de SQLite y qué lo diferencia de copiar el archivo?
15. ¿Por qué el modelo inicial se marca como experimental con `promotion_policy_passed: false`?
