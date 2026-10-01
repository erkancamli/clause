/* ================= the live readings =================
   These were the second half of 94-pool-view.js, which is a file about the
   pool: the map of where the book is, the block height, the capital bars. The
   bands on the home page are none of those things, and the home page's own
   part, 96-digest.js, the next file, reads eight names out of them: LIVE,
   agoText, bandFill, fillNowCountries, flightChip, quakeChip, weatherChip and
   the tables behind them.

   So the home page depended on a file named for a screen it has nothing to do
   with, and anyone reading the parts to work out what the buyer's page needs
   would have concluded it needs the pool view. It does not. Measured when the
   question was asked properly: 7,601 B of the 12,340 B in that file were
   these, and 4,739 B were the pool.

   Nothing moved but the seam. The declarations, their order and their text
   are as they were, and they still initialise before 96-digest.js reads them,
   which is what they did when the two halves shared a file. */

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
