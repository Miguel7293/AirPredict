package pe.airepredict;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.location.*;
import android.os.*;
import android.widget.*;
import org.json.*;
import java.util.*;

/** One foreground, approximate fix. Coordinates never enter HTTP or preferences. */
public class NearbyActivity extends Activity {
    private TextView status;private LinearLayout results;private LocationManager manager;
    private CancellationSignal cancellation;private LocationListener listener;private int sequence=0;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable timeout=()->finishLocation("La ubicación tardó demasiado. Revisa que esté activada o selecciona un punto manualmente.");
    @Override public void onCreate(Bundle state){super.onCreate(state);
        ScrollView scroll=new ScrollView(this);LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(28,48,28,32);box.setBackgroundColor(Color.rgb(246,247,242));scroll.addView(box);setContentView(scroll);
        box.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(28,insets.getSystemWindowInsetTop()+28,28,insets.getSystemWindowInsetBottom()+28);return insets;});
        add(box,"Cerca de ti",30);add(box,"Usa tu ubicación aproximada para buscar puntos de monitoreo en un rango de 25 km. El permiso es opcional.",15);
        add(box,"La ubicación se procesa en el teléfono, sin guardarla ni enviarla al servidor. Las mediciones y predicciones pertenecen al punto seleccionado, no a tu dirección.",13);
        button(box,"Usar mi ubicación",this::requestLocation);button(box,"Quitar mi ubicación",()->{cancelLocation();++sequence;results.removeAllViews();status.setText("Ubicación eliminada de esta pantalla. Puedes cambiar el permiso en Ajustes de Android.");});
        status=add(box,"Pulsa el botón para solicitar el permiso. Puedes volver y seleccionar un punto manualmente.",14);results=new LinearLayout(this);results.setOrientation(LinearLayout.VERTICAL);box.addView(results);button(box,"Volver",this::finish);
        manager=getSystemService(LocationManager.class);
    }
    private TextView add(LinearLayout box,String label,int size){TextView text=new TextView(this);text.setText(label);text.setTextSize(size);text.setTextColor(Color.rgb(18,63,60));text.setPadding(0,12,0,15);box.addView(text);return text;}
    private void button(LinearLayout box,String label,Runnable action){Button button=AppButtons.create(this,label,!label.equals("Volver"));LinearLayout.LayoutParams layout=new LinearLayout.LayoutParams(-1,-2);layout.setMargins(0,8,0,8);box.addView(button,layout);button.setOnClickListener(v->action.run());}
    private void requestLocation(){
        if(checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.ACCESS_COARSE_LOCATION},201);return;}
        locate();
    }
    @android.annotation.SuppressLint("MissingPermission") private void locate(){
        cancelLocation();final int requestSequence=++sequence;results.removeAllViews();status.setText("Buscando tu ubicación aproximada…");
        String provider=Build.VERSION.SDK_INT>=31&&manager.getProviders(true).contains("fused")?"fused":LocationManager.NETWORK_PROVIDER;
        try{
            if(!manager.isProviderEnabled(provider)){finishLocation("Activa la ubicación del teléfono o selecciona un punto manualmente.");return;}
            handler.postDelayed(timeout,25000);
            if(Build.VERSION.SDK_INT>=30){cancellation=new CancellationSignal();manager.getCurrentLocation(provider,cancellation,getMainExecutor(),position->{if(sequence==requestSequence)acceptLocation(position);});}
            else{listener=new LocationListener(){public void onLocationChanged(Location location){if(sequence==requestSequence)acceptLocation(location);}public void onStatusChanged(String p,int s,Bundle b){}public void onProviderEnabled(String p){}public void onProviderDisabled(String p){if(sequence==requestSequence)finishLocation("La ubicación está desactivada. Puedes consultar el mapa manualmente.");}};manager.requestSingleUpdate(provider,listener,Looper.getMainLooper());}
        }catch(SecurityException error){finishLocation("No se concedió el permiso de ubicación. Puedes consultar los puntos manualmente.");}catch(IllegalArgumentException error){finishLocation("Este dispositivo no ofrece ubicación aproximada. Puedes seleccionar un punto manualmente.");}
    }
    private void cancelLocation(){handler.removeCallbacks(timeout);if(cancellation!=null){cancellation.cancel();cancellation=null;}if(listener!=null&&manager!=null){manager.removeUpdates(listener);listener=null;}}
    private void finishLocation(String message){cancelLocation();status.setText(message);}
    void acceptLocation(Location position){
        cancelLocation();if(position==null||!valid(position.getLatitude(),position.getLongitude())||!position.hasAccuracy()||position.getAccuracy()<0||!Float.isFinite(position.getAccuracy())){status.setText("No se recibió una ubicación válida. Vuelve a intentarlo.");return;}
        if(SystemClock.elapsedRealtimeNanos()-position.getElapsedRealtimeNanos()>300000000000L){status.setText("La ubicación recibida es antigua. Vuelve a intentarlo.");return;}
        int token=++sequence;double latitude=position.getLatitude(),longitude=position.getLongitude(),margin=position.getAccuracy()/1000.;
        status.setText("Ubicación obtenida. Margen aproximado: ±"+format(margin)+" km. Buscando puntos cercanos…");
        new Thread(()->{try{JSONArray general=ForecastData.request(this,"/api/atlas").getJSONArray("sites"),stations=ForecastData.request(this,"/api/stations").getJSONArray("stations");runOnUiThread(()->{if(sequence==token){results.removeAllViews();if(distanceKm(latitude,longitude,-15.84,-70.02)+margin<=25){add(results,"Puno · calidad del aire",21);add(results,"Datos modelados por CAMS, sin estación física ni alertas de salud.",15);button(results,"Consultar Puno",()->startActivity(new Intent(this,PunoActivity.class)));}render(stations,false,latitude,longitude,margin);render(general,true,latitude,longitude,margin);status.setText("Referencias a un máximo de 25 km, considerando un margen aproximado de ±"+format(margin)+" km. La cercanía no garantiza una predicción para tu dirección.");}});}catch(Exception error){runOnUiThread(()->{if(sequence==token)status.setText("Ubicación obtenida, pero no se pudieron consultar los puntos. Revisa la conexión e inténtalo de nuevo.");});}}).start();
    }
    private void render(JSONArray items,boolean historical,double latitude,double longitude,double margin){
        add(results,historical?"Modelo general · referencias históricas":"Estaciones disponibles",21);List<JSONObject> candidates=new ArrayList<>();
        for(int i=0;i<items.length();i++){JSONObject site=items.optJSONObject(i);if(site==null||historical&&(!site.optBoolean("trained")||site.optInt("daily_count")==0))continue;double distance=distanceKm(latitude,longitude,site.optDouble("latitude",Double.NaN),site.optDouble("longitude",Double.NaN));if(distance+margin<=25)try{JSONObject copy=new JSONObject(site.toString());copy.put("distance_km",distance);candidates.add(copy);}catch(JSONException ignored){}}
        candidates.sort(Comparator.comparingDouble(s->s.optDouble("distance_km")));
        if(candidates.isEmpty()){add(results,"No hay puntos con datos dentro del rango de consulta. Puedes explorar otros puntos manualmente.",13);return;}
        int index=0;
        for(JSONObject site:candidates.subList(0,Math.min(3,candidates.size()))){String name=historical?site.optString("district")+" · "+site.optString("code"):site.optString("name");
            if(index++==0)add(results,historical?"Este es el punto histórico más cercano a tu ubicación:":"La estación más cercana a tu punto registró lo siguiente:",16);
            add(results,name+" · "+format(site.optDouble("distance_km"))+" km aprox.",17);
            add(results,historical?"Referencia histórica · último dato: "+site.optString("last_date")+". Abre el punto para simular una medición diaria y, debajo, consultar su análisis histórico.":stationReading(site),13);
            button(results,historical?"Simular y ver histórico":"Consultar "+name,()->{Intent intent=new Intent(this,MainActivity.class);if(historical)intent.putExtra("site_id",site.optString("id"));else intent.putExtra("station_id",site.optInt("id"));startActivity(intent);});}
    }
    static String stationReading(JSONObject site){JSONObject last=site.optJSONObject("latest");if(last==null||!Double.isFinite(last.optDouble("pm25",Double.NaN)))return "Todavía no hay una medición publicada para esta estación.";
        return String.format(Locale.forLanguageTag("es-PE"),"Registró %.2f µg/m³ de PM2.5 el %s. %s",last.optDouble("pm25"),ForecastData.formatTime(last.optString("timestamp")),site.optBoolean("fresh")?"Revisa la disponibilidad de su predicción horaria.":"Es la última medición recibida; no describe necesariamente el aire de este momento.");}

    static boolean valid(double lat,double lon){return Double.isFinite(lat)&&Double.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180;}
    static double distanceKm(double lat,double lon,double otherLat,double otherLon){if(!valid(lat,lon)||!valid(otherLat,otherLon))return Double.POSITIVE_INFINITY;double a=Math.pow(Math.sin(Math.toRadians(otherLat-lat)/2),2)+Math.cos(Math.toRadians(lat))*Math.cos(Math.toRadians(otherLat))*Math.pow(Math.sin(Math.toRadians(otherLon-lon)/2),2);return 6371*2*Math.atan2(Math.sqrt(Math.min(1,a)),Math.sqrt(Math.max(0,1-a)));}
    private String format(double value){return String.format(Locale.forLanguageTag("es-PE"),"%.2f",value);}
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] granted){super.onRequestPermissionsResult(request,permissions,granted);if(request==201){if(granted.length>0&&granted[0]==PackageManager.PERMISSION_GRANTED)locate();else status.setText("Permiso de ubicación rechazado. Puedes seguir seleccionando puntos manualmente.");}}
    @Override protected void onStop(){++sequence;cancelLocation();results.removeAllViews();super.onStop();}
}
