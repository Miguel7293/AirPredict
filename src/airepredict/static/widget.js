async function refreshWidget(){
  const status=document.getElementById('widget-mode');
  document.getElementById('widget-value').textContent='—';
  document.getElementById('widget-date').textContent='No se ha cargado una predicción actual.';
  document.getElementById('widget-observed').textContent='';
  try{
    const response=await fetch('/api/forecast',{cache:'no-store'});
    if(!response.ok)throw Error('No hay una predicción reciente disponible. Abre la aplicación completa para consultar la demostración histórica identificada como tal.');
    const data=await response.json();
    if(!data.is_current_forecast||Date.parse(data.target_time_utc)<=Date.now())throw Error('La predicción ha caducado.');
    status.textContent='Actual · experimental';
    document.getElementById('widget-value').textContent=data.predicted_pm25.toFixed(2);
    document.getElementById('widget-date').textContent='Predicción para '+new Date(data.target_time_utc).toLocaleString('es-PE',{timeZone:'America/Lima'})+' (Lima)';
    document.getElementById('widget-observed').textContent='Última medición: '+data.last_observed_pm25.toFixed(2)+' µg/m³';
  }catch(error){status.textContent=error.message;}
}
document.getElementById('widget-refresh').addEventListener('click',refreshWidget);refreshWidget();setInterval(refreshWidget,60000);
