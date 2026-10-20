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
    private final android.os.Handler handler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable freshnessCheck=new Runnable(){public void run(){render(ForecastData.cached(MainActivity.this));handler.postDelayed(this,60000);}};
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll=new ScrollView(this); LinearLayout box=new LinearLayout(this);box.setOrientation(1);box.setPadding(28,64,28,28);box.setBackgroundColor(Color.rgb(245,247,239));scroll.addView(box);setContentView(scroll);
        TextView title=new TextView(this);title.setText("AirePredict\nCampo de Marte");title.setTextSize(30);title.setTextColor(Color.rgb(22,117,103));box.addView(title);
        value=new TextView(this);value.setTextSize(40);box.addView(value);
        date=new TextView(this);box.addView(date);status=new TextView(this);box.addView(status);
        EditText origin=new EditText(this);origin.setSingleLine(true);origin.setHint("https://your-airpredict-server");origin.setText(ForecastData.baseUrl(this));origin.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);box.addView(origin);
        button(box,"Connect server",()->{try{String url=ForecastData.validateUrl(origin.getText().toString());ForecastData.preferences(this).edit().putString("base_url",url).remove("forecast").apply();refresh();ForecastJob.schedule(this);}catch(Exception e){status.setText(e.getMessage());}});
        button(box,"Refresh forecast",this::refresh);
        button(box,"Open full app / historical demonstration",()->{try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(ForecastData.validateUrl(ForecastData.baseUrl(this)))));}catch(Exception e){status.setText("Connect your HTTPS server first.");}});
        button(box,"Add home-screen widget",()->{AppWidgetManager manager=getSystemService(AppWidgetManager.class);if(manager.isRequestPinAppWidgetSupported()){manager.requestPinAppWidget(new ComponentName(this,ForecastWidget.class),null,null);status.setText("Confirm the widget request on your home screen.");}else status.setText("Long-press your home screen and select Widgets → AirePredict.");});
        button(box,"Enable forecast notifications",()->{ForecastData.preferences(this).edit().putBoolean("notifications",true).apply();if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},100);else status.setText("Notifications enabled for new current forecasts. Background updates depend on Android.");});
        button(box,"Disable notifications",()->{ForecastData.preferences(this).edit().putBoolean("notifications",false).apply();status.setText("Notifications disabled. Forecast consultation remains available.");});
        TextView note=new TextView(this);note.setText("Experimental next-hour PM2.5 concentration. Not an official measurement. Widget refreshes are controlled by Android; read the forecast time. No location or overlay permission is required.");box.addView(note);
        render(ForecastData.cached(this));ForecastJob.schedule(this);
        if(!ForecastData.baseUrl(this).isEmpty())refresh();
    }
    private void button(LinearLayout box,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setOnClickListener(v->action.run());box.addView(b);}
    private void render(JSONObject data){boolean fresh=ForecastData.fresh(data);value.setText(fresh?ForecastData.value(data):"— µg/m³");date.setText(ForecastData.time(data));status.setText(fresh?"Current · experimental":"No fresh forecast. Connect and refresh, or open the labelled historical demonstration.");}
    private void refresh(){status.setText("Loading current observations…");new Thread(()->{try{JSONObject data=ForecastData.fetch(this);runOnUiThread(()->render(data));ForecastWidget.refreshAll(this);}catch(Exception e){runOnUiThread(()->{render(ForecastData.cached(this));status.setText("Could not refresh current observations. Check your connection and server URL. Cached forecasts are shown only while their target hour is in the future.");});}}).start();}
    @Override protected void onResume(){super.onResume();handler.post(freshnessCheck);}
    @Override protected void onPause(){handler.removeCallbacks(freshnessCheck);super.onPause();}
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==100){boolean granted=results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED;ForecastData.preferences(this).edit().putBoolean("notifications",granted).apply();status.setText(granted?"Notifications enabled.":"Notifications declined. The app and widget remain available.");}}
}
