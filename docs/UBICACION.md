# Ubicación opcional en web y Android — versión 0.4.1

«Usar mi ubicación» busca referencias cercanas para el modelo seleccionado. En el modelo general se consideran puntos representados en el entrenamiento y con PM2.5 diario. En estaciones se consideran los tres sensores configurados, con su fecha y estado de datos recientes. El usuario elige qué referencia consultar.

Se muestran hasta tres resultados ordenados por distancia geográfica. Se utiliza Haversine con radio terrestre de 6.371 km y un rango de consulta de 25 km. Se exige que distancia más margen de ubicación no superen ese rango. Es un criterio de búsqueda, **no una validación científica de cobertura o precisión espacial** del modelo. Un punto sin mediciones recientes no se transforma en una predicción actual por estar cerca.

## Web

Se solicita `navigator.geolocation.getCurrentPosition` únicamente tras pulsar el botón. Se admite ubicación aproximada, tiempo máximo de 20 s y antigüedad máxima solicitada de 60 s. Se informa de permiso rechazado, falta de soporte, ubicación no disponible o tiempo agotado. La política HTTP habilita geolocalización solo para el origen de la aplicación; cámara y micrófono siguen deshabilitados.

El mapa muestra el punto del usuario y su margen informado. Los resultados distinguen referencias históricas de mediciones recientes. Seleccionar uno abre su análisis y conserva las coordenadas del **punto de monitoreo** en el modelo. No se sustituyen silenciosamente por las coordenadas de una ubicación no validada. «Quitar mi ubicación» elimina la posición y las capas de la página; los permisos concedidos se revocan desde los ajustes del navegador.

## Android

Inicio y Mapa incorporan el botón que abre «Cerca de ti». Solo se declara y solicita `ACCESS_COARSE_LOCATION`, de forma opcional y mientras se usa la pantalla. No se solicita ubicación precisa ni permiso de ubicación en segundo plano. Se usa LocationManager con una solicitud única y cancelación tras 25 s o al salir. Una posición con más de cinco minutos de antigüedad se rechaza. Se muestran por separado estaciones y referencias históricas del modelo general.

La pantalla permite abrir una estación o su punto histórico en la aplicación. El mapa integrado remite al botón nativo; no se concede geolocalización a contenido de WebView ni se añade un puente JavaScript nativo.

## Tratamiento de coordenadas y límites

Las coordenadas se mantienen en memoria del dispositivo. No se envían en peticiones HTTP, no se incluyen en URL, no se guardan en preferencias, cookies ni almacenamiento local. Se solicitan al servidor únicamente los catálogos públicos ya existentes. Al abrir un resultado se transmite el identificador público del punto seleccionado, igual que al seleccionarlo manualmente. La cartografía se sirve junto a la aplicación, sin enviar la posición a proveedores externos de mapas.

La ubicación ayuda a elegir referencias. La predicción corresponde a su punto de medición y fecha; no estima automáticamente el aire exacto de una vivienda. Si no existe una referencia adecuada, se informa y se mantiene la selección manual. No se modifica ni reentrena ningún modelo.

## Validación

Pruebas de distancia conocida, coordenadas inválidas, orden por cercanía, ausencia de referencias y margen demasiado amplio. En web se prueban permiso aceptado con coordenadas sintéticas, rechazo, error de tiempo y falta de soporte sin obtener la ubicación real del operador. Android prueba el permiso opcional rechazado y una ubicación aproximada sintética de Lima que debe mostrar referencias próximas. Los ejemplos sintéticos validan la interfaz y el cálculo, no la recepción física de GPS en cada dispositivo.

Referencias: [Geolocation API](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition), [permisos de ubicación Android](https://developer.android.com/develop/sensors-and-location/location/permissions).
