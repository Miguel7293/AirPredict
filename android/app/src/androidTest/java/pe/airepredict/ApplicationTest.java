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
    @Test public void homeScreenWidgetIsRegistered() {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertTrue(AppWidgetManager.getInstance(context).getInstalledProviders().stream().anyMatch(provider->provider.provider.getClassName().equals(ForecastWidget.class.getName())));
    }
    @Test public void appLaunchesWithOptionalPermissions() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        ForecastData.preferences(context).edit().clear().commit();
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            assertNotNull(device.wait(Until.findObject(By.textContains("Campo de Marte")),10000));
            File directory=context.getExternalFilesDir(null);
            assertTrue(device.takeScreenshot(new File(directory,"application.png")));
        }
    }
    @Test public void decliningNotificationsKeepsAppAvailable() throws Exception {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            UiDevice device=UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
            UiSelector selector=new UiSelector().textMatches("(?i)Enable forecast notifications");
            new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(selector);
            device.findObject(selector).click();
            androidx.test.uiautomator.UiObject2 deny=device.wait(Until.findObject(By.res("com.android.permissioncontroller","permission_deny_button")),5000);
            assertNotNull("Expected optional notification permission request",deny);
            deny.click();
            new UiScrollable(new UiSelector().scrollable(true)).scrollToBeginning(5);
            assertEquals(android.content.pm.PackageManager.PERMISSION_DENIED,context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS));
            assertNotNull(device.wait(Until.findObject(By.textContains("Notifications declined")),5000));
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
            assertTrue(device.takeScreenshot(new File(context.getExternalFilesDir(null),"widget.png")));
        } finally {host.deleteAppWidgetId(id);host.stopListening();}
    }
}
