const CACHE='airepredict-shell-v0.3.0';
const SHELL=['/','/widget','/static/style.css','/static/app.js','/static/pwa.js','/static/widget.js','/static/icon.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname==='/admin')return;
  event.respondWith(fetch(event.request).then(response=>{
    if(response.ok&&SHELL.includes(url.pathname))event.waitUntil(caches.open(CACHE).then(cache=>cache.put(url.pathname,response.clone())));
    return response;
  }).catch(()=>caches.match(event.request,{ignoreSearch:true}).then(response=>response||new Response('Offline. Reconnect to refresh.',{status:503}))));
});
