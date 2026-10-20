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
const historical = {mode:'historical', is_current_forecast:false,
  last_observed_pm25:19.49, predicted_pm25:19.61,
  last_observation_utc:'2026-10-15T22:00:00-05:00', target_time_utc:'2026-10-15T23:00:00-05:00',
  history:[{timestamp:'2026-10-15T22:00:00-05:00',pm25:19.49}]};
const context = vm.createContext({
  document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);}, createElementNS(){return element();}},
  navigator:{onLine:true},
  localStorage:{setItem(key,value){storage.set(key,value);},getItem(key){return storage.get(key)??null;}},
  fetch:async path=>{
    if(!context.navigator.onLine)throw Error('Offline');
    if(path==='/api/demo')return {ok:true,json:async()=>historical};
    if(path==='/api/forecast')return {ok:false,status:409,json:async()=>({detail:'Inputs are delayed'})};
    if(path==='/api/observations')return {ok:true,json:async()=>({history:[{timestamp:'2026-10-19T08:00:00-05:00',pm25:24.9}]})};
    throw Error('Unexpected endpoint');
  }
});
vm.runInContext(fs.readFileSync('src/airepredict/static/app.js','utf8'),context);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(elements.get('forecast').textContent,'19.61');
assert.match(elements.get('notice').textContent,/does not describe current/);
assert(storage.has('airepredict-recorded'));

await elements.get('live').events.click();
assert.equal(elements.get('last').textContent,'24.90');
assert.equal(elements.get('forecast').textContent,'—');
assert.equal(elements.get('live').attrs['aria-pressed'],'true');
assert.match(elements.get('notice').textContent,/No current forecast/);
assert.equal(elements.get('chart').children.length,1);

context.navigator.onLine=false;
await elements.get('demo').events.click();
assert.equal(elements.get('forecast').textContent,'19.61');
assert.match(elements.get('mode-label').textContent,/Offline.*historical/);
assert.match(elements.get('notice').textContent,/does not describe current/);
console.log('3 client flows passed: historical, delayed observations, explicitly labelled offline record.');
