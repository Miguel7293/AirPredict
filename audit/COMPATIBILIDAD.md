# Compatibilidad del histórico OEFA con OpenAQ

Fecha de comprobación: **19 de octubre de 2026**, zona America/Lima.

## Dictamen

**Compatibilidad parcial de contenido y ubicación; no se ha validado una combinación operativa para pronosticar PM2.5 a una hora y reentrenar con datos actuales usando directamente este CSV.**

La Huaca y Macacará son coincidencias sólidas: coordenadas prácticamente idénticas, PM2.5 y unidades equivalentes. Sin embargo, sus últimas mediciones publicadas corresponden al 3 de diciembre de 2025. Por tanto, no proporcionan el flujo actual de nuevos objetivos que necesita el proyecto.

La alternativa mejor respaldada por las muestras consultadas es utilizar el histórico y las actualizaciones de **una misma estación SENAMHI dentro de OpenAQ**. Campo de Marte es la primera candidata de las tres revisadas. Esto supone cambiar la fuente de entrenamiento del modelo operativo; el CSV OEFA puede conservarse para análisis complementarios.

## Alcance y evidencia

- Se recorrieron las 2 883 877 filas del CSV local, sin modificarlo.
- Se inspeccionaron 36 columnas y 34 combinaciones de código de punto y coordenadas. Estas combinaciones no equivalen necesariamente a 34 instalaciones distintas: existen alias y cambios de coordenadas.
- Se obtuvieron fichas públicas de 25 ubicaciones OEFA y de tres estaciones SENAMHI. La búsqueda por un intervalo regional de identificadores es un inventario de candidatos, no un listado exhaustivo del catálogo API.
- Se transformaron las coordenadas UTM WGS84 de los husos declarados 17, 18 y 19 sur a latitud y longitud WGS84. Se calcularon distancias geodésicas.
- Se descargaron archivos públicos de OpenAQ en AWS: siete días recientes por estación SENAMHI, un día de 2022 por estación y muestras OEFA de diciembre de 2025.
- La solicitud directa a la API v3 sin clave respondió HTTP 401. Las comprobaciones de valores se realizaron mediante el archivo público oficial, no mediante una sesión autenticada de la API.

Fuentes locales: [resumen del CSV](historico_oefa_resumen.json), [metadatos y cruce geográfico](openaq_metadatos_y_cruce.json), [muestras recientes](openaq_muestras_recientes.json) y [muestras OEFA](openaq_archivo_muestras.json). Los CSV descargados están en esta misma carpeta.

## Estado del histórico

| Comprobación | Resultado |
|---|---|
| Fechas de medición válidas del archivo | 01/01/2018 a 31/12/2022 |
| Fecha de corte declarada | 29/04/2024 en todas las filas; no es la fecha de la medición |
| PM2.5 numérico | 94 371 filas |
| PM2.5 con periodo de una hora | 90 492 filas |
| PM2.5 con periodo de 24 horas | 3 879 filas |
| PM2.5 horario con fecha y hora reconstruibles | 15 684 filas, en dos puntos |
| PM2.5 horario sin hora utilizable | 74 808 filas, aproximadamente 82,7 % del subconjunto horario |
| Unidad de los valores PM2.5 informados | ug/m3 |

No se deben inventar las horas de las filas cuyo HORA_INICIO es NA ni asignarlas automáticamente según su posición en el archivo.

Para las dos series reconstruibles se combinó FECHA_INICIO con la parte horaria de HORA_INICIO. El valor de fecha base `1899-12-31`, presente en 654 filas, se interpretó explícitamente como medianoche. La fecha base del formato Excel no se utilizó como fecha de medición. Esta interpretación debe contrastarse con el diccionario original antes de producción.

El CSV no declara un desplazamiento horario. La interpretación como hora peruana UTC−05 debe confirmarse con la documentación original antes de unir sus observaciones con OpenAQ.

| Punto local | Serie horaria reconstruible | Filas únicas | Cobertura del intervalo completo | Mayor hueco entre observaciones | Mayor tramo consecutivo |
|---|---|---:|---:|---:|---:|
| CA-MAC-01 | 09/12/2021 22:00 a 31/12/2022 23:00 | 8 236 | 88,65 % | 961 horas | 1 305 horas |
| CA-HUA-01 | 08/12/2021 18:00 a 31/12/2022 23:00 | 7 448 | 79,93 % | 1 711 horas | 1 818 horas |

Los intervalos y coberturas anteriores se calcularon con la interpretación de medianoche indicada. No se encontraron marcas de tiempo duplicadas en esas dos series. La cobertura cuenta horas presentes dentro del intervalo entre la primera y la última observación; no demuestra calidad instrumental.

## Estaciones que coinciden

Se encontraron once coincidencias de coordenadas inferiores a un metro dentro del inventario consultado. Ocho de ellas tienen PM2.5 tanto en el histórico como en la lista de sensores de OpenAQ. Una coincidencia de coordenadas respalda la ubicación; no demuestra por sí sola que el instrumento o su calibración se hayan mantenido.

| Código del CSV | Ubicación OpenAQ | ID OpenAQ | Distancia aproximada | PM2.5 en ambas fuentes | Hora reconstruible en el CSV |
|---|---|---:|---:|---|---|
| CA-CP-01 | Ccapacmarca | 2578964 | 0,04 m | Sí | No |
| CA-MAC-01 | Macacara | 2578979 | 0,05 m | Sí | Sí |
| CA-HUA-01 | La Huaca | 2578976 | 0,07 m | Sí | Sí |
| CA-SOC-01 | Socabaya | 2578986 | 0,05 m | Sí | No |
| CA-COLQ-01 | Colquijirca | 2578967 | 0,06 m | Sí | No |
| CA-TAL-01 | Tala | 2578987 | 0,05 m | Sí | No |
| CA-HU-04 | Huachipa - El Paraiso | 2578968 | 0,04 m | Sí | No |
| CA-HU-09 | Huachipa - Santa Maria | 2578970 | 0,04 m | Sí | No |
| CA-RZC-02 | Cajamarquilla-ROJ | 2578962 | 0,05 m | No: OpenAQ no lista ese sensor | No |
| CA-RZC-01 | Los Andes | 2578978 | 0,06 m | No: OpenAQ no lista ese sensor | No |
| CA-CC-01 | La Oroya | 2578977 | 0,06 m | No | No |

Las distancias centimétricas reflejan que las coordenadas publicadas son equivalentes tras la transformación; no implican precisión física centimétrica.

No se aceptaron coincidencias por nombre o cercanía exclusivamente. Por ejemplo, CA-CG-02 está a unos 238 metros de Casa Grande 03; CA-JUPR-01 está a unos 54 metros de Juprog. Se necesita comprobar cambios de emplazamiento antes de tratarlas como una misma serie. CA-HUAR-01 declara el huso 19, que produce una posición incompatible con su descripción de Huaraucaca; requiere revisar el huso original y no se corrigió automáticamente.

## Las dos coincidencias horarias no tienen datos actuales

| Estación | Sensor PM2.5 | Inicio publicado de la ubicación | Última fecha publicada de la ubicación, hora peruana |
|---|---:|---|---|
| [La Huaca](https://explore.openaq.org/locations/2578976) | 8437748 | 10/03/2024 20:00 | 03/12/2025 19:00 |
| [Macacara](https://explore.openaq.org/locations/2578979) | 8437742 | 10/03/2024 20:00 | 03/12/2025 19:05 |

El archivo público del 03/12/2025 contiene efectivamente PM2.5: una observación en La Huaca y dos en Macacará. Los archivos consultados del 15/10/2026 devuelven 404. La ausencia de un archivo aislado no demostraría una interrupción completa; se combina aquí con el límite temporal publicado en la ficha de cada ubicación.

Las series locales de esas dos estaciones terminan en diciembre de 2022 y los intervalos publicados en esas fichas empiezan en marzo de 2024. **No hay solapamiento que permita contrastar valores simultáneos en los intervalos comprobados.** No se ha demostrado igualdad de calibración, ausencia de sesgo o continuidad durante el intervalo faltante.

Ninguna de las 25 fichas OEFA consultadas mostraba una última observación de 2026. Esto no prueba que todas las estaciones OEFA existentes estén inactivas, ni que OEFA no disponga de otra fuente de publicación.

## Comparabilidad de variables e intervalos

| Aspecto | Decisión necesaria |
|---|---|
| PM2.5 frente a pm25 | Corresponden al mismo contaminante; normalizar el nombre |
| ug/m3 frente a µg/m³ | Misma unidad física; normalizar la etiqueta |
| Filas horarias y diarias en el CSV | Separarlas; no entrenar un pronóstico horario mezclando sus objetivos |
| Registros de cinco minutos en OpenAQ | Agregar por ventanas horarias con cobertura documentada; no tratarlos individualmente como promedios horarios |
| Definición de inicio y fin del intervalo | Contrastar FECHA/HORA_INICIO del CSV con datetimeFrom/datetimeTo de la API y evitar desplazar la serie una hora |
| Hora local y UTC | Convertir a una referencia común preservando America/Lima |
| Temperatura, humedad y viento | Las fichas consultadas de las dos estaciones coincidentes solo listan PM10 y PM2.5; no hay una fuente meteorológica equivalente comprobada para esas características |
| Valores cero | No sustituirlos automáticamente por datos faltantes; revisar indicadores de calidad del proveedor |
| Huecos temporales | Construir pares y ventanas solo en tramos válidos; no unir como consecutivas observaciones separadas por días |

OpenAQ documenta que `/sensors/{id}/hours` entrega el promedio horario. Para el pronóstico a una hora debe utilizarse una definición consistente del intervalo y evaluarse cronológicamente, sin utilizar mediciones futuras como características. [Documentación de mediciones](https://docs.openaq.org/resources/measurements).

## Alternativas con observaciones recientes comprobadas

Las fichas públicas muestran últimas observaciones de ubicación del 19/10/2026: San Borja y San Martín de Porres a las 11:00, Campo de Marte a las 09:00. Esta fecha es de la ubicación y puede corresponder a cualquier contaminante. Por eso se comprobó PM2.5 por separado en los archivos públicos.

Ventana de muestras: **09/10/2026 a 15/10/2026**, siete días completos de calendario local, con 168 horas potenciales. Los recuentos representan lo publicado en los archivos consultados y pueden cambiar si el proveedor completa datos posteriormente.

| Estación | ID ubicación | ID sensor PM2.5 | PM2.5 reciente en siete días | Fracción de 168 horas | Días con PM2.5 | Muestra del 15/10/2022 |
|---|---:|---:|---:|---:|---:|---:|
| [San Borja](https://explore.openaq.org/locations/2402) | 2402 | 4492 | 25 observaciones únicas | 14,88 % | 2 de 7 | 24 observaciones |
| [San Martín de Porres](https://explore.openaq.org/locations/2351) | 2351 | 4319 | 118 observaciones únicas | 70,24 % | 7 de 7 | 24 observaciones |
| [Campo de Marte](https://explore.openaq.org/locations/2415) | 2415 | 4672 | 125 observaciones únicas | 74,40 % | 7 de 7 | 22 observaciones |

Las muestras de 2022 y 2026 mantienen el mismo ID de sensor PM2.5 en cada una de esas tres estaciones. Los valores recientes comprobados son numéricos, no negativos y están expresados en µg/m³. Esto prueba acceso a histórico y a observaciones recientes de un mismo sensor, pero una muestra de siete días y un día histórico no certifican la continuidad completa ni el rendimiento de un modelo.

Ejemplo público verificable: [Campo de Marte, 15/10/2026](https://openaq-data-archive.s3.amazonaws.com/records/csv.gz/locationid=2415/year=2026/month=10/location-2415-20261015.csv.gz). Cada archivo contiene todos los contaminantes disponibles; se filtró `parameter=pm25` y su sensor.

## Decisión propuesta para el proyecto

1. **No aprobar la combinación directa del CSV OEFA con actualizaciones actuales de OpenAQ** para el modelo operativo: las dos series horarias reconstruibles no tienen actualizaciones de 2026 en las fichas comprobadas.
2. Si se mantiene el objetivo de una aplicación con datos actuales, empezar con **Campo de Marte, PM2.5, sensor 4672**, usando OpenAQ para histórico y nuevas mediciones. San Martín de Porres es una segunda candidata. Ambas requieren auditar un intervalo de entrenamiento suficientemente largo y reciente antes de fijar la selección.
3. No incorporar al entrenamiento operativo las observaciones OEFA como si pertenecieran a Campo de Marte. No existe equivalencia de estación. Un modelo entre estaciones sería un experimento adicional con evaluación de transferencia.
4. Para validar el flujo en producción falta la comprobación autenticada de `/sensors/4672/hours`, con una clave propia de OpenAQ, y una auditoría ampliada de cobertura, intervalos y calidad del sensor. La muestra disponible permite seleccionar un candidato, no certificar su disponibilidad futura.
5. El archivo AWS es una vía oficial sin credenciales para el histórico y la auditoría. OpenAQ documenta que se escribe **72 horas después de terminar el día local**, por lo que esa vía tiene retraso y no sirve por sí sola como entrada de un pronóstico de la próxima hora. [Estructura y frecuencia del archivo](https://docs.openaq.org/aws/about), [acceso público](https://docs.openaq.org/aws/quick-start).

La clave de la API se configura localmente como credencial del proyecto; no debe incluirse en el código o en este informe. [Autenticación de OpenAQ](https://docs.openaq.org/using-the-api/quick-start).
