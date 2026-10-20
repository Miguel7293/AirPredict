# Reentrenamiento, aprobación y recuperación

El proyecto incorpora un registro local de modelos con versiones inmutables, evaluación temporal de candidatos, activación controlada y recuperación de la versión anterior. El modelo inicial sigue siendo experimental: registrarlo no certifica sus métricas para producción.

## Ciclo implementado

1. La ingesta valida y guarda las nuevas mediciones.
2. El reentrenamiento exige al menos 168 ejemplos completos posteriores al último periodo reservado del modelo activo. Sin ellos, conserva el modelo actual.
3. Entrena con observaciones anteriores al periodo de evaluación, usando la receta combinada congelada. No ajusta hiperparámetros con el periodo de aprobación.
4. Compara candidato, modelo activo y persistencia sobre las mismas horas posteriores.
5. Solo activa al candidato cuando pasa todos los controles. Guarda la versión anterior y el informe de evaluación. Un rechazo o un error de entrenamiento conserva la versión activa.
6. El servicio detecta cambios de versión. Si una versión recién activada no carga o falla al predecir, intenta recuperar la anterior compatible. Si no puede recuperarla, devuelve un error de disponibilidad.

La política está en `config/promotion_policy.json`: al menos 100 ejemplos, siete días observados, cobertura del 35 %, mejora relativa del MAE de al menos 2 %, MAE inferior a persistencia, límites de RMSE, sesgo y error en concentraciones altas, y un intervalo bootstrap diario cuya cota superior sea negativa. Son umbrales iniciales del prototipo y requieren revisión para producción, especialmente la cobertura. Reentrenar no garantiza aprobar estos controles.

La mejora del experimento original tiene un intervalo que incluye cero. Por tanto, ese resultado por sí solo no acredita superar la nueva política estricta.

## Operación local

Desde la carpeta del proyecto, anteponer `.\.venv\Scripts\python.exe -m airepredict` a cada comando:

| Comando | Acción |
|---|---|
| `registry-init` | Registra el modelo combinado existente como versión experimental inicial |
| `registry-status` | Consulta las versiones activa y anterior, y el historial |
| `retrain` | Entrena y evalúa si hay suficientes datos nuevos; activa solo si aprueba |
| `monitor` | Evalúa predicciones actuales cuando ya existen las mediciones reales |
| `rollback` | Recupera manualmente la versión anterior compatible |
| `maintenance` | Ejecuta ingesta, reentrenamiento y supervisión en una llamada |
| `mlops-demo` | Reproduce aceptación, rechazo y recuperación en un registro histórico aislado |

`maintenance` requiere `OPENAQ_API_KEY`. Todavía no hay una tarea periódica instalada ni conexión autenticada verificada. El comando automatiza el ciclo al ejecutarse; no se ejecuta por sí solo. `readiness` sigue siendo únicamente un indicador de cantidad de datos.

El servicio registra las predicciones actuales emitidas y sus entradas. `monitor` necesita al menos 50 predicciones con resultados conocidos repartidas en siete días, dentro de los últimos 14 días. Recupera la versión anterior si el MAE y el RMSE activos superan a persistencia en más del 10 %, y la versión anterior mejora el MAE activo en más del 2 % sin empeorar el RMSE. Estos límites también son provisionales. La demostración histórica no aporta predicciones actuales a este monitor.

## Versiones y compatibilidad

`models/registry/` contiene el registro SQLite, los modelos, sus hashes, configuración, versiones de dependencias, copias de código y evaluaciones. Debe conservarse junto con `data/live/`, usando almacenamiento persistente en un despliegue. La activación comprueba que el modelo activo no haya cambiado mientras se evaluaba el candidato.

La recuperación exige compatibilidad con las características y el entorno en ejecución. Si cambian dependencias o transformaciones, puede ser necesario restaurar también el entorno y el código guardados. Una versión marcada como fallida queda bloqueada para nuevas activaciones. La recuperación consume el puntero a la versión anterior para evitar volver automáticamente al modelo fallido.

## Evidencia de la demostración

`reports/mlops_demo.json` contiene el resultado y los eventos: entrenamiento aceptado frente a persistencia, segundo entrenamiento rechazado por no mejorar y recuperación de la referencia tras una falla simulada. Usa datos históricos ya consultados y relaja explícitamente dos controles solo en el registro aislado. No constituye aprobación de producción ni modifica el registro de la aplicación.

Se verificaron 33 pruebas, incluyendo integridad de artefactos, incompatibilidad de dependencias, activación concurrente, aislamiento de la simulación, rechazo sin aprobación, recuperación del servicio y recuperación por degradación de métricas. Falta verificar la operación con datos actuales, instalar la ejecución periódica y desplegar con almacenamiento persistente.

## Despliegue gratuito y automatización

El MVP ahora tiene flujos de GitHub Actions y alojamiento Render gratuito. La rama `runtime-state` conserva el estado y el servidor consume copias de lectura. Las tareas locales descritas arriba siguen disponibles, pero el mantenimiento publicado se ejecuta en Actions. Véase [INFORME_TECNICO_MVP.md](INFORME_TECNICO_MVP.md) para horarios, credenciales, sincronización y límites. Los periodos de aprobación quedan consumidos incluso tras rechazos o fallas.
