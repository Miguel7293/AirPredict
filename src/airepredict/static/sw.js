const CACHE='airepredict-shell-v0.4.1-location';
const SHELL=['/static/nearby.js','/stations','/static/atlas.css','/static/atlas.js','/static/vendor/leaflet.css','/static/vendor/leaflet.js','/static/region.geojson','/static/departments.geojson','/','/widget','/static/style.css','/static/app.js','/static/pwa.js','/static/widget.js','/static/icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname==='/admin')return;
  event.respondWith(fetch(event.request).then(response=>{
    if(response.ok&&SHELL.includes(url.pathname)){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(url.pathname,copy)));}
    return response;
  }).catch(()=>caches.match(event.request,{ignoreSearch:true}).then(response=>response||new Response('Sin conexión. Vuelve a conectarte para actualizar.',{status:503}))));
});
