package pe.airepredict;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetHost;
import android.appwidget.AppWidgetHostView;
import android.content.ComponentName;
import android.content.Context;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.Until;
import androidx.test.uiautomator.UiScrollable;
import androidx.test.uiautomator.UiSelector;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.File;
import java.time.OffsetDateTime;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class ApplicationTest {
    private static void saveEvidence(String name) throws Exception {
        String path="/data/local/tmp/airepredict-"+name;
        shell("screencap -p "+path);
        assertTrue(shell("ls "+path).contains(path));
    }
    private static String shell(String command) throws Exception {
        android.os.ParcelFileDescriptor output=InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand(command);
        java.io.ByteArrayOutputStream text=new java.io.ByteArrayOutputStream();
        try(android.os.ParcelFileDescriptor.AutoCloseInputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(output)){int c;while((c=input.read())!=-1)text.write(c);}
        return text.toString("UTF-8");
    }
    @Test public void expiredForecastIsNeverCurrent() throws Exception {
        JSONObject data=new JSONObject();data.put("is_current_forecast",true);
        data.put("target_time_utc",OffsetDateTime.now().minusHours(1).toString());assertFalse(ForecastData.fresh(data));
        data.put("target_time_utc",OffsetDateTime.now().plusHours(1).toString());assertTrue(ForecastData.fresh(data));
        data.put("is_current_forecast",false);assertFalse(ForecastData.fresh(data));
    }
    @Test public void insecureOriginsAreRejected() {
        for(String url:new String[]{"http://example.com","https://user:pass@example.com","https://example.com/path"}){
            try{ForecastData.validateUrl(url);fail("Unsafe origin accepted");}catch(IllegalArgumentException expected){}
        }
        assertEquals("https://example.com",ForecastData.validateUrl("https://example.com/"));
    }
    @Test public void districtCachesNeverMix() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        ForecastData.preferences(context).edit().putInt("station_id",2402).putString("forecast_2402","{\"location_id\":2402}").putString("forecast_2351","{\"location_id\":2351}").commit();
        assertEquals(2402,ForecastData.cached(context).getInt("location_id"));
        ForecastData.preferences(context).edit().putInt("station_id",2351).commit();
        assertEquals(2351,ForecastData.cached(context).getInt("location_id"));
        ForecastData.preferences(context).edit().clear().commit();
    }
    @Test public void nearestStationReadingIncludesValueAndStaleness() throws Exception {
        JSONObject site=new JSONObject();assertTrue(NearbyActivity.stationReading(site).contains("no hay una medición"));
        site.put("latest",new JSONObject().put("pm25",24.9).put("timestamp","2026-10-19T08:00:00-05:00"));
        String reading=NearbyActivity.stationReading(site);assertTrue(reading.contains("24.90"));assertTrue(reading.contains("2026"));assertTrue(reading.contains("no describe necesariamente"));
    }
    private static android.webkit.WebView findWeb(android.view.View view){
        if(view instanceof android.webkit.WebView)return (android.webkit.WebView)view;
        if(view instanceof android.view.ViewGroup){android.view.ViewGroup group=(android.view.ViewGroup)view;for(int i=0;i<group.getChildCount();i++){android.webkit.WebView child=findWeb(group.getChildAt(i));if(child!=null)return child;}}return null;
    }
    private static JSONObject punoLayout(ActivityScenario<PunoActivity> screen) throws Exception {
        java.util.concurrent.CountDownLatch done=new java.util.concurrent.CountDownLatch(1);String[] result={"null"};
        screen.onActivity(activity->{android.webkit.WebView web=findWeb(activity.getWindow().getDecorView());assertNotNull(web);web.evaluateJavascript("JSON.stringify((()=>{const info=document.getElementById('puno-source-details'),value=document.getElementById('puno-value');return {ready:!!info&&!!value&&value.textContent!=='—',open:info?info.open:false,infoHeight:info?info.getBoundingClientRect().height:0,valueBottom:value?value.getBoundingClientRect().bottom:9999,height:innerHeight,width:innerWidth,contentWidth:document.documentElement.scrollWidth};})())",text->{result[0]=text;done.countDown();});});
        assertTrue(done.await(5,java.util.concurrent.TimeUnit.SECONDS));Object text=new org.json.JSONTokener(result[0]).nextValue();return text instanceof String?new JSONObject((String)text):new JSONObject();
    }
    @Test public void punoScreenFitsSmallDisplayAndSeparatesEstimatedData() throws Exception {
        for(String name:ForecastData.NAMES)assertFalse(name.contains("Puno"));
        shell("wm size 640x1136");shell("wm density 320");
        try(ActivityScenario<PunoActivity> screen=ActivityScenario.launch(PunoActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.text("Puno")),5000));
            JSONObject layout=new JSONObject();long deadline=android.os.SystemClock.elapsedRealtime()+90000;
            while(android.os.SystemClock.elapsedRealtime()<deadline){layout=punoLayout(screen);if(layout.optBoolean("ready"))break;android.os.SystemClock.sleep(350);}
            assertTrue("Expected the deployed Puno page and loaded estimate",layout.optBoolean("ready"));
            assertFalse("Source details start collapsed",layout.getBoolean("open"));
            assertTrue("Source notice must be compact",layout.getDouble("infoHeight")<75);
            assertTrue("Estimate must be visible on a small phone",layout.getDouble("valueBottom")<layout.getDouble("height"));
            assertTrue("No horizontal page overflow",layout.getDouble("contentWidth")<=layout.getDouble("width")+1);
            JSONObject data=ForecastData.request(InstrumentationRegistry.getInstrumentation().getTargetContext(),"/api/puno/experiment");
            assertEquals("experimental",data.getString("mode"));assertFalse(data.getBoolean("is_measurement"));assertFalse(data.getBoolean("health_alerts_enabled"));
            saveEvidence("puno.png");
        }finally{shell("wm size reset");shell("wm density reset");}
    }
    private static JSONObject mapLayout(ActivityScenario<MainActivity> screen) throws Exception {
        java.util.concurrent.CountDownLatch done=new java.util.concurrent.CountDownLatch(1);String[] result={"null"};
        screen.onActivity(activity->{android.webkit.WebView web=findWeb(activity.getWindow().getDecorView());assertNotNull(web);web.evaluateJavascript("JSON.stringify((()=>{const map=document.getElementById('map'),filters=document.getElementById('mobile-filters'),rect=map?map.getBoundingClientRect():{};return {ready:document.body.classList.contains('mobile-map')&&document.querySelectorAll('#map [role=button].leaflet-interactive').length>0,top:rect.top||0,bottom:rect.bottom||0,mapHeight:rect.height||0,height:innerHeight,width:innerWidth,contentWidth:document.documentElement.scrollWidth,filtersOpen:filters?filters.open:true,analysis:document.body.classList.contains('show-analysis')};})())",text->{result[0]=text;done.countDown();});});
        assertTrue(done.await(5,java.util.concurrent.TimeUnit.SECONDS));Object text=new org.json.JSONTokener(result[0]).nextValue();return text instanceof String?new JSONObject((String)text):new JSONObject();
    }
    @Test public void mapIsVisibleOnSmallDisplayAndDetailsOpenSeparately() throws Exception {
        shell("wm size 640x1136");shell("wm density 320");
        try(ActivityScenario<MainActivity> screen=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());device.wait(Until.findObject(By.text("Mapa")),5000).click();
            try{
                JSONObject layout=new JSONObject();long deadline=android.os.SystemClock.elapsedRealtime()+90000;
                while(android.os.SystemClock.elapsedRealtime()<deadline){layout=mapLayout(screen);if(layout.optBoolean("ready"))break;android.os.SystemClock.sleep(350);}
                assertTrue("Expected visible Leaflet markers in the map",layout.optBoolean("ready"));
                assertFalse(layout.getBoolean("filtersOpen"));assertTrue(layout.getDouble("mapHeight")>=180);
                assertTrue("Map begins inside viewport",layout.getDouble("top")>=0);
                assertTrue("Map is visible before scrolling",layout.getDouble("bottom")<=layout.getDouble("height")+1);
                assertTrue(layout.getDouble("contentWidth")<=layout.getDouble("width")+1);
                saveEvidence("map.png");device.wait(Until.findObject(By.text("Ver datos →")),5000).click();assertTrue(mapLayout(screen).getBoolean("analysis"));
                device.wait(Until.findObject(By.text("← Mapa")),5000).click();assertFalse(mapLayout(screen).getBoolean("analysis"));
            }catch(Throwable error){saveEvidence("map.png");throw error;}
        }finally{shell("wm size reset");shell("wm density reset");}
    }
    @Test public void launcherAndHeaderUseTheWebWindIcon() {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();assertTrue(context.getApplicationInfo().loadIcon(context.getPackageManager()) instanceof android.graphics.drawable.AdaptiveIconDrawable);
        android.graphics.drawable.Drawable icon=context.getDrawable(pe.airepredict.R.drawable.app_icon);android.graphics.Bitmap bitmap=android.graphics.Bitmap.createBitmap(192,192,android.graphics.Bitmap.Config.ARGB_8888);icon.setBounds(0,0,192,192);icon.draw(new android.graphics.Canvas(bitmap));
        assertEquals(android.graphics.Color.rgb(245,247,239),bitmap.getPixel(70,116));assertEquals(android.graphics.Color.rgb(22,117,103),bitmap.getPixel(96,170));assertEquals(0,android.graphics.Color.alpha(bitmap.getPixel(0,0)));
    }
    @Test public void nearbyDistanceAndUnknownCoordinatesAreHandled() {
        assertEquals(0,NearbyActivity.distanceKm(-12.07,-77.04,-12.07,-77.04),.0001);
        assertEquals(111.195,NearbyActivity.distanceKm(0,0,0,1),.01);
        assertTrue(Double.isInfinite(NearbyActivity.distanceKm(100,0,0,0)));
    }
    @Test public void locationIsOptionalAndDenialKeepsManualNavigation() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        shell("pm revoke "+context.getPackageName()+" android.permission.ACCESS_COARSE_LOCATION");
        shell("pm clear-permission-flags "+context.getPackageName()+" android.permission.ACCESS_COARSE_LOCATION user-set user-fixed");
        try(ActivityScenario<NearbyActivity> scenario=ActivityScenario.launch(NearbyActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertEquals(android.content.pm.PackageManager.PERMISSION_DENIED,context.checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION));
            device.wait(Until.findObject(By.text("Usar mi ubicación")),5000).click();
            androidx.test.uiautomator.UiObject2 deny=device.wait(Until.findObject(By.res("com.android.permissioncontroller","permission_deny_button")),10000);
            assertNotNull("Expected optional approximate location permission",deny);deny.click();
            if(device.findObject(new UiSelector().scrollable(true)).exists())new UiScrollable(new UiSelector().scrollable(true)).scrollToEnd(3);
            assertNotNull(device.wait(Until.findObject(By.textContains("Permiso de ubicación rechazado")),5000));
            assertNotNull(device.findObject(By.text("Volver")));
            saveEvidence("location.png");
        }
    }
    @Test public void injectedApproximateLocationShowsNearbyReferences() throws Exception {
        try(ActivityScenario<NearbyActivity> scenario=ActivityScenario.launch(NearbyActivity.class)){
            scenario.onActivity(activity->{android.location.Location sample=new android.location.Location("test-fixture");sample.setLatitude(-12.070544);sample.setLongitude(-77.043214);sample.setAccuracy(1000);sample.setTime(System.currentTimeMillis());sample.setElapsedRealtimeNanos(android.os.SystemClock.elapsedRealtimeNanos());activity.acceptLocation(sample);});
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.textContains("Referencias a un máximo")),90000));
            new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().textStartsWith("Jesús María ·"));
            assertNotNull(device.wait(Until.findObject(By.textContains("Jesús María ·")),90000));
            saveEvidence("location-nearby.png");
        }
    }
    @Test public void navigationSeparatesModelsAndConnectionSettings() throws Exception {
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.textContains("en perspectiva.")),5000));
            device.findObject(By.text("Estaciones")).click();
            assertNotNull(device.wait(Until.findObject(By.textContains("con contexto.")),5000));
            device.findObject(By.text("Ajustes")).click();
            assertNotNull(device.wait(Until.findObject(By.text("Guardar y comprobar conexión")),5000));
            saveEvidence("settings.png");
        }
    }
    @Test public void historicalScreenConnectsToPublishedStationService() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        ForecastData.preferences(context).edit().putInt("station_id",2402).commit();
        JSONObject response=ForecastData.fetchStation(context,2402,true);
        assertEquals(2402,response.getInt("location_id"));
        assertEquals("historical",response.getString("mode"));
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            device.wait(Until.findObject(By.text("Estaciones")),5000).click();
            device.wait(Until.findObject(By.text("Explorar predicción histórica")),5000).click();
            new UiScrollable(new UiSelector().scrollable(true)).scrollToEnd(5);
            assertNotNull(device.wait(Until.findObject(By.textContains("Ejemplo histórico: no describe")),90000));
            saveEvidence("station-connected.png");
        }finally{ForecastData.preferences(context).edit().clear().commit();}
    }
    @Test public void homeScreenWidgetIsRegistered() {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertTrue(AppWidgetManager.getInstance(context).getInstalledProviders().stream().anyMatch(provider->provider.provider.getClassName().equals(ForecastWidget.class.getName())));
    }
    @Test public void appLaunchesWithOptionalPermissions() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        ForecastData.preferences(context).edit().clear().commit();
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.textContains("AirePredict")),10000));
            File directory=context.getExternalFilesDir(null);
            saveEvidence("application.png");
        }
    }
    @Test public void decliningNotificationsKeepsAppAvailable() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        shell("pm revoke "+context.getPackageName()+" android.permission.POST_NOTIFICATIONS");
        shell("pm clear-permission-flags "+context.getPackageName()+" android.permission.POST_NOTIFICATIONS user-set user-fixed");
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            device.wait(Until.findObject(By.text("Ajustes")),5000).click();
            UiSelector selector=new UiSelector().textMatches("(?iu)Activar notificaciones de predicción");
            new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(selector);
            device.waitForIdle();
            androidx.test.uiautomator.UiObject2 enable=device.wait(Until.findObject(By.text(java.util.regex.Pattern.compile("Activar notificaciones de predicción",java.util.regex.Pattern.CASE_INSENSITIVE|java.util.regex.Pattern.UNICODE_CASE))),5000);
            assertNotNull("Expected notification button in Spanish",enable);
            enable.click();
            androidx.test.uiautomator.UiObject2 deny=device.wait(Until.findObject(By.res("com.android.permissioncontroller","permission_deny_button")),10000);
            if(deny==null){saveEvidence("permission-failure.png");device.dumpWindowHierarchy(new File("/data/local/tmp/airepredict-permission-failure.xml"));}
            assertNotNull("Expected optional notification permission request",deny);
            deny.click();
            assertEquals(android.content.pm.PackageManager.PERMISSION_DENIED,context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS));
            assertTrue(device.wait(Until.hasObject(By.pkg(context.getPackageName())),5000));
        }
    }
    @Test public void widgetCanBindAndRenderInHomeScreenHost() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.os.ParcelFileDescriptor output=InstrumentationRegistry.getInstrumentation().getUiAutomation().executeShellCommand("appwidget grantbind --package pe.airepredict");
        try(android.os.ParcelFileDescriptor.AutoCloseInputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(output)){while(input.read()!=-1){}}
        AppWidgetHost host=new AppWidgetHost(context,71);
        int id=host.allocateAppWidgetId();
        AppWidgetManager manager=AppWidgetManager.getInstance(context);
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            assertTrue(manager.bindAppWidgetIdIfAllowed(id,new ComponentName(context,ForecastWidget.class)));
            scenario.onActivity(activity->{
                host.startListening();
                AppWidgetHostView view=host.createView(activity,id,manager.getAppWidgetInfo(id));
                activity.setContentView(view);
                ForecastWidget.refreshAll(context);
            });
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.textContains("AIREPREDICT")),10000));
            saveEvidence("widget.png");
        } finally {host.deleteAppWidgetId(id);host.stopListening();}
    }
}
