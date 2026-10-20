package pe.airepredict;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;
import org.json.JSONObject;

public class ForecastWidget extends AppWidgetProvider {
    static void refreshAll(Context c){AppWidgetManager m=AppWidgetManager.getInstance(c);update(c,m,m.getAppWidgetIds(new ComponentName(c,ForecastWidget.class)));}
    static void update(Context c,AppWidgetManager manager,int[] ids){
        JSONObject data=ForecastData.cached(c);boolean fresh=ForecastData.fresh(data);
        for(int id:ids){RemoteViews view=new RemoteViews(c.getPackageName(),R.layout.forecast_widget);
            view.setTextViewText(R.id.widget_title,"AIREPREDICT · "+ForecastData.stationName(c));
            view.setTextViewText(R.id.widget_value,fresh?ForecastData.value(data):"— µg/m³");
            view.setTextViewText(R.id.widget_status,fresh?"Experimental · válida solo hasta la hora indicada":"Desactualizada / no disponible · abre la aplicación para actualizar");
            view.setTextViewText(R.id.widget_time,ForecastData.time(data));
            view.setOnClickPendingIntent(R.id.widget_root,PendingIntent.getActivity(c,id,new Intent(c,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT));manager.updateAppWidget(id,view);
        }
    }
    @Override public void onUpdate(Context c,AppWidgetManager manager,int[] ids){update(c,manager,ids);ForecastJob.schedule(c);ForecastJob.now(c);}
    @Override public void onEnabled(Context c){ForecastJob.schedule(c);}
}
