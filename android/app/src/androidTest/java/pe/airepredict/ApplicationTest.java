package pe.airepredict;

import android.appwidget.AppWidgetManager;
import android.content.Context;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.Until;
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
}
