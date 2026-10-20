async function refreshWidget(){
  const status=document.getElementById('widget-mode');
  document.getElementById('widget-value').textContent='—';
  document.getElementById('widget-date').textContent='No current forecast loaded.';
  document.getElementById('widget-observed').textContent='';
  try{
    const response=await fetch('/api/forecast',{cache:'no-store'});
    if(!response.ok)throw Error('No fresh forecast is available. Open the full application for the labelled historical demonstration.');
    const data=await response.json();
    if(!data.is_current_forecast||Date.parse(data.target_time_utc)<=Date.now())throw Error('The forecast has expired.');
    status.textContent='Current · experimental';
    document.getElementById('widget-value').textContent=data.predicted_pm25.toFixed(2);
    document.getElementById('widget-date').textContent='Forecast for '+new Date(data.target_time_utc).toLocaleString('en-GB',{timeZone:'America/Lima'})+' (Lima)';
    document.getElementById('widget-observed').textContent='Last measured: '+data.last_observed_pm25.toFixed(2)+' µg/m³';
  }catch(error){status.textContent=error.message;}
}
document.getElementById('widget-refresh').addEventListener('click',refreshWidget);refreshWidget();setInterval(refreshWidget,60000);
