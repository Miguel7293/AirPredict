package pe.airepredict;
import android.Manifest;
import android.app.*;
import android.app.job.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Build;
import org.json.JSONObject;

public class ForecastJob extends JobService {
    static JobInfo.Builder builder(Context c,int id){return new JobInfo.Builder(id,new ComponentName(c,ForecastJob.class)).setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY);}
    static void schedule(Context c){JobScheduler scheduler=c.getSystemService(JobScheduler.class);if(scheduler.getPendingJob(1)==null)scheduler.schedule(builder(c,1).setPeriodic(1800000).setPersisted(true).build());}
    static void now(Context c){c.getSystemService(JobScheduler.class).schedule(builder(c,2).setOverrideDeadline(1000).build());}
    @Override public boolean onStartJob(JobParameters params){new Thread(()->{try{JSONObject data=ForecastData.fetch(this);notifyForecast(data);}catch(Exception ignored){}finally{ForecastWidget.refreshAll(this);jobFinished(params,false);}}).start();return true;}
    @Override public boolean onStopJob(JobParameters params){return true;}
    private void notifyForecast(JSONObject data){
        if(data.optInt("location_id")!=ForecastData.stationId(this))return;
        if(!ForecastData.preferences(this).getBoolean("notifications",false)||!ForecastData.fresh(data))return;
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return;
        String time=data.optString("target_time_utc");if((data.optInt("location_id")+"/"+time).equals(ForecastData.preferences(this).getString("notified_time","")))return;
        NotificationManager manager=getSystemService(NotificationManager.class);manager.createNotificationChannel(new NotificationChannel("forecast","Predicciones actuales",NotificationManager.IMPORTANCE_LOW));
        Notification notification=new Notification.Builder(this,"forecast").setSmallIcon(R.drawable.app_icon).setContentTitle(data.optString("station","Tu distrito")+" · experimental").setContentText(ForecastData.value(data)+" · "+ForecastData.time(data)).setContentIntent(PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE)).setAutoCancel(true).setTimeoutAfter(Math.max(1,java.time.OffsetDateTime.parse(time).toInstant().toEpochMilli()-System.currentTimeMillis())).build();
        manager.notify(1,notification);ForecastData.preferences(this).edit().putString("notified_time",data.optInt("location_id")+"/"+time).apply();
    }
}
