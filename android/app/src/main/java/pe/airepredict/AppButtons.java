package pe.airepredict;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.widget.Button;
/** Shared touch targets and pressed states for native actions. */
final class AppButtons {
    static int dp(Context context,int value){return Math.round(value*context.getResources().getDisplayMetrics().density);}
    static Button create(Context context,String label,boolean primary){
        Button button=new Button(context);button.setText(label);button.setAllCaps(false);button.setTextSize(14);
        button.setMinWidth(0);button.setMinimumWidth(0);button.setMinHeight(dp(context,48));button.setMinimumHeight(dp(context,48));
        button.setPadding(dp(context,16),dp(context,10),dp(context,16),dp(context,10));
        int ink=Color.rgb(18,63,60);button.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{Color.rgb(111,128,121),primary?Color.WHITE:ink}));
        GradientDrawable shape=new GradientDrawable();shape.setColor(primary?ink:Color.rgb(235,242,228));shape.setCornerRadius(dp(context,13));shape.setStroke(dp(context,1),primary?ink:Color.rgb(207,220,199));
        button.setBackgroundTintList(null);button.setBackground(new RippleDrawable(ColorStateList.valueOf(primary?0x30FFFFFF:0x20123F3C),shape,null));button.setStateListAnimator(null);button.setElevation(0);
        return button;
    }
}
