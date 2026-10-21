// Execute the real client against controlled HTTP responses and a minimal DOM.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const elements = new Map();
function element() {
  return {textContent:'', clientWidth:480, attrs:{}, events:{}, children:[],
    classList:{add(){},remove(){},toggle(){}},
    setAttribute(name,value){this.attrs[name]=value;},
    appendChild(child){this.children.push(child);},
    replaceChildren(...children){this.children=children;},
    addEventListener(name,callback){this.events[name]=callback;}};
}
const storage = new Map();
let latestAvailable=true;
const historical = {mode:'historical', is_current_forecast:false,
  last_observed_pm25:19.49, predicted_pm25:19.61,
  last_observation_utc:'2026-10-15T22:00:00-05:00', target_time_utc:'2026-10-15T23:00:00-05:00',
  history:[{timestamp:'2026-10-15T22:00:00-05:00',pm25:19.49}]};
const context = vm.createContext({
  URLSearchParams,
  document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);}, createElementNS(){return element();}},
  navigator:{onLine:true},
  localStorage:{setItem(key,value){storage.set(key,value);},getItem(key){return storage.get(key)??null;}},
  fetch:async path=>{
    if(!context.navigator.onLine)throw Error('Offline');
    if(path==='/api/stations/2415/forecast?mode=historical')return {ok:true,json:async()=>historical};
    if(path==='/api/stations/2415/forecast?mode=latest')return latestAvailable?{ok:true,json:async()=>({...historical,mode:'latest'})}:{ok:false,status:409,json:async()=>({detail:'Missing consecutive hours'})};
    if(path==='/api/stations/2415/observations')return {ok:true,json:async()=>({history:[{timestamp:'2026-10-19T08:00:00-05:00',pm25:24.9}]})};
    throw Error('Unexpected endpoint');
  }
});
vm.runInContext(fs.readFileSync('src/airepredict/static/app.js','utf8'),context);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(elements.get('forecast').textContent,'19.61');
assert.match(elements.get('notice').textContent,/Esa hora ya pasó/);
assert.match(elements.get('mode-label').textContent,/hora objetivo pasada/);
await elements.get('demo').events.click();
assert(storage.has('airepredict-recorded-2415'));
latestAvailable=false;

await elements.get('live').events.click();
assert.equal(elements.get('last').textContent,'24.90');
assert.equal(elements.get('forecast').textContent,'—');
assert.equal(elements.get('live').attrs['aria-pressed'],'true');
assert.match(elements.get('notice').textContent,/No hay una predicción actual/);
assert.equal(elements.get('chart').children.length,1);

context.navigator.onLine=false;
await elements.get('demo').events.click();
assert.equal(elements.get('forecast').textContent,'19.61');
assert.match(elements.get('mode-label').textContent,/Sin conexión.*histórico/);
assert.match(elements.get('notice').textContent,/[Nn]o describe las condiciones actuales/);
console.log('4 client flows passed: visible delayed estimate, historical, missing window, explicitly labelled offline record.');
