# Puno: modelo experimental independiente

## Alcance

La fuente es `https://api-aire-puno.onrender.com/api/puno/forecast`, identificada como CAMS global vía Open-Meteo. No es una estación física. Sus valores son pronósticos externos y nunca se guardan en las bases de mediciones SENAMHI/OpenAQ. No se reutilizan las métricas del modelo OEFA ni se presentan como precisión local. No se habilitan alertas de salud, notificaciones ni selección de widget para este laboratorio.

La web `/puno` y la pantalla Android «Puno · calidad del aire» muestran el mapa, la curva CAMS, una estimación del modelo propio, fechas, métricas y versiones. También se ofrece el acceso al usar una ubicación próxima a Puno. Las coordenadas personales siguen procesándose solo en el dispositivo.

## Entrenamiento inicial

Se descargaron 48 valores horarios modelados. Tres retardos consecutivos forman entradas para estimar el siguiente valor de CAMS: nivel anterior, dos diferencias horarias y seno/coseno de la hora. Resultan 45 ejemplos: 27 entrenamiento, 9 validación y 9 prueba, ordenados por hora objetivo. No se conectan huecos de la serie.

El modelo es StandardScaler + Ridge. Se selecciona alpha entre 0.1, 1 y 10 usando solo validación. Se conserva el modelo ajustado con las 27 filas de entrenamiento; no se reajusta con prueba. El informe y el artefacto se guardan juntos, con versión derivada del SHA256 del modelo.

El primer ajuste obtuvo MAE 0.267072 y RMSE 0.288417 µg/m³; R² 0.698391, frente a una referencia de persistencia con MAE 0.233333. **El modelo inicial no mejora repetir el último valor.** Su activación es exclusivamente una semilla de demostración, no una promoción de producción aprobada por superioridad. La muestra es pequeña. Los valores pertenecen a una curva futura ya publicada por CAMS: esta partición comprueba reproducción de la curva, no acierto de un pronóstico real emitido antes de observaciones posteriores. No existen mediciones de contraste de Puno.

El punto inferido usa las tres horas modeladas anteriores a la primera hora objetivo futura que cubra la curva. Se muestran la predicción propia y la estimación CAMS para esa misma hora. Si pasaron más de tres horas desde la descarga o no queda horizonte futuro, se oculta el valor vigente y se permite consultar la curva archivada.

## MLOps

El flujo existente `Scheduled model maintenance` descarga Puno con la ingestión horaria y evalúa su reentrenamiento semanal. También admite acciones manuales `puno` y `puno-rollback`. Los errores de la fuente conservan el modelo y se registran separados de las estaciones reales.

Se conservan la fecha de descarga, la hora objetivo y el valor de la primera publicación observada para cada hora. Las revisiones de un mismo objetivo no aumentan el número de ejemplos ni sustituyen sus valores originales. La curva más reciente se guarda separadamente para visualización/inferencia.

Un nuevo entrenamiento requiere al menos 168 objetivos nuevos, posteriores al último periodo consumido. El último 20 % de los objetivos nuevos, con mínimo 24 ejemplos, forma una prueba nueva. Los datos anteriores se separan cronológicamente entre entrenamiento y validación. Candidato y campeón se evalúan en la misma prueba, sin incluir sus etiquetas en el ajuste. La ventana queda consumida también si se rechaza el candidato.

Para activar un candidato posterior: MAE menor al 99 % del MAE del campeón, MAE no superior a persistencia y RMSE no superior al campeón. En caso contrario permanece activo el campeón. Se guarda el modelo anterior y se puede restaurar desde GitHub Actions. La web verifica el hash antes de cargar artefactos; si el activo está dañado, intenta el anterior sin modificar las estaciones reales.

GitHub Actions es el único escritor del estado duradero en `runtime-state`; Render lo consulta mediante las instantáneas existentes. El artefacto inicial incluido en la imagen sirve de respaldo antes de la primera publicación del nuevo estado. No hay endpoints públicos para entrenar ni restaurar.

## Validación y evolución

Las pruebas cubren procedencia, unidades, horas duplicadas, separación temporal, revisiones, muestra mínima, promoción, rechazo, ventanas consumidas, restauración, integridad, caducidad y aislamiento de estaciones. Android verifica el acceso y el contrato experimental.

Una futura fase con sensores locales deberá crear un conjunto de mediciones reales independiente, registrar pronósticos antes de sus objetivos y evaluar contra dichas mediciones. La coincidencia con CAMS no demuestra precisión frente a la contaminación real.

Fuentes: https://api-aire-puno.onrender.com/docs y https://open-meteo.com/en/docs/air-quality-api. Atribución CAMS ENSEMBLE / Open-Meteo (CC BY 4.0); se mantienen las condiciones del proveedor.

## Pantallas pequeñas (0.5.1)

La información de la fuente se muestra una sola vez, en una tarjeta desplegable dentro del contenido. No es fija ni cubre el mapa o la estimación. Android dispone de una barra compacta con Volver y Actualizar; los mensajes de conexión desaparecen al cargar correctamente y los errores siguen visibles. Los botones comparten tamaños táctiles de al menos 48 dp, esquinas redondeadas y respuesta visual al pulsar. La prueba Android verifica una pantalla de 320 × 568 dp, la estimación visible y la ausencia de desbordamiento horizontal.

## Renovación de la fuente desde web y Android

La página consulta `/api/puno/experiment?refresh=true` al abrirse o actualizarse. El servicio descarga y valida la curva pública de Puno para inferencia con el mismo modelo verificado. Esta renovación no entrena, no cambia métricas ni versiones y no escribe observaciones o registros duraderos. También funciona en el WebView del APK existente, sin reinstalarlo.

Una caché compartida por proceso limita la consulta al proveedor a una cada diez minutos; después de un fallo espera al menos un minuto. Las solicitudes concurrentes usan la última copia mientras una sola consulta renueva la fuente. Una lectura de caché no modifica `fetched_at`. Se mantiene el límite de tres horas y la exigencia de horizonte futuro; si la fuente falla y la copia ya caducó, el valor sigue no disponible con un mensaje de renovación fallida. Un valor todavía vigente puede mostrarse con advertencia de que no pudo renovarse.

GitHub Actions sigue siendo el único escritor del histórico de entrenamiento y del registro persistente. Su horario puede retrasarse, por lo que la inferencia en pantalla ya no depende exclusivamente de una ejecución puntual. La copia en memoria desaparece al reiniciar y se vuelve a consultar si el usuario abre Puno. El endpoint sin `refresh` consulta el estado disponible sin iniciar llamadas al proveedor.
