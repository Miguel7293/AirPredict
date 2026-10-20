let installPrompt;
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;document.getElementById('install-app').hidden=false;});
document.getElementById('install-app')?.addEventListener('click',async()=>{
  if(installPrompt){await installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;document.getElementById('install-app').hidden=true;}
});
window.addEventListener('offline',()=>{const notice=document.getElementById('notice');if(notice)notice.textContent='Offline. Reconnect to load verified observations. Previously displayed values may be outdated.';});
fetch('/api/model').then(r=>r.ok?r.json():Promise.reject()).then(data=>{
  document.getElementById('model-version').textContent=data.version;
  const initial=data.initial_experiment?.combinado?.test;
  document.getElementById('model-metrics').textContent=initial?`Initial historical test: MAE ${initial.mae.toFixed(2)} µg/m³ · RMSE ${initial.rmse.toFixed(2)} · R² ${initial.r2.toFixed(3)}. Active releases are evaluated separately.`:'Historical experiment: MAE 2.02 µg/m³, RMSE 2.88, R² 0.617. Active releases are evaluated separately.';
}).catch(()=>{document.getElementById('model-version').textContent='Unavailable offline';});
