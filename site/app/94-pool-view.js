/* ================= pool view ================= */
var height=412000,armed=1284;
function tick(){
  height+=8+Math.floor(Math.random()*5);
  if(Math.random()<.3)armed+=Math.random()<.55?1:-1;
  $("r-height").textContent=f0.format(height);
  $("r-armed").textContent=f0.format(armed);
  $("map-block").textContent=t("block {n}",{n:f0.format(height)});
}
var TICKER=null;
function startTick(){ if(!TICKER){ tick(); TICKER=setInterval(tick,1000); } }
function stopTick(){ if(TICKER){ clearInterval(TICKER); TICKER=null; } }
function fillCapBars(){
  requestAnimationFrame(function(){
    Array.prototype.forEach.call(document.querySelectorAll(".cap-row .fill"),function(f){
      f.style.width=f.dataset.w+"%";
    });
  });
}

var TR=[[26.1,41.7],[28.0,41.98],[31.4,41.1],[35.0,42.0],[38.4,40.9],[41.0,41.5],[43.5,40.9],[44.8,39.7],
  [44.0,37.7],[42.5,37.2],[40.0,36.8],[36.6,36.2],[36.2,36.6],[34.0,36.3],[32.0,36.1],[30.5,36.3],
  [29.0,36.6],[27.3,36.7],[27.2,38.4],[26.2,39.5],[26.2,40.1]];
var BOOK=[{code:"IST-KADIKOY",n:4,limit:180000},{code:"IST-BAKIRKOY",n:3,limit:150000},
  {code:"IZM-KONAK",n:3,limit:140000},{code:"ADY-MERKEZ",n:2,limit:120000},{code:"ANK-CANKAYA",n:3,limit:90000}];
var DEG_Y=340/7,DEG_X=DEG_Y*Math.cos(39*Math.PI/180);
function px(lon){return (lon-25.2)*DEG_X+118;}
function py(lat){return (42.6-lat)*DEG_Y+22;}
function buildMap(){
  var out="",i,j;
  for(i=26;i<=45;i+=4)out+='<line class="grat" x1="'+px(i).toFixed(1)+'" y1="16" x2="'+px(i).toFixed(1)+'" y2="372"/>';
  for(i=36;i<=42;i+=2)out+='<line class="grat" x1="0" y1="'+py(i).toFixed(1)+'" x2="1000" y2="'+py(i).toFixed(1)+'"/>';
  var d="";
  for(i=0;i<TR.length;i++)d+=(i?"L":"M")+px(TR[i][0]).toFixed(1)+" "+py(TR[i][1]).toFixed(1);
  out+='<path class="outline" d="'+d+'Z"/>';
  out+='<circle class="ring" id="ring" cx="0" cy="0" r="0"/><circle class="epi" id="epi" cx="0" cy="0" r="0"/>';
  // A label that would land on one already placed steps down instead. Kadıköy
  // and Bakırköy are the same city: six units apart on this map, with names
  // ninety units long, so side by side they were one smear in every language.
  var placed=[];
  BOOK.forEach(function(e,index){
    var p=PLACES[e.code],cx=px(p.lon),cy=py(p.lat);
    for(j=0;j<e.n;j++){
      var a=(j/e.n)*Math.PI*2+index,ox=Math.cos(a)*(e.n>1?9:0),oy=Math.sin(a)*(e.n>1?9:0);
      out+='<circle class="pt" data-code="'+e.code+'" data-limit="'+e.limit+'" cx="'+(cx+ox).toFixed(1)+
           '" cy="'+(cy+oy).toFixed(1)+'" r="5"/>';
    }
    var lx=cx+14,ly=cy+4,guard=0;
    while(guard++<6&&placed.some(function(q){
      return Math.abs(q.x-lx)<Math.max(q.w,p.name.length*5.6)&&Math.abs(q.y-ly)<11;
    }))ly+=13;
    placed.push({x:lx,y:ly,w:p.name.length*5.6});
    out+='<text class="lbl" x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'">'+esc(p.name.toUpperCase())+'</text>';
  });
  $("map").innerHTML=out;
}
buildMap();
function pushEv(target,text,amount){
  var row=document.createElement("div");
  row.className="ev";
  row.innerHTML='<span class="tag paid">'+esc(t("paid"))+'</span><span>'+t("<b>{place}</b> settled",{place:esc(text)})+'</span><span class="amt">'+esc(amount)+'</span>';
  target.insertBefore(row,target.firstChild);
  while(target.children.length>6)target.removeChild(target.lastChild);
}
$("quake-btn").addEventListener("click",function(){
  var e=PLACES["IST-KADIKOY"],cx=px(e.lon),cy=py(e.lat);
  var ring=$("ring"),epi=$("epi");
  [ring,epi].forEach(function(n){n.setAttribute("cx",cx);n.setAttribute("cy",cy);n.style.transition="none";n.setAttribute("r",0);});
  ring.style.opacity=0; epi.style.opacity=.9;
  void ring.getBoundingClientRect();
  ring.style.transition="r .7s cubic-bezier(.22,1,.36,1), opacity .7s";
  epi.style.transition="r 1.1s ease-out, opacity 1.1s ease-out";
  ring.setAttribute("r",62); ring.style.opacity=1;
  epi.setAttribute("r",150); epi.style.opacity=0;
  var hit=Array.prototype.filter.call(document.querySelectorAll(".pt"),function(n){
    return n.dataset.code==="IST-KADIKOY"||n.dataset.code==="IST-BAKIRKOY";});
  var total=0; $("ev-feed").innerHTML="";
  hit.forEach(function(n,i){
    setTimeout(function(){
      n.classList.add("paid"); n.setAttribute("r",7);
      total+=+n.dataset.limit;
      $("ev-total").textContent=money(total);
      pushEv($("ev-feed"),PLACES[n.dataset.code].name,"+"+money(+n.dataset.limit));
    },300+i*85);
  });
  setTimeout(function(){
    $("ev-sub").textContent=t("{n} policies, one reading, block {block}. No claim was filed.",{n:hit.length,block:f0.format(height)});
  },300+hit.length*85+150);
});
$("reset-btn").addEventListener("click",function(){
  buildMap(); $("ev-total").textContent="0"; $("ev-sub").textContent=t("no event yet"); $("ev-feed").innerHTML="";
});


/* ---------------- happening now ----------------
   Two bands on the home page: earthquakes anywhere in the past day, and flight
   delays in force now. Read from the protocol, which fetches each source at
   most once a minute however many people are looking. Shown, not priced. */

var LIVE={timer:null, country:null};

/* Which country the bands show. Guessed, never asked for: the clock's time zone
   says where the reader probably is, and the browser's language settles the
   rest. No location permission is requested for something this small, and the
   guess is only a starting point; the reader can change it, and the choice is
   remembered on this device. An empty value is the whole world. */
var ZONE_COUNTRY={"Europe/Istanbul":"TR","Asia/Istanbul":"TR","Asia/Tokyo":"JP","America/Santiago":"CL",
  "America/Mexico_City":"MX","America/Monterrey":"MX","America/Cancun":"MX","America/Tijuana":"MX",
  "Pacific/Auckland":"NZ","Asia/Taipei":"TW","Asia/Jakarta":"ID","Asia/Makassar":"ID","Asia/Jayapura":"ID",
  "Asia/Manila":"PH","Europe/Athens":"GR","Europe/Rome":"IT","Europe/Berlin":"DE","Europe/Paris":"FR",
  "Europe/Madrid":"ES","Europe/Moscow":"RU","Europe/London":"GB","Europe/Vienna":"AT","Europe/Zurich":"CH",
  "Europe/Amsterdam":"NL","Europe/Brussels":"BE","Europe/Lisbon":"PT","Europe/Warsaw":"PL",
  "America/Argentina/Buenos_Aires":"AR","America/Bogota":"CO","America/Lima":"PE","America/Sao_Paulo":"BR",
  "America/Toronto":"CA","America/Vancouver":"CA","Australia/Sydney":"AU","Australia/Melbourne":"AU",
  "Asia/Seoul":"KR","Asia/Shanghai":"CN","Asia/Kolkata":"IN","Asia/Dubai":"AE","Asia/Tehran":"IR",
  "America/Puerto_Rico":"PR","Pacific/Honolulu":"US","America/Anchorage":"US"};
var LANG_COUNTRY={tr:"TR",ja:"JP",de:"DE",fr:"FR",ru:"RU",it:"IT",el:"GR",es:"ES"};
function guessCountry(){
  try{ var saved=localStorage.getItem("clause.nowCountry"); if(saved!==null)return saved; }catch(e){}
  var zone="";
  try{ zone=Intl.DateTimeFormat().resolvedOptions().timeZone||""; }catch(e){}
  if(ZONE_COUNTRY[zone])return ZONE_COUNTRY[zone];
  if(/^America\/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Detroit|Indiana|Boise|Kentucky)/.test(zone))return "US";
  var langs=(navigator.languages&&navigator.languages.length)?navigator.languages:[navigator.language||""];
  for(var i=0;i<langs.length;i++){
    var m=String(langs[i]).match(/^([a-z]{2,3})(?:-([A-Z]{2}))?/i);
    if(m&&m[2])return m[2].toUpperCase();
    if(m&&LANG_COUNTRY[m[1].toLowerCase()])return LANG_COUNTRY[m[1].toLowerCase()];
  }
  return "";
}
function fillNowCountries(){
  var select=$("now-country"); if(!select)return;
  if(LIVE.country===null)LIVE.country=guessCountry();
  if(select.dataset.filled!==LANG){
    var collator=new Intl.Collator(LOCALES[LANG]||"en-US");
    var rows=COUNTRIES.map(function(row){ return [row[0], regionName(row[0])]; })
      .sort(function(a,b){ return collator.compare(a[1],b[1]); });
    select.innerHTML='<option value="">'+esc(t("The whole world"))+'</option>'+rows.map(function(row){
      return '<option value="'+row[0]+'">'+esc(row[1])+'</option>';
    }).join("");
    select.dataset.filled=LANG;
  }
  select.value=LIVE.country||"";
  if(select.value!==(LIVE.country||""))LIVE.country="";
}
function agoText(seconds){
  var rtf;
  try{ rtf=new Intl.RelativeTimeFormat(LOCALES[LANG]||"en-US",{numeric:"auto",style:"short"}); }
  catch(e){ return ""; }
  var s=Math.max(0,Math.round(seconds));
  if(s<60)return rtf.format(-s,"second");
  if(s<3600)return rtf.format(-Math.round(s/60),"minute");
  return rtf.format(-Math.round(s/3600),"hour");
}
function clockText(at){
  try{ return new Intl.DateTimeFormat(LOCALES[LANG]||"en-US",
         {weekday:"short",hour:"2-digit",minute:"2-digit"}).format(new Date(at*1000)); }
  catch(e){ return ""; }
}
function durationText(minutes){
  if(minutes==null)return "";
  var h=Math.floor(minutes/60), m=minutes%60;
  return h ? t("{h} h {m} min",{h:f0.format(h),m:f0.format(m)}) : t("{m} min",{m:f0.format(m)});
}
function bandFill(id,chips,empty){
  var run=$(id);
  if(!chips.length){ run.style.animation="none"; run.innerHTML='<div class="band-empty">'+esc(empty)+'</div>'; return; }
  run.style.animation="";
  // Twice, so the loop is seamless; the copy is hidden from screen readers.
  run.innerHTML=chips.join("")+'<span class="dup" aria-hidden="true" style="display:contents">'+
    chips.join("")+'</span>';
  // Roughly the same reading speed however many items there are.
  run.style.setProperty("--dur",Math.max(30,chips.length*6)+"s");
}
var SKY={clear:N("clear"),"mostly clear":N("mostly clear"),"partly cloudy":N("partly cloudy"),overcast:N("overcast"),fog:N("fog"),
  drizzle:N("drizzle"),rain:N("rain"),"heavy rain":N("heavy rain"),snow:N("snow"),"heavy snow":N("heavy snow"),showers:N("showers"),
  "violent showers":N("violent showers"),thunderstorm:N("thunderstorm"),"thunderstorm with hail":N("thunderstorm with hail")};
function weatherChip(w){
  var rain=w.rain_mm||0, cls=rain>=50?"m6":rain>=20?"m5":"";
  var temp=w.temp_max!=null?w.temp_max:null, low=w.temp_min!=null?w.temp_min:null;
  var lv=rain>=50||(w.gust_kmh||0)>=90?" lv-crit":rain>=20||(w.gust_kmh||0)>=60?" lv-warn":"";
  if(!lv&&temp!=null&&temp>=35)lv=" lv-hot";
  if(!lv&&low!=null&&low<=0)lv=" lv-cold";
  return '<span class="chip'+lv+'"><b class="mag '+cls+'">'+esc(f1.format(rain))+' mm</b>'+
    '<span>'+esc(w.place)+(w.sky?' · '+esc(t(SKY[w.sky]||w.sky)):'')+'</span>'+
    (w.temp_max!=null?'<time>'+esc(f0.format(Math.round(w.temp_max)))+'°</time>':'')+
    (w.gust_kmh>=60?'<span class="flag">'+esc(t("gusts {kmh} km/h",{kmh:f0.format(Math.round(w.gust_kmh))}))+'</span>':'')+'</span>';
}
function quakeChip(q,now){
  var cls=q.magnitude>=6?"m6":q.magnitude>=5?"m5":"";
  var lv=q.magnitude>=5.5||q.tsunami?" lv-crit":q.magnitude>=4.5?" lv-warn":"";
  return '<a class="chip'+lv+'" href="'+esc(q.url)+'" target="_blank" rel="noopener">'+
    '<b class="mag '+cls+'">M'+esc(q.magnitude.toFixed(1))+'</b>'+
    '<span>'+esc(q.place||t("location not given"))+'</span>'+
    (q.tsunami?'<span class="flag">'+esc(t("tsunami bulletin"))+'</span>':'')+
    '<time>'+esc(agoText(now-q.at))+'</time></a>';
}
var FLIGHT_KINDS={delays:N("delays"),ground_stop:N("ground stop"),ground_delay:N("ground delay programme"),
  arrival_delay:N("arrival delays"),departure_delay:N("departure delays"),closed:N("closed")};
var FLIGHT_CAUSES={weather:N("weather"),volume:N("traffic volume"),runway:N("runway works"),
  equipment:N("equipment or staffing"),other:N("other causes")};
function flightChip(f){
  var parts=[f.count?t("{n} departures late",{n:f.count}):t(FLIGHT_KINDS[f.kind]||f.kind)];
  if(f.kind==="closed"&&f.until_at) parts.push(t("until {time}",{time:clockText(f.until_at)}));
  if(f.average_minutes!=null&&(f.kind==="ground_delay"||f.kind==="delays"))
    parts.push(t("average {time}",{time:durationText(f.average_minutes)}));
  if(f.flights&&f.flights.length) parts.push(f.flights.slice(0,2).map(function(x){return x.flight+(x.to?"→"+x.to:"")+" +"+durationText(x.minutes);}).join(", "));
  if(f.max_minutes!=null) parts.push(t("up to {time}",{time:durationText(f.max_minutes)}));
  if(f.cause&&!f.count) parts.push(t(FLIGHT_CAUSES[f.cause]||"other causes"));
  var worst=Math.max(f.max_minutes||0,f.average_minutes||0);
  var lv=f.kind==="closed"||f.kind==="ground_stop"||worst>=120?" lv-crit":worst>=60||f.kind==="ground_delay"?" lv-warn":"";
  return '<span class="chip'+lv+'"><b>'+esc(f.airport)+'</b>'+
    (f.name?'<span>'+esc(f.name)+'</span>':'')+
    '<span>'+esc(parts.join(" · "))+'</span></span>';
}
