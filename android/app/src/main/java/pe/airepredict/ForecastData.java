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
    static SharedPreferences preferences(Context c) { return c.getSharedPreferences("airepredict", Context.MODE_PRIVATE); }
    static String baseUrl(Context c) { return preferences(c).getString("base_url", BuildConfig.DEFAULT_BASE_URL); }
    static String validateUrl(String value) {
        String clean=value.trim().replaceAll("/+$", "");
        try { URL u=new URL(clean); if(!u.getProtocol().equals("https") || u.getHost().isEmpty() || u.getUserInfo()!=null || !u.getPath().isEmpty() || u.getQuery()!=null || u.getRef()!=null) throw new Exception(); }
        catch(Exception e) { throw new IllegalArgumentException("Enter an HTTPS server origin without a path."); }
        return clean;
    }
    static JSONObject cached(Context c) {
        try { return new JSONObject(preferences(c).getString("forecast", "{}")); } catch(Exception e) { return new JSONObject(); }
    }
    static boolean fresh(JSONObject data) {
        try { return data.getBoolean("is_current_forecast") && OffsetDateTime.parse(data.getString("target_time_utc")).toInstant().toEpochMilli()>System.currentTimeMillis(); }
        catch(Exception e) { return false; }
    }
    static JSONObject fetch(Context c) throws Exception {
        String origin=validateUrl(baseUrl(c));
        HttpsURLConnection conn=(HttpsURLConnection)new URL(origin+"/api/forecast").openConnection();
        conn.setConnectTimeout(8000); conn.setReadTimeout(8000); conn.setInstanceFollowRedirects(false);
        try {
            if(conn.getResponseCode()!=200) throw new Exception("Fresh observations are unavailable. Historical examples are available in the full app.");
            java.io.BufferedReader reader=new java.io.BufferedReader(new java.io.InputStreamReader(conn.getInputStream(),StandardCharsets.UTF_8));
            StringBuilder body=new StringBuilder(); char[] block=new char[4096];int count;
            while((count=reader.read(block))!=-1){body.append(block,0,count);if(body.length()>1000000)throw new Exception("Response too large");}
            JSONObject data=new JSONObject(body.toString());
            if(!fresh(data)) throw new Exception("The forecast is outdated.");
            preferences(c).edit().putString("forecast",data.toString()).putLong("fetched_at",System.currentTimeMillis()).apply();
            return data;
        } finally { conn.disconnect(); }
    }
    static String value(JSONObject data) { return String.format(Locale.US,"%.2f µg/m³",data.optDouble("predicted_pm25",0)); }
    static String time(JSONObject data) {
        try { return OffsetDateTime.parse(data.getString("target_time_utc")).atZoneSameInstant(ZoneId.of("America/Lima")).format(DateTimeFormatter.ofPattern("dd MMM HH:mm",Locale.ENGLISH))+" Lima"; }
        catch(Exception e) { return "No forecast timestamp"; }
    }
}
