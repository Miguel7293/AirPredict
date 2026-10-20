let installPrompt;
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;document.getElementById('install-app').hidden=false;});
document.getElementById('install-app')?.addEventListener('click',async()=>{
  if(installPrompt){await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;document.getElementById('install-app').hidden=true;}
});
window.addEventListener('offline',()=>{const notice=document.getElementById('notice');if(notice)notice.textContent='Sin conexión. Vuelve a conectarte para cargar observaciones verificadas. Los valores mostrados pueden estar desactualizados.';});
fetch('/api/model').then(r=>r.ok?r.json():Promise.reject()).then(data=>{
  document.getElementById('model-version').textContent=data.version;
  const initial=data.initial_experiment?.combinado?.test;
  document.getElementById('model-metrics').textContent=initial?`Prueba histórica inicial: MAE ${initial.mae.toFixed(2)} µg/m³ · RMSE ${initial.rmse.toFixed(2)} · R² ${initial.r2.toFixed(3)}. Las versiones activas se evalúan por separado.`:'Experimento histórico: MAE 2.02 µg/m³, RMSE 2.88, R² 0.617. Las versiones activas se evalúan por separado.';
}).catch(()=>{document.getElementById('model-version').textContent='No disponible sin conexión';});
