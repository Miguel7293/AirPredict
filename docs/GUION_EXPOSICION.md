# Exposición técnica: 14 minutos

La demostración de funcionamiento se realiza en inglés. Distribuir los bloques entre los integrantes del equipo; el curso exige equipo de hasta cuatro estudiantes y no permite trabajo individual.

| Tiempo | Responsable sugerido | Contenido y evidencia |
|---|---|---|
| 0:00–2:00 | Producto | Abrir la URL pública desde otro dispositivo. Mostrar estación, fechas, observado, predicho, gráfico y estados. Explicar cuándo la demostración es histórica. |
| 2:00–6:00 | Datos y modelo | Problema supervisado, fuentes, ejemplos completos, nueve características, partición temporal, 30 configuraciones y selección por validación. Mostrar MAE, RMSE, R² y comparación con persistencia, con sus límites. |
| 6:00–8:00 | Despliegue | Render gratuito, contenedor Python, estado durable en GitHub, sincronización y recuperación tras reinicio. Mostrar commit desplegado y HTTPS. |
| 8:00–12:00 | DevOps/MLOps | Mostrar CI real, construcción de imagen y despliegue. Abrir ejecución de mantenimiento: datos, candidato y decisión. Mostrar simulación aislada de aceptación/rechazo/recuperación y respaldo verificado. |
| 12:00–14:00 | Producto y operación | Abrir Android, explicar widget y permisos opcionales, enseñar evidencia de pruebas. Presentar informe técnico y límites pendientes de datos actuales. |

## Frases de demostración en inglés

“AirePredict estimates next-hour PM2.5 at Campo de Marte. Please read the observation and forecast dates first.”

“This recorded example is historical. It does not describe current air conditions.”

“The model was selected using temporal validation. The held-out test shows a modest improvement, and its confidence interval includes zero.”

“A new model replaces the active one only after it passes the quality gates. A rejected candidate leaves the active model unchanged.”

“The widget displays the target time. Notifications are optional, and declining permission does not block the application.”

## Preparación

Abrir previamente aplicación, GitHub Actions, informe del entrenamiento y APK. Descargar evidencias por si falla la conexión durante la exposición. Esperar el arranque de Render gratuito antes del turno. No mostrar valores de secretos ni pantallas con claves. Una ejecución sin datos suficientes se explica como control correcto, no como entrenamiento nuevo.
