package pe.airepredict;

import android.Manifest;
import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.graphics.Color;
import android.widget.*;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private TextView status, value, date;
    private JSONObject displayed=new JSONObject();
    private final android.os.Handler handler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable freshnessCheck=new Runnable(){public void run(){render(displayed);handler.postDelayed(this,60000);}};
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll=new ScrollView(this); LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(28,64,28,28);box.setBackgroundColor(Color.rgb(245,247,239));scroll.addView(box);setContentView(scroll);
        TextView title=new TextView(this);title.setText("AirePredict\nCampo de Marte");title.setTextSize(30);title.setTextColor(Color.rgb(22,117,103));box.addView(title);
        value=new TextView(this);value.setTextSize(40);box.addView(value);
        date=new TextView(this);box.addView(date);status=new TextView(this);box.addView(status);
        EditText origin=new EditText(this);origin.setSingleLine(true);origin.setHint("https://tu-servidor-airpredict");origin.setText(ForecastData.baseUrl(this));origin.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);box.addView(origin);
        Button connectButton=button(box,"Conectar servidor",()->{try{String url=ForecastData.validateUrl(origin.getText().toString());ForecastData.preferences(this).edit().putString("base_url",url).remove("forecast").apply();refresh();ForecastJob.schedule(this);}catch(Exception e){status.setText(e.getMessage());}});
        if(!BuildConfig.DEFAULT_BASE_URL.isEmpty()){origin.setVisibility(android.view.View.GONE);connectButton.setVisibility(android.view.View.GONE);button(box,"Configuración de conexión",()->{boolean hidden=origin.getVisibility()!=android.view.View.VISIBLE;origin.setVisibility(hidden?android.view.View.VISIBLE:android.view.View.GONE);connectButton.setVisibility(hidden?android.view.View.VISIBLE:android.view.View.GONE);});}
        button(box,"Actualizar predicción",this::refresh);
        button(box,"Explorar predicción histórica",()->{status.setText("Cargando el ejemplo histórico…");new Thread(()->{try{JSONObject data=ForecastData.historical(this);runOnUiThread(()->render(data));}catch(Exception e){runOnUiThread(()->status.setText("No se pudo cargar el ejemplo histórico. Revisa la conexión e inténtalo de nuevo."));}}).start();});
        button(box,"Abrir aplicación completa / demostración histórica",()->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(ForecastData.validateUrl(ForecastData.baseUrl(this)))));}catch(Exception e){status.setText("Conecta primero tu servidor HTTPS.");}});
        button(box,"Añadir widget a la pantalla de inicio",()->{AppWidgetManager manager=getSystemService(AppWidgetManager.class);if(manager.isRequestPinAppWidgetSupported()){manager.requestPinAppWidget(new ComponentName(this,ForecastWidget.class),null,null);status.setText("Confirma la solicitud del widget en tu pantalla de inicio.");}else status.setText("Mantén pulsada la pantalla de inicio y selecciona Widgets → AirePredict.");});
        button(box,"Activar notificaciones de predicción",()->{ForecastData.preferences(this).edit().putBoolean("notifications",true).apply();if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},100);else status.setText("Notificaciones activadas para nuevas predicciones actuales. Las actualizaciones en segundo plano dependen de Android.");});
        button(box,"Desactivar notificaciones",()->{ForecastData.preferences(this).edit().putBoolean("notifications",false).apply();status.setText("Notificaciones desactivadas. Puedes seguir consultando las predicciones.");});
        TextView note=new TextView(this);note.setText("Concentración experimental de PM2.5 para la próxima hora. No es una medición oficial. Android controla las actualizaciones del widget; revisa la hora de la predicción. No se requieren permisos de ubicación ni de superposición.");box.addView(note);
        render(ForecastData.cached(this));ForecastJob.schedule(this);
        if(!ForecastData.baseUrl(this).isEmpty())refresh();
    }
    private Button button(LinearLayout box,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setOnClickListener(v->action.run());box.addView(b);return b;}
    private void render(JSONObject data){displayed=data;boolean fresh=ForecastData.fresh(data),historical=data.optString("mode").equals("historical");value.setText(fresh||historical?ForecastData.value(data):"— µg/m³");date.setText(ForecastData.time(data));status.setText(historical?"Ejemplo histórico · no representa las condiciones actuales del aire":fresh?"Actual · experimental":"No hay una predicción reciente. Explora la demostración histórica.");}
    private void refresh(){status.setText("Cargando observaciones actuales…");new Thread(()->{try{JSONObject data=ForecastData.fetch(this);runOnUiThread(()->render(data));ForecastWidget.refreshAll(this);}catch(Exception e){runOnUiThread(()->{render(ForecastData.cached(this));status.setText("No se pudieron actualizar las observaciones actuales. Revisa la conexión y la dirección del servidor. Las predicciones guardadas solo se muestran si su hora estimada aún está en el futuro.");});}}).start();}
    @Override protected void onResume(){super.onResume();handler.post(freshnessCheck);}
    @Override protected void onPause(){handler.removeCallbacks(freshnessCheck);super.onPause();}
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==100){boolean granted=results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED;ForecastData.preferences(this).edit().putBoolean("notifications",granted).apply();status.setText(granted?"Notificaciones activadas.":"Notificaciones rechazadas. La aplicación y el widget siguen disponibles.");}}
}
