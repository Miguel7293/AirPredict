import vm from 'node:vm';import fs from 'node:fs';import assert from 'node:assert/strict';
const nodes=new Map(),requests=[];let geoRequests=0;
function node(){return {value:'',textContent:'',hidden:false,clientWidth:600,children:[],classList:{add(){},toggle(){},contains(){return false;}},replaceChildren(...items){this.children=items;},appendChild(item){this.children.push(item);},setAttribute(){},addEventListener(name,fn){this[name]=fn;}};}
function layer(){return {addTo(){return this;},remove(){},getElement(){return node();},bindPopup(){return this;},on(){return this;},bindTooltip(){return this;}};}
const map={setView(){return this;},fitBounds(){return this;},createPane(){},getPane(){return {style:{}};},attributionControl:{addAttribution(){}}};
const site={id:'near',code:'P-1',district:'Distrito de ejemplo',region:'Lima',latitude:-12.071,longitude:-77.041,daily_count:310,trained:true,first_date:'2022-01-01',last_date:'2022-12-31'};
const catalog={sites:[site,{...site,id:'far',latitude:-5,longitude:-80}],years:[2022],general_model:{counts:{scanned_rows:100,accepted_daily_observations:10},training_sites:2,test:{mae:2,rmse:3,r2:.5},persistence:{mae:3}}};
const context=vm.createContext({URLSearchParams,location:{search:''},document:{body:node(),getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node,createElementNS:node},navigator:{geolocation:{getCurrentPosition(ok){geoRequests++;ok({coords:{latitude:-12.07,longitude:-77.04,accuracy:500}});}}},L:{map:()=>map,circleMarker:layer,circle:layer,geoJSON:layer,polyline:layer,latLngBounds:()=>({pad(){return this;}}),control:{scale:layer}},fetch:async(path,options)=>{requests.push([path,options]);let data;if(path==='/api/atlas')data=catalog;else if(path==='/api/stations')data={stations:[{id:2415,name:'Jesús María',latitude:-12.071,longitude:-77.041,fresh:false,latest:{pm25:24.9,timestamp:'2026-10-19T08:00:00-05:00'}}]};else if(path==='/api/general/predict')data={predicted_pm25:16.4,target_date:'2022-12-21',observed_date:'2022-12-20',outside_training_period:false,note:'Simulación con tus datos, sin verificar.'};else if(path.startsWith('/api/atlas/sites/'))data={history:[{date:'2022-12-31',pm25:12}],prediction:{observed_date:'2022-12-31',observed:12,value:13,target_date:'2023-01-01',trained_site:true}};else if(path.startsWith('/static/'))data={features:[]};else throw Error(path);return {ok:true,json:async()=>data};}});
for(const file of ['nearby.js','atlas.js'])vm.runInContext(fs.readFileSync('src/airepredict/static/'+file,'utf8'),context);
await new Promise(setImmediate);assert.equal(geoRequests,0);assert.equal(nodes.get('raw-count').textContent,'100');
const initialRequests=requests.length;
await nodes.get('use-location').onclick();assert.equal(geoRequests,1);await new Promise(setImmediate);assert(requests.length>initialRequests,'Load the selected public reference, without sending device coordinates');assert.equal(nodes.get('nearby-list').children.length,2);assert.match(nodes.get('nearby-list').children[0].children[0].textContent,/Referencia más cercana.*km aprox/);
assert.match(nodes.get('nearby-reading').children[0].textContent,/estación más cercana.*Jesús María/);
assert.match(nodes.get('nearby-reading').children[1].textContent,/24.9.*2026.*no describe necesariamente/);
assert.match(nodes.get('nearby-list').children[1].textContent,/12.*2022-12-31.*no una medición actual/);
assert.equal(nodes.get('scenario-fields').disabled,false);
assert.match(nodes.get('scenario-point').textContent,/Distrito de ejemplo/);
nodes.get('scenario-date').value='2022-12-20';nodes.get('scenario-pm25').value='15';nodes.get('scenario-previous').value='14';
await nodes.get('scenario-form').submit({preventDefault(){}});
const scenarioRequest=requests.find(([path])=>path==='/api/general/predict');assert(scenarioRequest);
assert.deepEqual(JSON.parse(scenarioRequest[1].body),{site_id:'near',observed_date:'2022-12-20',pm25:15,previous_pm25:14});
assert.equal(nodes.get('estimate').textContent,'16.4');assert.match(nodes.get('prediction-kicker').textContent,/SIMULACIÓN CON TUS DATOS/);
for(const [path,options] of requests){assert(!path.includes('-12.07')&&!path.includes('-77.04'));assert(!options?.body?.includes('latitude'));assert(!options?.body?.includes('longitude'));}
const html=fs.readFileSync('src/airepredict/static/dashboard.html','utf8');
assert(html.indexOf('id="simular"')<html.indexOf('id="historico"'));assert(!html.includes('<details id="scenario-box"'));assert(html.indexOf('id="scenario-form"')<html.indexOf('id="history-chart"'));

nodes.get('clear-location').onclick();assert.equal(nodes.get('nearby-list').children.length,0);assert(nodes.get('clear-location').hidden);
context.navigator.geolocation.getCurrentPosition=(ok,error)=>error({code:1});await nodes.get('use-location').onclick();assert.match(nodes.get('location-status').textContent,/rechazado/);
context.navigator.geolocation.getCurrentPosition=ok=>ok({coords:{latitude:40,longitude:0,accuracy:500}});await nodes.get('use-location').onclick();assert.match(nodes.get('nearby-list').textContent,/No hay puntos/);
console.log('Atlas flows passed: visible daily simulation before history, scenario inputs/result, nearest station measurement/date, automatic historical reference selection, optional location, denial, clear, no coverage and no coordinates transmitted.');
