# AirePredict Perú

Observatorio experimental de PM2.5 de Perú. Mapa e histórico del dataset OEFA completo, modelo general diario y modelos horarios independientes para Jesús María, San Borja y San Martín de Porres. Web y Android en español, con inicio, mapa, estaciones, ajustes y widget.

**Aplicación:** https://airpredict-4u3c.onrender.com/  
**Automatizaciones:** https://github.com/Miguel7293/AirPredict/actions  
**APK Android de demostración:** [descargar](https://github.com/Miguel7293/AirPredict/releases/download/v0.4.0/airepredict-demo.apk)

## Producto y operación

La aplicación distingue observaciones actuales de la demostración histórica, muestra las fechas y representa los huecos de datos. Android añade widget de pantalla de inicio y notificaciones opcionales. El modelo sigue siendo experimental.

Render gratuito sirve la aplicación. GitHub Actions ejecuta las operaciones y conserva el estado en la rama pública `runtime-state`; el servidor carga revisiones completas cada diez minutos y al arrancar. No se contrató alojamiento de pago. El primer acceso puede tardar porque el servicio gratuito se suspende por inactividad.

Los flujos comprueban pruebas y contenedor, publican imágenes por commit, despliegan en Render, ingieren datos, evalúan candidatos, supervisan predicciones y respaldan el estado. La ingesta autenticada ya se verificó con 34 horas aceptadas. Si las mediciones llegan tarde, la aplicación permite inspeccionarlas y mantiene deshabilitada la predicción actual. Sin `OPENAQ_API_KEY`, la ingesta utiliza el archivo público retrasado y conserva explícitamente el modo histórico.

## Nuevo atlas y modelos (0.4)

[Metodología del atlas, entrenamiento general y modelos por estación](docs/ATLAS_Y_MODELOS.md). El modelo general revisó 2.883.877 registros, utiliza 3.879 observaciones diarias válidas y mantiene el test separado. MAE diario 2,67 µg/m³ y R² 0,692; no equivale a las métricas horarias ni a cobertura continua del país.

El mapa permite explorar el histórico y simular el día siguiente con datos diarios introducidos por el usuario. Las simulaciones se identifican como datos sin verificar. Solo los puntos de OpenAQ configurados participan en el MLOps automático.

## Documentación

- [Informe técnico del MVP](docs/INFORME_TECNICO_MVP.md): arquitectura, configuración, pipelines, recuperación y límites.
- [Entrenamiento y resultados](reports/oefa_campo_marte_v1/REPORTE_ENTRENAMIENTO.md): fuentes, 30 configuraciones, métricas y gráficos.
- [Guion de exposición de 14 minutos](docs/GUION_EXPOSICION.md).
- [Registro y controles de modelos](docs/MLOPS.md).
- [Contrato de predicción e ingesta](docs/SERVICIO.md).
- [Auditoría de compatibilidad](audit/COMPATIBILIDAD.md).

El combinado obtiene MAE 2,0177 µg/m³, RMSE 2,8815 y R² 0,6175 en 270 ejemplos históricos de prueba. La mejora observada frente a persistencia es pequeña; el intervalo diario incluye cero. El registro inicial no representa aprobación de la nueva política de promoción.

## Verificación de la entrega inicial (0.3)

- 45 pruebas Python en Linux; en Windows pasan 43 y se omiten dos específicas de Linux.
- Tres flujos del cliente: demostración histórica, mediciones retrasadas y consulta histórica guardada sin conexión.
- Seis pruebas de Android 15, incluida la vinculación del widget y el rechazo de notificaciones.
- Ingesta autenticada comprobada, recuperación real de una versión anterior de la aplicación y restauración de un respaldo con hashes verificados.
- Simulación aislada de aceptación, rechazo y recuperación de modelos; el activo conserva su condición experimental.

[Evidencias y enlaces a ejecuciones](reports/ENTREGA_MVP.json). [Desarrollo e instalación de Android](docs/ANDROID.md).

## Ejecución local

Usar Python 3.12 para mantener compatibilidad con CI y contenedor:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m airepredict registry-init
.\.venv\Scripts\python.exe -m airepredict serve
```

El modelo inicial y las mediciones normalizadas necesarias para arrancar están incluidos. Reproducir la auditoría completa desde el CSV original requiere conservarlo en `Dataset/`; ese archivo grande no se publica en el repositorio. La receta y resultados del entrenamiento original están documentados.

Para operaciones locales: `registry-status`, `retrain`, `monitor`, `rollback`, `maintenance` y `mlops-demo`. Las operaciones de producción gratuita se ejecutan desde **Scheduled model maintenance → Run workflow** en GitHub.

## Organización

| Ruta | Función |
|---|---|
| `src/airepredict/` | Datos, características, entrenamiento, servicio, registro y recuperación |
| `src/airepredict/static/` | Interfaz, PWA, vista compacta y acceso a operaciones |
| `android/` | Aplicación nativa, widget y pruebas de dispositivo |
| `.github/workflows/` | CI, entrega, mantenimiento y Android |
| `scripts/state_job.py` | Operaciones del estado durable en Actions |
| `config/` | Experimento y controles de promoción |
| `data/processed/` | Semilla normalizada de datos públicos |
| `models/oefa_campo_marte_v1/` | Modelo experimental de arranque |
| `docs/` y `reports/` | Informe, procedimientos, entrenamiento y evidencias |

No guardar credenciales en el código, los modelos, el APK ni la rama `runtime-state`.
