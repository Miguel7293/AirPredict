const $ = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat('en-GB',{timeZone:'America/Lima',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
const hourFormat = new Intl.DateTimeFormat('en-GB',{timeZone:'America/Lima',hour:'2-digit',minute:'2-digit'});
function renderChart(data){
  const rows=[...(data.history||[])].sort((a,b)=>new Date(a.timestamp)-new Date(b.timestamp));
  if(!rows.length){$('chart').textContent='No observations available.';return;}
  const hasForecast=Number.isFinite(data.predicted_pm25);
  const last=new Date(data.target_time_utc||rows.at(-1).timestamp).getTime(),first=Math.min(new Date(rows[0].timestamp).getTime(),last-3600000);
  const W=Math.min(1080,Math.max(300,$('chart').clientWidth)),H=W<600?220:260,L=40,R=24,T=18,B=37;
  const max=Math.max(...rows.map(r=>r.pm25),(hasForecast?data.predicted_pm25:0),1)*1.2;
  const x=t=>L+(new Date(t).getTime()-first)/(last-first)*(W-L-R),y=v=>T+(1-v/max)*(H-T-B);
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',hasForecast?'Measured PM2.5 concentrations and a forecast for the next hour':'Ingested PM2.5 observations; no current forecast available');
  const el=(name,attrs,text)=>{const e=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.appendChild(e);return e;};
  for(let i=0;i<=4;i++){const v=max*i/4;el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),stroke:'#e6ebe3'});el('text',{x:L-9,y:y(v)+4,'text-anchor':'end',fill:'#73847c','font-size':12},v.toFixed(0));}
  let path='';rows.forEach((r,i)=>{const gap=i&&new Date(r.timestamp)-new Date(rows[i-1].timestamp)>3600000;path+=`${!i||gap?'M':'L'}${x(r.timestamp)},${y(r.pm25)} `;});
  el('path',{d:path,fill:'none',stroke:'#167567','stroke-width':2.6,'stroke-linecap':'round','stroke-linejoin':'round'});
  rows.forEach(r=>el('circle',{cx:x(r.timestamp),cy:y(r.pm25),r:2.5,fill:'#167567'}));
  if(hasForecast){const previous=rows.at(-1);el('line',{x1:x(previous.timestamp),y1:y(previous.pm25),x2:x(data.target_time_utc),y2:y(data.predicted_pm25),stroke:'#799435','stroke-width':2.5,'stroke-dasharray':'5 5'});
  el('circle',{cx:x(data.target_time_utc),cy:y(data.predicted_pm25),r:6,fill:'#799435',stroke:'white','stroke-width':2});}
  for(let i=0;i<6;i++){const t=new Date(first+Math.round((last-first)/3600000*i/5)*3600000);el('text',{x:x(t),y:H-10,'text-anchor':i===0?'start':i===5?'end':'middle',fill:'#73847c','font-size':12},hourFormat.format(t));}
  $('chart').replaceChildren(svg);
}
async function load(mode){
  $('notice').classList.remove('error');$('notice').textContent='Loading observations…';
  $('demo').disabled=$('live').disabled=true;
  for(const name of ['demo','live']){$(name).classList.toggle('active',name===mode);$(name).setAttribute('aria-pressed',String(name===mode));}
  try{
    const response=await fetch(mode==='live'?'/api/forecast':'/api/demo');const data=await response.json();if(!response.ok)throw new Error(mode==='live'&&response.status===409?'A fresh consecutive measurement window is unavailable for a current forecast.':typeof data.detail==='string'?data.detail:'The forecast could not be loaded.');
    $('last').textContent=data.last_observed_pm25.toFixed(2);$('forecast').textContent=data.predicted_pm25.toFixed(2);
    $('last-time').textContent=dateFormat.format(new Date(data.last_observation_utc));$('forecast-time').textContent=dateFormat.format(new Date(data.target_time_utc));
    const historical=data.mode!=='live';$('mode-label').textContent=historical?'Historical demonstration':'Current · experimental';
    $('notice').textContent=historical?`Recorded observations from ${dateFormat.format(new Date(data.last_observation_utc))}. This forecast does not describe current conditions.`:'Forecast based on recently ingested hourly observations. The model remains experimental.';
    $('freshness-note').textContent=historical?'Recorded forecasts let you explore the model using historical observations. They do not describe current air conditions.':'This forecast is available only when three consecutive hourly measurements exist and its target hour is still in the future.';
    renderChart(data);if(mode==='demo'){try{localStorage.setItem('airepredict-recorded',JSON.stringify(data));}catch(ignored){}}
  }catch(error){$('notice').classList.add('error');$('notice').textContent=error.message;$('last').textContent=$('forecast').textContent='—';$('last-time').textContent=$('forecast-time').textContent='Unavailable';$('chart').textContent='No observations loaded for this mode.';$('mode-label').textContent=mode==='live'?'Current forecast unavailable':'Historical forecast unavailable';
    if(mode==='demo'&&!navigator.onLine){
      try{const cached=JSON.parse(localStorage.getItem('airepredict-recorded'));if(cached&&Number.isFinite(cached.predicted_pm25)&&Number.isFinite(cached.last_observed_pm25)){$('last').textContent=cached.last_observed_pm25.toFixed(2);$('forecast').textContent=cached.predicted_pm25.toFixed(2);$('last-time').textContent=dateFormat.format(new Date(cached.last_observation_utc));$('forecast-time').textContent=dateFormat.format(new Date(cached.target_time_utc));$('mode-label').textContent='Offline · saved historical record';$('notice').textContent='Offline. Showing a previously saved historical forecast. This does not describe current conditions. Reconnect to refresh.';renderChart(cached);}}catch(ignored){}
    }
    if(mode==='live'){
      try{const response=await fetch('/api/observations',{cache:'no-store'});if(response.ok){const measured=await response.json();if(measured.history.length){const latest=measured.history.at(-1);$('last').textContent=latest.pm25.toFixed(2);$('last-time').textContent=dateFormat.format(new Date(latest.timestamp));$('notice').textContent=`Last ingested observation: ${dateFormat.format(new Date(latest.timestamp))}. No current forecast is available; the inputs may be delayed or incomplete.`;$('freshness-note').textContent='These are actual ingested observations. Their date and missing hours determine whether a next-hour forecast can be issued.';renderChart(measured);}}}catch(ignored){}
    }
  }
  finally{$('demo').disabled=$('live').disabled=false;}
}
$('demo').addEventListener('click',()=>load('demo'));$('live').addEventListener('click',()=>load('live'));load('demo');
