package pe.airepredict;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.*;
import android.widget.*;

/** A dedicated laboratory. Never selected as a measured station or widget source. */
public class PunoActivity extends Activity {
    private WebView web;
    @android.annotation.SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state){super.onCreate(state);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setBackgroundColor(Color.rgb(246,247,242));
        box.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(12,insets.getSystemWindowInsetTop(),12,insets.getSystemWindowInsetBottom());return insets;});setContentView(box);
        TextView title=new TextView(this);title.setText("Puno · modelo experimental");title.setTextSize(22);title.setPadding(16,18,16,12);box.addView(title);
        TextView warning=new TextView(this);warning.setText("Datos modelados por CAMS. Sin mediciones locales ni alertas de salud.");warning.setTextSize(15);warning.setTextColor(Color.rgb(101,69,7));warning.setBackgroundColor(Color.rgb(255,244,217));warning.setPadding(16,12,16,12);box.addView(warning);
        LinearLayout actions=new LinearLayout(this);Button back=new Button(this);back.setText("Volver");back.setAllCaps(false);back.setOnClickListener(v->finish());actions.addView(back);Button refresh=new Button(this);refresh.setText("Actualizar");refresh.setAllCaps(false);actions.addView(refresh);box.addView(actions);
        TextView status=new TextView(this);status.setText("Conectando con el laboratorio…");status.setTextSize(14);status.setPadding(16,8,16,8);box.addView(status);
        web=new WebView(this);web.setContentDescription("Laboratorio de Puno: modelo, curva y entrenamiento");web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){Uri uri=request.getUrl(),origin=Uri.parse(ForecastData.baseUrl(PunoActivity.this));if("https".equals(uri.getScheme())&&origin.getHost().equals(uri.getHost())&&origin.getPort()==uri.getPort())return false;if("https".equals(uri.getScheme()))startActivity(new Intent(Intent.ACTION_VIEW,uri));return true;}
            @Override public void onPageFinished(WebView view,String url){status.setText("Laboratorio conectado · consulta la vigencia y el origen de los datos.");}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())status.setText("No se pudo conectar. Revisa la dirección en Ajustes y vuelve a actualizar.");}
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){if(request.isForMainFrame())status.setText("Laboratorio no disponible. Actualiza dentro de un momento.");}
        });box.addView(web,new LinearLayout.LayoutParams(-1,0,1));refresh.setOnClickListener(v->web.reload());web.loadUrl(ForecastData.baseUrl(this)+"/puno?embedded=1");
    }
    @Override protected void onDestroy(){if(web!=null)web.destroy();super.onDestroy();}
}
