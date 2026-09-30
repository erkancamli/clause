/* ================= the hazard surface, in the browser =================
   The same geometry the protocol prices with, so that when the server is
   unreachable this page computes the model rather than guessing or going blank.
   The data below is exported from clause/perils/geo.py, not re-derived. */

var FAULTS = [{"code":"NAF","name":"North Anatolian Fault","zone":"TR-NAF","b":0.96,"cm":7.3,"ret":250.0,"floor":0.04,"amp":2.5,"decay":40.0,"trace":[[40.62,26.4],[40.68,27.3],[40.72,28.2],[40.78,28.95],[40.74,29.7],[40.72,30.35],[40.78,31.2],[40.82,32.2],[40.72,33.4],[40.6,34.8],[40.45,36.0],[40.3,37.1],[40.05,38.4],[39.88,39.6],[39.78,40.8],[39.7,42.0],[39.66,43.2]],"elev":[[1,4,3.0]],"gap":"The stretch beneath the Sea of Marmara has not ruptured while the segments on either side of it have, so it carries a materially higher rate here than the system's average."},{"code":"EAF","name":"East Anatolian Fault","zone":"TR-EAST","b":0.98,"cm":7.5,"ret":290.0,"floor":0.05,"amp":1.35,"decay":60.0,"trace":[[36.2,36.1],[36.75,36.45],[37.25,36.95],[37.7,37.75],[38.15,38.55],[38.5,39.35],[38.85,40.05],[39.25,40.75],[39.55,41.3]],"elev":[],"gap":""},{"code":"BITLIS","name":"Bitlis and Van thrust belt","zone":"TR-EASTHIGH","b":0.97,"cm":7.1,"ret":520.0,"floor":0.05,"amp":1.15,"decay":55.0,"trace":[[37.9,41.0],[38.2,42.0],[38.5,43.1],[38.9,43.6],[39.4,43.9]],"elev":[],"gap":""},{"code":"AEG-GEDIZ","name":"Gediz graben","zone":"TR-AEGEAN","b":1.02,"cm":6.9,"ret":420.0,"floor":0.12,"amp":2.3,"decay":48.0,"trace":[[38.44,26.9],[38.5,27.6],[38.58,28.3],[38.66,29.1]],"elev":[],"gap":""},{"code":"AEG-MENDERES","name":"Büyük Menderes graben","zone":"TR-AEGEAN","b":1.02,"cm":6.8,"ret":450.0,"floor":0.12,"amp":2.05,"decay":48.0,"trace":[[37.75,27.2],[37.82,27.95],[37.88,28.7],[37.95,29.4]],"elev":[],"gap":""},{"code":"AEG-SIMAV","name":"Simav graben","zone":"TR-AEGEAN","b":1.02,"cm":6.7,"ret":500.0,"floor":0.1,"amp":1.7,"decay":45.0,"trace":[[39.05,28.4],[39.12,29.1],[39.2,29.85]],"elev":[],"gap":""},{"code":"TUZ","name":"Tuz Gölü fault","zone":"TR-CENTRAL","b":0.94,"cm":6.5,"ret":1100.0,"floor":0.02,"amp":0.2,"decay":38.0,"trace":[[38.2,33.55],[38.8,33.4],[39.4,33.25]],"elev":[],"gap":""},{"code":"ECEMIS","name":"Ecemiş fault","zone":"TR-CENTRAL","b":0.94,"cm":6.6,"ret":950.0,"floor":0.02,"amp":0.26,"decay":38.0,"trace":[[37.2,35.05],[37.9,35.25],[38.55,35.5]],"elev":[],"gap":""},{"code":"HELLENIC","name":"Hellenic subduction margin","zone":"TR-AEGEAN","b":1.05,"cm":7.2,"ret":600.0,"floor":0.1,"amp":1.6,"decay":70.0,"trace":[[36.2,27.3],[36.1,28.4],[36.2,29.6],[36.4,30.6]],"elev":[],"gap":""}];
var ZONE_NAMES = {"TR-NAF":"the North Anatolian Fault belt","TR-EAST":"the East Anatolian Fault","TR-AEGEAN":"western Anatolia and the Aegean","TR-CENTRAL":"the Central Anatolian interior","TR-EASTHIGH":"the Bitlis and Van thrust belt"};
var INTERIOR_KM = 90.0, INTERIOR_B = 0.95, INTERIOR_BG = 0.03;
var LOCAL_PLACES = [{"name":"Adana","latitude":37.0,"longitude":35.32,"region":"Akdeniz","kind":"province"},{"name":"Adıyaman","latitude":37.76,"longitude":38.28,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Afyonkarahisar","latitude":38.76,"longitude":30.54,"region":"Ege","kind":"province"},{"name":"Ağrı","latitude":39.72,"longitude":43.05,"region":"Doğu Anadolu","kind":"province"},{"name":"Aksaray","latitude":38.37,"longitude":34.03,"region":"İç Anadolu","kind":"province"},{"name":"Amasya","latitude":40.65,"longitude":35.83,"region":"Karadeniz","kind":"province"},{"name":"Ankara","latitude":39.93,"longitude":32.86,"region":"İç Anadolu","kind":"province"},{"name":"Antalya","latitude":36.9,"longitude":30.69,"region":"Akdeniz","kind":"province"},{"name":"Ardahan","latitude":41.11,"longitude":42.7,"region":"Doğu Anadolu","kind":"province"},{"name":"Artvin","latitude":41.18,"longitude":41.82,"region":"Karadeniz","kind":"province"},{"name":"Aydın","latitude":37.85,"longitude":27.84,"region":"Ege","kind":"province"},{"name":"Balıkesir","latitude":39.65,"longitude":27.89,"region":"Marmara","kind":"province"},{"name":"Bartın","latitude":41.64,"longitude":32.34,"region":"Karadeniz","kind":"province"},{"name":"Batman","latitude":37.88,"longitude":41.13,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Bayburt","latitude":40.26,"longitude":40.23,"region":"Karadeniz","kind":"province"},{"name":"Bilecik","latitude":40.14,"longitude":29.98,"region":"Marmara","kind":"province"},{"name":"Bingöl","latitude":38.89,"longitude":40.5,"region":"Doğu Anadolu","kind":"province"},{"name":"Bitlis","latitude":38.4,"longitude":42.11,"region":"Doğu Anadolu","kind":"province"},{"name":"Bolu","latitude":40.74,"longitude":31.61,"region":"Karadeniz","kind":"province"},{"name":"Burdur","latitude":37.72,"longitude":30.29,"region":"Akdeniz","kind":"province"},{"name":"Bursa","latitude":40.19,"longitude":29.06,"region":"Marmara","kind":"province"},{"name":"Çanakkale","latitude":40.15,"longitude":26.41,"region":"Marmara","kind":"province"},{"name":"Çankırı","latitude":40.6,"longitude":33.62,"region":"İç Anadolu","kind":"province"},{"name":"Çorum","latitude":40.55,"longitude":34.95,"region":"Karadeniz","kind":"province"},{"name":"Denizli","latitude":37.78,"longitude":29.09,"region":"Ege","kind":"province"},{"name":"Diyarbakır","latitude":37.91,"longitude":40.24,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Düzce","latitude":40.84,"longitude":31.16,"region":"Karadeniz","kind":"province"},{"name":"Edirne","latitude":41.68,"longitude":26.56,"region":"Marmara","kind":"province"},{"name":"Elazığ","latitude":38.68,"longitude":39.22,"region":"Doğu Anadolu","kind":"province"},{"name":"Erzincan","latitude":39.75,"longitude":39.49,"region":"Doğu Anadolu","kind":"province"},{"name":"Erzurum","latitude":39.9,"longitude":41.27,"region":"Doğu Anadolu","kind":"province"},{"name":"Eskişehir","latitude":39.78,"longitude":30.52,"region":"İç Anadolu","kind":"province"},{"name":"Gaziantep","latitude":37.07,"longitude":37.38,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Giresun","latitude":40.91,"longitude":38.39,"region":"Karadeniz","kind":"province"},{"name":"Gümüşhane","latitude":40.46,"longitude":39.48,"region":"Karadeniz","kind":"province"},{"name":"Hakkâri","latitude":37.57,"longitude":43.74,"region":"Doğu Anadolu","kind":"province"},{"name":"Hatay","latitude":36.2,"longitude":36.16,"region":"Akdeniz","kind":"province"},{"name":"Iğdır","latitude":39.92,"longitude":44.04,"region":"Doğu Anadolu","kind":"province"},{"name":"Isparta","latitude":37.77,"longitude":30.55,"region":"Akdeniz","kind":"province"},{"name":"İstanbul","latitude":41.01,"longitude":28.98,"region":"Marmara","kind":"province"},{"name":"İzmir","latitude":38.42,"longitude":27.14,"region":"Ege","kind":"province"},{"name":"Kahramanmaraş","latitude":37.58,"longitude":36.93,"region":"Akdeniz","kind":"province"},{"name":"Karabük","latitude":41.2,"longitude":32.63,"region":"Karadeniz","kind":"province"},{"name":"Karaman","latitude":37.18,"longitude":33.22,"region":"İç Anadolu","kind":"province"},{"name":"Kars","latitude":40.6,"longitude":43.1,"region":"Doğu Anadolu","kind":"province"},{"name":"Kastamonu","latitude":41.39,"longitude":33.78,"region":"Karadeniz","kind":"province"},{"name":"Kayseri","latitude":38.73,"longitude":35.49,"region":"İç Anadolu","kind":"province"},{"name":"Kilis","latitude":36.72,"longitude":37.12,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Kırıkkale","latitude":39.85,"longitude":33.52,"region":"İç Anadolu","kind":"province"},{"name":"Kırklareli","latitude":41.74,"longitude":27.22,"region":"Marmara","kind":"province"},{"name":"Kırşehir","latitude":39.15,"longitude":34.16,"region":"İç Anadolu","kind":"province"},{"name":"Kocaeli","latitude":40.77,"longitude":29.92,"region":"Marmara","kind":"province"},{"name":"Konya","latitude":37.87,"longitude":32.49,"region":"İç Anadolu","kind":"province"},{"name":"Kütahya","latitude":39.42,"longitude":29.99,"region":"Ege","kind":"province"},{"name":"Malatya","latitude":38.36,"longitude":38.31,"region":"Doğu Anadolu","kind":"province"},{"name":"Manisa","latitude":38.62,"longitude":27.43,"region":"Ege","kind":"province"},{"name":"Mardin","latitude":37.31,"longitude":40.74,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Mersin","latitude":36.81,"longitude":34.64,"region":"Akdeniz","kind":"province"},{"name":"Muğla","latitude":37.22,"longitude":28.36,"region":"Ege","kind":"province"},{"name":"Muş","latitude":38.73,"longitude":41.49,"region":"Doğu Anadolu","kind":"province"},{"name":"Nevşehir","latitude":38.62,"longitude":34.71,"region":"İç Anadolu","kind":"province"},{"name":"Niğde","latitude":37.97,"longitude":34.68,"region":"İç Anadolu","kind":"province"},{"name":"Ordu","latitude":40.98,"longitude":37.88,"region":"Karadeniz","kind":"province"},{"name":"Osmaniye","latitude":37.07,"longitude":36.25,"region":"Akdeniz","kind":"province"},{"name":"Rize","latitude":41.02,"longitude":40.52,"region":"Karadeniz","kind":"province"},{"name":"Sakarya","latitude":40.78,"longitude":30.4,"region":"Marmara","kind":"province"},{"name":"Samsun","latitude":41.29,"longitude":36.33,"region":"Karadeniz","kind":"province"},{"name":"Siirt","latitude":37.93,"longitude":41.94,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Sinop","latitude":42.03,"longitude":35.15,"region":"Karadeniz","kind":"province"},{"name":"Sivas","latitude":39.75,"longitude":37.02,"region":"İç Anadolu","kind":"province"},{"name":"Şanlıurfa","latitude":37.17,"longitude":38.79,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Şırnak","latitude":37.52,"longitude":42.46,"region":"Güneydoğu Anadolu","kind":"province"},{"name":"Tekirdağ","latitude":40.98,"longitude":27.51,"region":"Marmara","kind":"province"},{"name":"Tokat","latitude":40.31,"longitude":36.55,"region":"Karadeniz","kind":"province"},{"name":"Trabzon","latitude":41.0,"longitude":39.72,"region":"Karadeniz","kind":"province"},{"name":"Tunceli","latitude":39.11,"longitude":39.55,"region":"Doğu Anadolu","kind":"province"},{"name":"Uşak","latitude":38.68,"longitude":29.41,"region":"Ege","kind":"province"},{"name":"Van","latitude":38.49,"longitude":43.38,"region":"Doğu Anadolu","kind":"province"},{"name":"Yalova","latitude":40.66,"longitude":29.28,"region":"Marmara","kind":"province"},{"name":"Yozgat","latitude":39.82,"longitude":34.81,"region":"İç Anadolu","kind":"province"},{"name":"Zonguldak","latitude":41.46,"longitude":31.79,"region":"Karadeniz","kind":"province"},{"name":"İstanbul, Kadıköy","latitude":40.99,"longitude":29.03,"region":"Marmara","kind":"district"},{"name":"İstanbul, Bakırköy","latitude":40.98,"longitude":28.87,"region":"Marmara","kind":"district"},{"name":"İstanbul, Beşiktaş","latitude":41.04,"longitude":29.01,"region":"Marmara","kind":"district"},{"name":"İstanbul, Büyükçekmece","latitude":41.02,"longitude":28.58,"region":"Marmara","kind":"district"},{"name":"İstanbul, Pendik","latitude":40.88,"longitude":29.24,"region":"Marmara","kind":"district"},{"name":"İstanbul, Şile","latitude":41.17,"longitude":29.61,"region":"Marmara","kind":"district"},{"name":"Ankara, Çankaya","latitude":39.9,"longitude":32.85,"region":"İç Anadolu","kind":"district"},{"name":"İzmir, Konak","latitude":38.42,"longitude":27.13,"region":"Ege","kind":"district"},{"name":"İzmir, Bornova","latitude":38.47,"longitude":27.22,"region":"Ege","kind":"district"},{"name":"Adana, Seyhan","latitude":36.99,"longitude":35.3,"region":"Akdeniz","kind":"district"},{"name":"Antalya, Muratpaşa","latitude":36.88,"longitude":30.71,"region":"Akdeniz","kind":"district"},{"name":"Bursa, Osmangazi","latitude":40.18,"longitude":29.06,"region":"Marmara","kind":"district"},{"name":"Kocaeli, Gölcük","latitude":40.72,"longitude":29.82,"region":"Marmara","kind":"district"},{"name":"Kahramanmaraş, Pazarcık","latitude":37.49,"longitude":37.3,"region":"Akdeniz","kind":"district"},{"name":"Hatay, Antakya","latitude":36.2,"longitude":36.16,"region":"Akdeniz","kind":"district"},{"name":"Elazığ, Sivrice","latitude":38.45,"longitude":39.31,"region":"Doğu Anadolu","kind":"district"},{"name":"Muğla, Bodrum","latitude":37.03,"longitude":27.43,"region":"Ege","kind":"district"},{"name":"Muğla, Fethiye","latitude":36.62,"longitude":29.12,"region":"Ege","kind":"district"},{"name":"Denizli, Sarayköy","latitude":37.92,"longitude":28.92,"region":"Ege","kind":"district"},{"name":"Konya, Çumra","latitude":37.57,"longitude":32.77,"region":"İç Anadolu","kind":"district"},{"name":"Şanlıurfa, Harran","latitude":36.86,"longitude":39.03,"region":"Güneydoğu Anadolu","kind":"district"},{"name":"Edirne, Keşan","latitude":40.85,"longitude":26.63,"region":"Marmara","kind":"district"}];

var R_EARTH = 6371.0;
function kmBetween(a, b){
  var mid = (a[0] + b[0]) * 0.5 * Math.PI / 180;
  var x = (b[1] - a[1]) * Math.PI / 180 * Math.cos(mid);
  var y = (b[0] - a[0]) * Math.PI / 180;
  return R_EARTH * Math.hypot(x, y);
}
function kmToSegment(point, start, end){
  function project(p){
    return [
      (p[1] - point[1]) * Math.PI / 180 * Math.cos(point[0] * Math.PI / 180) * R_EARTH,
      (p[0] - point[0]) * Math.PI / 180 * R_EARTH,
    ];
  }
  var a = project(start), b = project(end);
  var dx = b[0] - a[0], dy = b[1] - a[1];
  if (dx === 0 && dy === 0) return Math.hypot(a[0], a[1]);
  var t = Math.max(0, Math.min(1, (-a[0] * dx + -a[1] * dy) / (dx * dx + dy * dy)));
  return Math.hypot(a[0] + t * dx, a[1] + t * dy);
}
function faultDistance(system, point){
  var best = Infinity;
  for (var i = 0; i < system.trace.length - 1; i++){
    best = Math.min(best, kmToSegment(point, system.trace[i], system.trace[i + 1]));
  }
  return best;
}
function segmentFactor(system, index){
  for (var i = 0; i < system.elev.length; i++){
    if (system.elev[i][0] <= index && index < system.elev[i][1]) return system.elev[i][2];
  }
  return 1;
}
function weightedLengthInside(system, centre, radius){
  var total = 0;
  for (var i = 0; i < system.trace.length - 1; i++){
    var a = system.trace[i], b = system.trace[i + 1];
    var length = kmBetween(a, b), inside = 0, steps = 24;
    for (var j = 0; j < steps; j++){
      var f = (j + 0.5) / steps;
      if (kmBetween([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], centre) <= radius) inside++;
    }
    total += length * inside / steps * segmentFactor(system, i);
  }
  return total;
}

var _siteCache = {};
function siteAt(latitude, longitude){
  var key = latitude.toFixed(4) + ":" + longitude.toFixed(4);
  if (_siteCache[key]) return _siteCache[key];

  var point = [latitude, longitude], total = 0, best = null, bestWeight = -1, bestDistance = Infinity;
  for (var i = 0; i < FAULTS.length; i++){
    var system = FAULTS[i];
    var distance = faultDistance(system, point);
    var weight = system.amp * Math.exp(-distance / system.decay);
    total += weight;
    if (weight > bestWeight){ bestWeight = weight; best = system; bestDistance = distance; }
  }

  var site = bestDistance > INTERIOR_KM
    ? {zone:"TR-INTERIOR", zoneName:"no dominant nearby fault", b:INTERIOR_B,
       background:INTERIOR_BG + total, nearest:null, distance:bestDistance}
    : {zone:best.zone, zoneName:ZONE_NAMES[best.zone] || best.zone, b:best.b,
       background:best.floor + total, nearest:best, distance:bestDistance};
  _siteCache[key] = site;
  return site;
}

function characteristicRate(latitude, longitude, radius){
  var centre = [latitude, longitude], total = 0, dominant = null, best = 0;
  for (var i = 0; i < FAULTS.length; i++){
    var length = weightedLengthInside(FAULTS[i], centre, radius);
    if (length <= 0) continue;
    var rate = (length / 100) / FAULTS[i].ret;
    total += rate;
    if (rate > best){ best = rate; dominant = FAULTS[i]; }
  }
  return {total:total, dominant:dominant};
}


function gridShare(grid, m){
  // Truncated Gutenberg and Richter, exactly as clause/hazard/model.py has it.
  if (m >= grid.max_magnitude) return 0;
  if (m <= grid.reference_magnitude) return 1;
  var top = Math.pow(10, -grid.b_value * (grid.max_magnitude - grid.reference_magnitude));
  var here = Math.pow(10, -grid.b_value * (m - grid.reference_magnitude));
  return Math.max(0, (here - top) / (1 - top));
}
function gridRate(radius){
  var row = flow.grid && flow.grid.radii[String(radius)];
  return row ? row.rate_reference : 0;
}
/* A car: the place's own extreme rainfall levels, from the protocol. */
function carCurve(){
  var v=flow.vehicle; if(!v) return {shape:"step",pts:[[60,.25],[75,.6],[90,1]]};
  return {shape:"step",pts:v.levels.map(function(l){ return [l.mm,l.share]; })};
}
function carExc(days){
  var v=flow.vehicle; if(!v) return function(){ return 0; };
  var years=days/365.25, g=v.gumbel;
  return function(mm){
    var p=1-Math.exp(-Math.exp(-(mm-g.mu)/g.beta));
    return 1-Math.pow(1-p,years);
  };
}
function loadVehicle(){
  flow.vehicle=null; flow.vehicleError=null;
  var at=coordinates(); if(!at||flow.peril!=="car"){ return; }
  if(!link.live){ flow.vehicleError=t("Car cover needs the protocol, which is not reachable right now."); renderCarInfo(); setNextLabel(); return; }
  var seq=++flow.hazardSeq;
  renderCarInfo();
  api("/api/vehicle?latitude="+at.latitude+"&longitude="+at.longitude,{timeout:10000}).then(function(reply){
    if(seq!==flow.hazardSeq)return;
    flow.vehicle=reply; renderCarInfo(); updatePriceBar(); setNextLabel();
  },function(error){
    if(seq!==flow.hazardSeq)return;
    var d=error&&error.payload&&error.payload.detail;
    flow.vehicleError=typeof d==="string"?ts(d):t("The protocol did not answer.");
    renderCarInfo(); updatePriceBar(); setNextLabel();
  });
}
function renderCarInfo(){
  var box=$("s2-extra");
  if(flow.peril!=="car"||!flow.subject){ return; }
  box.hidden=false;
  if(flow.vehicleError){ box.innerHTML='<div class="verdict no"><p>'+esc(flow.vehicleError)+'</p></div>'; return; }
  if(!flow.vehicle){ box.innerHTML='<p class="hint">'+esc(t("Reading the rainfall record for this place…"))+'</p>'; return; }
  var v=flow.vehicle;
  box.innerHTML='<div class="label">'+esc(t("When it pays, for this place"))+'</div>'+
    '<div class="tbl-wrap" style="margin-top:8px"><table class="tbl" style="min-width:0"><tbody>'+
    v.levels.map(function(l){
      return '<tr><td>'+esc(t("{mm} mm in one day",{mm:f1.format(l.mm)}))+'</td><td class="num">'+esc(t("about once in {n} years",{n:f0.format(l.years)}))+'</td><td class="num">'+pct(l.share,0)+'</td></tr>';
    }).join("")+'</tbody></table></div>'+
    '<p class="fine" style="margin-top:8px">'+esc(t("Read from NASA POWER at {station}, {km} km away, and checked against the national service and ERA5. Accidents, theft and hail are not covered.",{station:v.subject.station,km:f0.format(v.subject.distance_km)}))+'</p>';
}
function carReady(){ return flow.peril!=="car" || !flow.subject || (!!flow.vehicle && !flow.vehicleError); }
/* A home against storm: the place's own extreme wind levels, from the protocol. */
function stormCurve(){
  var w=flow.storm; if(!w) return {shape:"step",pts:[[70,.25],[85,.6],[100,1]]};
  return {shape:"step",pts:w.levels.map(function(l){ return [l.kmh,l.share]; })};
}
function stormExc(days){
  var w=flow.storm; if(!w) return function(){ return 0; };
  var years=days/365.25, g=w.gumbel;
  return function(kmh){
    var p=1-Math.exp(-Math.exp(-(kmh-g.mu)/g.beta));
    return 1-Math.pow(1-p,years);
  };
}
function loadStorm(){
  flow.storm=null; flow.stormError=null;
  var at=coordinates(); if(!at||flow.peril!=="storm"){ return; }
  if(!link.live){ flow.stormError=t("Storm cover needs the protocol, which is not reachable right now."); renderStormInfo(); setNextLabel(); return; }
  var seq=++flow.hazardSeq;
  renderStormInfo();
  api("/api/storm?latitude="+at.latitude+"&longitude="+at.longitude,{timeout:10000}).then(function(reply){
    if(seq!==flow.hazardSeq)return;
    flow.storm=reply; renderStormInfo(); updatePriceBar(); setNextLabel();
  },function(error){
    if(seq!==flow.hazardSeq)return;
    var d=error&&error.payload&&error.payload.detail;
    flow.stormError=typeof d==="string"?ts(d):t("The protocol did not answer.");
    renderStormInfo(); updatePriceBar(); setNextLabel();
  });
}
function renderStormInfo(){
  var box=$("s2-extra");
  if(flow.peril!=="storm"||!flow.subject){ return; }
  box.hidden=false;
  if(flow.stormError){ box.innerHTML='<div class="verdict no"><p>'+esc(flow.stormError)+'</p></div>'; return; }
  if(!flow.storm){ box.innerHTML='<p class="hint">'+esc(t("Reading the wind record for this place…"))+'</p>'; return; }
  var w=flow.storm;
  box.innerHTML='<div class="label">'+esc(t("When it pays, for this place"))+'</div>'+
    '<div class="tbl-wrap" style="margin-top:8px"><table class="tbl" style="min-width:0"><tbody>'+
    w.levels.map(function(l){
      return '<tr><td>'+esc(t("{kmh} km/h in one day",{kmh:f0.format(Math.round(l.kmh))}))+'</td><td class="num">'+esc(t("about once in {n} years",{n:f0.format(l.years)}))+'</td><td class="num">'+pct(l.share,0)+'</td></tr>';
    }).join("")+'</tbody></table></div>'+
    '<p class="fine" style="margin-top:8px">'+esc(t("Read from NASA POWER at {station}, {km} km away, and checked against the national service and ERA5. The figure is the day's strongest hour over the area, lower than a gust at a station. Hail, lightning, snow and flood are not covered.",{station:w.subject.station,km:f0.format(w.subject.distance_km)}))+'</p>';
}
function stormReady(){ return flow.peril!=="storm" || !flow.subject || (!!flow.storm && !flow.stormError); }
function shakingIndex(){ return flow.peril==="quake" && flow.index==="shaking"; }
/* Shaking at the address comes from the protocol, which turns its rate model
   into intensity at the point; the page interpolates between the levels it
   published, on a log scale, which is how such curves fall. */
function shakingExc(days){
  var sk=flow.shaking; if(!sk) return function(){ return 0; };
  var years=days/365.25, L=sk.levels, P=sk.annual_probability;
  function annualRate(x){
    var rates=P.map(function(p){ return -Math.log(Math.max(1e-12,1-p)); });
    if(x<=L[0]) return rates[0];
    for(var i=1;i<L.length;i++){
      if(x<=L[i]){
        var f=(x-L[i-1])/(L[i]-L[i-1]);
        return Math.exp(Math.log(Math.max(rates[i-1],1e-12))*(1-f)+Math.log(Math.max(rates[i],1e-12))*f);
      }
    }
    return rates[rates.length-1];
  }
  return function(x){ return 1-Math.exp(-annualRate(x)*years); };
}
function quakeExcAt(latitude, longitude, radius, days){
  if (shakingIndex()) return shakingExc(days);
  var years = days / 365.25;
  if (flow.grid){
    var base = gridRate(radius), grid = flow.grid;
    return function(m){ return 1 - Math.exp(-base * gridShare(grid, m) * years); };
  }
  var site = siteAt(latitude, longitude);
  var characteristic = characteristicRate(latitude, longitude, radius);
  return function(m){
    var background = 0;
    if (m < BG_MAX){
      var anchor = Math.max(m, ANCHOR);
      var top = Math.pow(10, -site.b * (BG_MAX - ANCHOR));
      var here = Math.pow(10, -site.b * (anchor - ANCHOR));
      background = site.background * ((here - top) / (1 - top)) *
                   (radius * radius) / (REF_R * REF_R);
    }
    var fault = 0;
    if (characteristic.dominant){
      var centre = characteristic.dominant.cm;
      var low = centre - CHAR_HALF, high = centre + CHAR_HALF, share;
      if (m <= low) share = 1; else if (m >= high) share = 0;
      else share = (high - m) / (high - low);
      fault = characteristic.total * share;
    }
    return 1 - Math.exp(-(background + fault) * years);
  };
}

