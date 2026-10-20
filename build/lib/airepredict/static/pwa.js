let installPrompt;
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;document.getElementById('install-app').hidden=false;});
document.getElementById('install-app')?.addEventListener('click',async()=>{
  if(installPrompt){await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;document.getElementById('install-app').hidden=true;}
});
window.addEventListener('offline',()=>{const notice=document.getElementById('notice');if(notice)notice.textContent='Sin conexión. Vuelve a conectarte para cargar observaciones verificadas. Los valores mostrados pueden estar desactualizados.';});
async function stationMetrics(){
  try{const response=await fetch('/api/stations',{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();const selected=Number(document.getElementById('station-select').value);const station=data.stations.find(s=>s.id===selected);document.getElementById('model-version').textContent=station.model_version||'Modelo inicial experimental';const metric=station.metrics?.combinado?.test;document.getElementById('model-metrics').textContent=metric?`Prueba histórica de ${station.name}: MAE ${metric.mae.toFixed(2)} µg/m³ · RMSE ${metric.rmse.toFixed(2)} · R² ${metric.r2.toFixed(3)}. Cada modelo tiene una evaluación independiente.`:'No hay métricas publicadas para este punto.';}catch{document.getElementById('model-version').textContent='No disponible sin conexión';}
}
window.addEventListener('stationchange',stationMetrics);stationMetrics();
