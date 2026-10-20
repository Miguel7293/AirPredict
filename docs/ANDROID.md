# Aplicación y widget Android

El aplicativo consulta el servicio HTTPS publicado. Permite explorar la demostración histórica, solicitar una predicción actual cuando existen datos frescos, abrir la web completa, añadir el widget y habilitar o deshabilitar notificaciones.

## Instalación de demostración

Descargar el APK de [Releases](https://github.com/Miguel7293/AirPredict/releases). Requiere Android 8 o posterior; las pruebas de dispositivo se ejecutan en Android 15. Es un APK firmado para pruebas y no una publicación en Google Play. Las compilaciones de CI pueden usar certificados de prueba distintos; si Android rechaza actualizar un APK anterior, desinstalar primero esa versión de demostración.

El servidor viene configurado durante la compilación desde la variable GitHub `APP_BASE_URL`. Connection settings permite cambiarlo a otro origen HTTPS compatible. La clave de OpenAQ y las credenciales administrativas nunca se incluyen en el APK.

## Widget y permisos

Pulsar Add home-screen widget y confirmar la solicitud del launcher. Si no admite ese mecanismo, añadir AirePredict desde el selector de widgets de la pantalla de inicio. El widget abre la app al tocarlo y muestra la hora objetivo. Android controla la frecuencia de las actualizaciones; el periodo solicitado es de 30 minutos.

Enable forecast notifications solicita el permiso de notificaciones en las versiones de Android que lo requieren. Rechazarlo mantiene disponible la consulta y el widget. Disable notifications desactiva la preferencia. Las notificaciones informan de nuevas predicciones actuales; no representan alertas sanitarias oficiales.

No se solicita ubicación, cámara, micrófono ni superposición sobre otras aplicaciones. Campo de Marte es una estación fija. Si no existe una predicción fresca, el widget muestra su indisponibilidad; no sustituye ese estado por el ejemplo histórico.

## Desarrollo y construcción

Herramientas: JDK 17, Gradle 8.14, Android SDK Platform 35 y Build Tools 35.0.0. Abrir la carpeta android en Android Studio o usar Gradle instalado:

```powershell
$env:APP_BASE_URL='https://airpredict-4u3c.onrender.com'
gradle -p android assembleDebug lintDebug
```

El APK se genera en `android/app/build/outputs/apk/debug/`. La compilación también está automatizada en Android application de GitHub Actions. Su ejecución manual añade las pruebas de emulador y guarda capturas e informes como artefactos.

Las pruebas comprueban expiración de pronósticos, rechazo de orígenes inseguros, registro del proveedor del widget, apertura del aplicativo, rechazo de notificaciones y vinculación/renderizado del widget en un host Android de pruebas. El permiso de vinculación del host se concede únicamente dentro del emulador de CI; el aplicativo distribuido usa la confirmación normal del launcher.
