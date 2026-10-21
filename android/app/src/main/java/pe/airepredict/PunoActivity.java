package pe.airepredict;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.*;
import android.widget.*;
/** Compact native toolbar; all source details scroll with the page. */
public class PunoActivity extends Activity {
    private WebView web;private boolean pageFailed;
    @android.annotation.SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state){super.onCreate(state);
        int paper=Color.rgb(246,247,242),ink=Color.rgb(18,63,60);
        getWindow().setStatusBarColor(paper);getWindow().setNavigationBarColor(paper);getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setBackgroundColor(paper);
        box.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(0,insets.getSystemWindowInsetTop(),0,insets.getSystemWindowInsetBottom());return insets;});setContentView(box);
        LinearLayout toolbar=new LinearLayout(this);toolbar.setGravity(android.view.Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(12),dp(8),dp(12),dp(8));
        Button back=AppButtons.create(this,"‹",false);back.setTextSize(28);back.setContentDescription("Volver");back.setPadding(0,0,0,0);back.setOnClickListener(v->finish());toolbar.addView(back,new LinearLayout.LayoutParams(dp(48),dp(48)));
        LinearLayout name=new LinearLayout(this);name.setOrientation(LinearLayout.VERTICAL);name.setPadding(dp(12),0,dp(6),0);TextView title=new TextView(this);title.setText("Puno");title.setTextSize(22);title.setTextColor(ink);name.addView(title);TextView subtitle=new TextView(this);subtitle.setText("Calidad del aire");subtitle.setTextSize(12);subtitle.setTextColor(Color.rgb(100,121,117));name.addView(subtitle);toolbar.addView(name,new LinearLayout.LayoutParams(0,-2,1));
        Button refresh=AppButtons.create(this,"Actualizar",true);refresh.setTextSize(13);toolbar.addView(refresh,new LinearLayout.LayoutParams(dp(110),dp(48)));box.addView(toolbar);
        ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setIndeterminate(true);progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(ink));box.addView(progress,new LinearLayout.LayoutParams(-1,dp(3)));
        TextView status=new TextView(this);status.setTextSize(14);status.setTextColor(Color.rgb(132,46,30));status.setPadding(dp(16),dp(8),dp(16),dp(8));status.setVisibility(View.GONE);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);box.addView(status);
        web=new WebView(this);web.setBackgroundColor(paper);web.setContentDescription("Puno: calidad del aire, estimaciones y datos del modelo");web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);web.getSettings().setAllowFileAccess(false);web.getSettings().setAllowContentAccess(false);web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){Uri uri=request.getUrl(),origin=Uri.parse(ForecastData.baseUrl(PunoActivity.this));if("https".equals(uri.getScheme())&&origin.getHost().equals(uri.getHost())&&origin.getPort()==uri.getPort())return false;if("https".equals(uri.getScheme()))startActivity(new Intent(Intent.ACTION_VIEW,uri));return true;}
            @Override public void onPageStarted(WebView view,String url,Bitmap icon){pageFailed=false;status.setVisibility(View.GONE);progress.setVisibility(View.VISIBLE);refresh.setEnabled(false);}
            @Override public void onPageFinished(WebView view,String url){progress.setVisibility(View.GONE);refresh.setEnabled(true);if(!pageFailed)status.setVisibility(View.GONE);}
            private void failed(String message){pageFailed=true;status.setText(message);status.setVisibility(View.VISIBLE);progress.setVisibility(View.GONE);refresh.setEnabled(true);}
            @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())failed("No se pudo conectar. Revisa la dirección en Ajustes y vuelve a actualizar.");}
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){if(request.isForMainFrame())failed("El servicio no está disponible. Intenta actualizar dentro de un momento.");}
        });box.addView(web,new LinearLayout.LayoutParams(-1,0,1));refresh.setOnClickListener(v->web.reload());web.loadUrl(ForecastData.baseUrl(this)+"/puno?embedded=1");
    }
    private int dp(int value){return AppButtons.dp(this,value);}
    @Override protected void onDestroy(){if(web!=null)web.destroy();super.onDestroy();}
}
