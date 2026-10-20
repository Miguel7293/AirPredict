/* Pure geography: coordinates remain in memory on this device. */
(function(root){
  function valid(lat,lon){return Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180;}
  function distance(lat,lon,otherLat,otherLon){
    if(!valid(lat,lon)||!valid(otherLat,otherLon))return Infinity;
    const rad=Math.PI/180,dlat=(otherLat-lat)*rad,dlon=(otherLon-lon)*rad;
    const a=Math.sin(dlat/2)**2+Math.cos(lat*rad)*Math.cos(otherLat*rad)*Math.sin(dlon/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(Math.min(1,a)),Math.sqrt(Math.max(0,1-a)));
  }
  function nearest(sites,position,radius=25){
    return sites.filter(s=>valid(s.latitude,s.longitude)).map(s=>({...s,distance_km:distance(position.latitude,position.longitude,s.latitude,s.longitude)}))
      .filter(s=>s.distance_km+(position.accuracy||0)/1000<=radius).sort((a,b)=>a.distance_km-b.distance_km).slice(0,3);
  }
  function locate(geolocation){
    return new Promise((resolve,reject)=>{
      if(!geolocation){reject(Error('Tu navegador no permite obtener la ubicación. Puedes seleccionar un punto en el mapa.'));return;}
      geolocation.getCurrentPosition(p=>{
        const c=p.coords;if(!valid(c.latitude,c.longitude)||!Number.isFinite(c.accuracy)||c.accuracy<0){reject(Error('No se recibió una ubicación válida. Inténtalo de nuevo.'));return;}
        resolve({latitude:c.latitude,longitude:c.longitude,accuracy:c.accuracy});
      },error=>reject(Error(error.code===1?'Permiso de ubicación rechazado. Puedes seguir usando el mapa manualmente.':error.code===3?'La ubicación tardó demasiado. Revisa que esté activada e inténtalo de nuevo.':'No se pudo obtener tu ubicación. Revisa la ubicación del dispositivo o selecciona un punto manualmente.')),
      {enableHighAccuracy:false,timeout:20000,maximumAge:60000});
    });
  }
  root.AireNearby={distance,nearest,locate};
})(globalThis);
