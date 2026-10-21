package pe.airepredict;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.net.URL;
import javax.net.ssl.HttpsURLConnection;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

final class ForecastData {
    static final int[] IDS={2415,2402,2351};
    static final String[] NAMES={"Jesús María","San Borja","San Martín de Porres"};
    static SharedPreferences preferences(Context c){return c.getSharedPreferences("airepredict",Context.MODE_PRIVATE);}
    static String baseUrl(Context c){String fallback=BuildConfig.DEFAULT_BASE_URL.isEmpty()?"https://airpredict-4u3c.onrender.com":BuildConfig.DEFAULT_BASE_URL;String saved=preferences(c).getString("base_url",fallback);return saved.isEmpty()?fallback:saved;}
    static int stationId(Context c){int id=preferences(c).getInt("station_id",2415);for(int candidate:IDS)if(candidate==id)return id;return 2415;}
    static String stationName(Context c){int id=stationId(c);for(int i=0;i<IDS.length;i++)if(IDS[i]==id)return NAMES[i];return NAMES[0];}
    static String validateUrl(String value){String clean=value.trim().replaceAll("/+$","");try{URL u=new URL(clean);if(!u.getProtocol().equals("https")||u.getHost().isEmpty()||u.getUserInfo()!=null||!u.getPath().isEmpty()||u.getQuery()!=null||u.getRef()!=null)throw new Exception();}catch(Exception e){throw new IllegalArgumentException("Introduce una dirección HTTPS sin una ruta adicional.");}return clean;}
    static JSONObject cached(Context c){try{return new JSONObject(preferences(c).getString("forecast_"+stationId(c),"{}"));}catch(Exception e){return new JSONObject();}}
    static boolean fresh(JSONObject data){try{return data.getBoolean("is_current_forecast")&&OffsetDateTime.parse(data.getString("target_time_utc")).toInstant().toEpochMilli()>System.currentTimeMillis();}catch(Exception e){return false;}}
    static JSONObject request(Context c,String path) throws Exception{
        HttpsURLConnection conn=(HttpsURLConnection)new URL(validateUrl(baseUrl(c))+path).openConnection();
        // Allow free-host cold starts; distinguish HTTP 409 from network failure.
        conn.setConnectTimeout(20000);conn.setReadTimeout(70000);conn.setInstanceFollowRedirects(false);conn.setRequestProperty("Cache-Control","no-cache");
        try{
            int code=conn.getResponseCode();java.io.InputStream stream=code==200?conn.getInputStream():conn.getErrorStream();
            if(stream==null)throw new Exception("El servicio aún no responde. Espera y vuelve a intentarlo.");
            StringBuilder body=new StringBuilder();try(java.io.BufferedReader reader=new java.io.BufferedReader(new java.io.InputStreamReader(stream,StandardCharsets.UTF_8))){char[] block=new char[4096];int n;while((n=reader.read(block))!=-1){body.append(block,0,n);if(body.length()>2000000)throw new Exception("Respuesta demasiado grande.");}}
            JSONObject data;try{data=new JSONObject(body.toString());}catch(Exception e){throw new Exception("El servidor se está iniciando. Vuelve a intentarlo en un minuto.");}
            if(code!=200)throw new Exception(data.optString("detail","No se pudo consultar el servicio ("+code+")."));
            return data;
        }finally{conn.disconnect();}
    }
    static JSONObject fetch(Context c)throws Exception{return fetchStation(c,stationId(c),false);}
    static JSONObject historical(Context c)throws Exception{return fetchStation(c,stationId(c),true);}
    static JSONObject latest(Context c,int id)throws Exception{
        JSONObject data=request(c,"/api/stations/"+id+"/forecast?mode=latest");
        if(data.optInt("location_id")!=id||!data.optString("mode").equals("latest")||!Double.isFinite(data.optDouble("predicted_pm25",Double.NaN)))throw new Exception("Respuesta de predicción incompatible con el punto seleccionado.");
        // Delayed estimates are displayed in the app, never cached as live alerts.
        return data;
    }
    static JSONObject fetchStation(Context c,int id,boolean historical)throws Exception{
        JSONObject data=request(c,"/api/stations/"+id+"/forecast?mode="+(historical?"historical":"live"));
        if(data.optInt("location_id")!=id)throw new Exception("El servidor devolvió un punto de monitoreo diferente.");
        if(historical){if(!data.optString("mode").equals("historical")||data.optBoolean("is_current_forecast"))throw new Exception("Respuesta histórica inesperada.");}
        else{if(!fresh(data))throw new Exception("La predicción ha caducado.");preferences(c).edit().putString("forecast_"+id,data.toString()).apply();}
        return data;
    }
    static String value(JSONObject data){return String.format(Locale.forLanguageTag("es-PE"),"%.2f µg/m³",data.optDouble("predicted_pm25",0));}
    static String formatTime(String stamp){try{return OffsetDateTime.parse(stamp).atZoneSameInstant(ZoneId.of("America/Lima")).format(DateTimeFormatter.ofPattern("dd MMM yyyy · HH:mm",Locale.forLanguageTag("es-PE")))+" · Lima";}catch(Exception e){return "Sin fecha de medición";}}
    static String time(JSONObject data){return formatTime(data.optString("target_time_utc"));}
}
