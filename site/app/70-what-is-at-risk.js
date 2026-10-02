/* ---------------- what is actually at risk ----------------
   The step that makes this insurance. Cover is capped by what the buyer says is
   at risk, and refused outright if the thing insured is not inside the area the
   index measures. Both are checked here, and again by the protocol. */

/* What may be declared at risk, held to what the protocol will accept.

   This was four times the largest cover and nothing else, which for a flight
   reached 20,000 by arithmetic rather than by agreement -- and for anything
   carried in from another peril, no ceiling at all. The protocol publishes its
   own bounds for exactly this ("so the page can show a buyer the ceiling as
   they type and the protocol can hold them to it"), so they are what bounds
   the slider. A reader cannot be offered a figure that will be refused after
   they have read the contract. */
var VALUE_BOUNDS={flight:"trip", car:"vehicle"};
function valueRange(){
  var limits=PERILS[flow.peril].limits, low=limits[0], high=limits[1]*4;
  var said=VALUATION&&VALUATION[VALUE_BOUNDS[flow.peril]];
  if(said&&said.length===2&&said[0]<said[1]){
    low=Math.max(low,said[0]);
    high=Math.min(high,said[1]);
  }
  return [low, Math.max(high, low*1.01)];
}
function valueFromSlider(v){
  var range=valueRange(),f=(v-1)/99;
  var raw=range[0]*Math.pow(range[1]/range[0],f);
  var step=raw>200000?25000:raw>50000?10000:raw>5000?1000:100;
  return Math.max(range[0],Math.round(raw/step)*step);
}
function sliderFromValue(value){
  var range=valueRange();
  var v=Math.round(1+Math.log(value/range[0])/Math.log(range[1]/range[0])*99);
  return Math.min(100,Math.max(1,v));
}

function areaSentence(){
  if(flow.peril==="quake")
    return t("the circle of {km} km around {place}",{km:flow.radius,place:subjectLabel()});
  if(flow.peril==="drought"){
    var station=stationFor();
    return t("the ground the station at {station} reports for, {km} km from {place}",
      {station:station.name,km:f0.format(Math.round(flow.stationKm)),place:subjectLabel()});
  }
  if(flow.peril==="car")
    return t("the place where the car is kept, read at {station}",{station:flow.vehicle?flow.vehicle.subject.station:subjectLabel()});
  if(flow.peril==="storm")
    return t("the place where the home stands, read at {station}",{station:flow.storm?flow.storm.subject.station:subjectLabel()});
  return t("the flight itself");
}

function renderInterest(){
  var interest=flow.interest;
  if(!interest.what&&flow.peril==="flight")interest.what=t("one flight, and what missing it costs");
  if(!interest.what&&flow.peril==="car")interest.what=t("my car");
  // A home is named after its place; the buyer can change the words. And
  // the place the buyer chose is where the home stands, so it is inside the
  // area by construction: nothing to confirm that the address did not.
  // Named after the place, and renamed when the place moves. Only the words
  // the page put there: anything the buyer wrote is theirs and is left alone.
  if(!interest.whatTouched&&flow.place&&(flow.peril==="quake"||flow.peril==="storm"||flow.peril==="drought"))
    interest.what="";
  if(!interest.what&&flow.peril==="quake"&&flow.place)interest.what=t("A flat in {place}",{place:subjectLabel()});
  if(!interest.what&&flow.peril==="storm"&&flow.place)interest.what=t("A house in {place}",{place:subjectLabel()});
  // Drought was the one peril with no name offered, so its buyer met an empty
  // required box where the other four met a filled one. It is named the way
  // they are: after what it is and where, from the crop already selected and
  // the place already chosen, and the words stay the buyer's to change.
  if(!interest.what&&flow.peril==="drought"&&flow.place)
    interest.what=t("A field of {crop} in {place}",
                    {crop:cropInSentence(sizeState().crop),place:subjectLabel()});
  // A flight belongs on that list and was left off it. The area a flight
  // cover measures is the flight, which is what areaSentence() says in so many
  // words -- "the flight itself" -- so the buyer was being asked to confirm
  // that their flight is inside their flight. Measured: it was the only thing
  // blocking Continue on that step, with every other field already answered.
  //
  // Drought is not on the list and should not be. The field can be kilometres
  // from the station that settles it, the sentence names that distance, and
  // basis risk lives in it. That one is a buyer's to confirm.
  if(!interest.insideTouched&&flow.peril!=="drought")interest.inside=true;
  /* The box is written after the name is worked out, and not before it.

     It was written first, so for a home, a field and a car the field showed
     its placeholder while flow.interest.what already held "A flat in
     Istanbul, Kadikoy". The button said Continue, the summary row said the
     name, and /api/contract and /api/applications were both sent it: the
     buyer signed a declaration of what is at risk that the box they were
     looking at never showed. It healed itself on the next render, which is
     one compliance round trip away, up to 18.9 seconds on a slow line. */
  $("what").value=interest.what;
  $("what").placeholder = flow.peril==="car" ? t("my car") : flow.peril==="quake" ? t("A flat in {place}",{place:subjectLabel()})
    : flow.peril==="storm" ? t("A house in {place}",{place:subjectLabel()})
    : flow.peril==="drought" ? t("40 hectares of wheat") : t("one flight, and what missing it costs");
  // Start from the cover, because that is the common case, but stop adjusting
  // it the moment the buyer sets a figure: a value at risk the page chose for
  // you is not a declaration, and the cap on cover would mean nothing.
  // A flight is worth what missing it costs, which is the cover, not the
  // price of a flat. The first version started every peril at 150,000.
  var trip=flow.peril==="flight"||flow.peril==="car";
  $("value-label").textContent=flow.peril==="car"?t("What the car is worth"):t("What the trip cost");
  $("value-field").hidden=!trip;
  if(trip){
    if(!interest.touched) interest.value=Math.max(interest.value||0, flow.limit);
    var bounds=valueRange();
    interest.value=Math.min(bounds[1],Math.max(bounds[0],interest.value||bounds[0]));
    if(interest.declared)
      interest.declared=Math.min(bounds[1],Math.max(bounds[0],interest.declared));
    $("value").value=sliderFromValue(interest.declared||interest.value);
    $("value-val").textContent=f0.format(interest.declared||interest.value)+" USDC";
    $("size-box").innerHTML=flow.peril==="car"?carYearHtml():"";
    if(flow.peril==="car")bindCarYear();
  } else {
    renderSize();
  }
  var needsAddr=flow.peril==="quake"||flow.peril==="car"||flow.peril==="storm";
  $("addr-box").hidden=!needsAddr;
  if(needsAddr){
    $("addr-title").textContent=flow.peril==="car"?t("Where the car is kept"):t("The address of the home");
    $("addr-note").textContent=flow.peril==="car"
      ? t("Seen only by the company that issues the policy, which checks that the car is yours (registration). The protocol keeps a fingerprint of it, not the address.")
      : t("Seen only by the company that issues the policy, which checks that the home is yours or that you live in it (title deed or lease). The protocol keeps a fingerprint of it, not the address.");
    var a=interest.address||{};
    ["street","number","flat","postcode","city"].forEach(function(k){ var el=$("addr-"+k); if(el&&!el.dataset.bound){ el.dataset.bound="1";
      el.addEventListener("input",function(e){ (interest.address=interest.address||{})[k]=e.target.value;
        // Once they have written any of it themselves, nothing offers over it again.
        interest.addressTouched=true; var offered=$("addr-offered"); if(offered)offered.hidden=true;
        lookUpTheAddress(); setNextLabel(); }); }
      if(el&&el.value!==(a[k]||""))el.value=a[k]||""; });
    if(!a.city&&flow.place){ var parts=String(flow.place).split(", "); if(parts.length>=2){ a.city=parts[parts.length-2]; (interest.address=a); $("addr-city").value=a.city; } }
    lookUpTheAddress();
    // Said out loud when it was filled in for them, because an answer somebody
    // did not write is one they have not checked.
    var offered=$("addr-offered");
    if(offered){ offered.hidden=!(interest.addressOffered&&!interest.addressTouched);
      offered.textContent=t("Filled in from the place you chose. Correct it if it is not right."); }
    $("docs-note").textContent=flow.peril==="car"
      ? t("The company will want to see the vehicle registration. You send it after buying, from the screen that follows or from My cover: nothing about the price depends on it, and the company decides afterwards either way.")
      : t("The company will want to see the paper that shows it is yours. You send it after buying, from the screen that follows or from My cover: nothing about the price depends on it, and the company decides afterwards either way.");
  }
  $("inside-sub").textContent=t("It is inside {area}.",{area:areaSentence()});
  $("inside").setAttribute("aria-pressed",String(!!interest.inside));
  fillCountries($("country"), interest.country);

  // What this country's answer actually is, read from the registry rather than
  // from a list on this page. Until the protocol has answered, the page says it
  // does not know, which is different from saying no.
  //
  // The country that answers is where the risk is. For a place, the place, and
  // the buyer's own country is asked only for the checks that are about them.
  var code=riskCountry();
  $("country-why").textContent = tiedToPlace()
    ? ((flow.peril==="quake"||flow.peril==="storm"||flow.peril==="car")
        ? t("Asked for the checks that are about you. The policy itself is issued where the property is, in {country}, whoever owns it and wherever they live.",{country:countryName(code)})
        : t("Asked for the checks that are about you. The policy itself is issued where the land is, in {country}, whoever owns it and wherever they live.",{country:countryName(code)}))
    : t("A flight follows you, so the company issuing this must be licensed where you live.");
  var cover=coverFor(code), note=NOTES[code]||null;
  var box=$("rule-note");
  box.hidden=false;
  var refusal=link.live?licensing(code):null;
  var open=!!cover&&!refusal, name=countryName(code);
  if(!link.live){
    box.className="verdict";
    box.innerHTML='<div class="vrow"><span class="pill">'+esc(t("Not connected"))+'</span><span>'+
      esc(name)+'</span></div><p>'+esc(t("This page cannot reach the protocol, so it cannot tell you which companies are licensed where you are."))+'</p>';
  } else if(!coverageKnown()){
    // The answer has not arrived. It used to read "Nobody registered" while
    // it was on its way, in red, which is a different sentence altogether.
    box.className="verdict";
    box.innerHTML='<div class="vrow"><span class="pill">'+esc(t("Still checking"))+'</span><span>'+
      esc(name)+'</span></div><p>'+esc(t("Still checking which company is licensed to write this in {country}.",{country:name}))+'</p>';
  } else if(open){
    box.className="verdict ok";
    box.innerHTML='<div class="vrow"><span class="pill ok">'+
      esc(cover.retail?t("Available"):t("Professional only"))+'</span><span>'+esc(name)+
      ' · '+esc(listText(cover.authorities.map(ts)))+'</span></div>'+
      '<p>'+esc(t(cover.carriers.length>1
        ? "{carriers} are licensed to issue this in {country}, paid in {cash}."
        : "{carriers} is licensed to issue this in {country}, paid in {cash}.",
        {carriers:listText(cover.carriers.map(ts)),country:name,
         cash:cashName(code, cover.settlement.indexOf("stablecoin")>=0?"stablecoin":cover.settlement[0])}))+'</p>';
  } else if(cover||(COVERAGE&&COVERAGE.__waiting&&COVERAGE.__waiting[code])){
    // Somebody is licensed, and something else is missing. Say what, because
    // "nobody registered" would be false and would send an insurer who has
    // already registered off to register again.
    box.className="verdict no";
    box.innerHTML='<div class="vrow"><span class="pill no">'+esc(t("Not yet"))+'</span><span>'+
      esc(name)+'</span></div><p>'+esc(refusal||"")+'</p>';
  } else {
    box.className="verdict no";
    box.innerHTML='<div class="vrow"><span class="pill no">'+esc(t("Nobody registered"))+'</span><span>'+
      esc(name)+'</span></div><p>'+esc(t("No licensed company has registered to write cover in {country}. Insurance without a licence is a criminal offence in most of the world, so the protocol refuses rather than quietly selling into it. If you know an insurer there, the company side of this protocol is open.",{country:name}))+'</p>'+
      '<p><a href="#/insurers">'+esc(t("How a company registers"))+'</a></p>';
  }
  if(note)box.innerHTML+='<p class="fine">'+esc(t(note.note))+'</p>';

  setNextLabel();
}

/* ---------------- how big it is, and so what it is worth ----------------
   The value at risk is worked out from what the buyer describes, the same way
   the protocol works it out: a home from its floor area, a field from its area
   and crop. The figures come from the protocol; this copy is only for when it
   cannot be reached. Cover is then capped at the value, so a hundred square
   metres of garden cannot buy a farm's cover. */
var VALUATION={
  rebuild_per_m2:{TR:{flat:517,house:517,shop:833},IT:{flat:2153,house:2153,shop:2153},
    GR:{flat:1027,house:1027,shop:1027},JP:{flat:2482,house:1653,shop:2482},
    TW:{flat:1097,house:763,shop:1097},NZ:{flat:2274,house:2127,shop:2274},
    MX:{flat:425,house:425,shop:425},CL:{flat:1146,house:1146,shop:1146},
    PH:{flat:480,house:480,shop:480},ID:{flat:348,house:348,shop:348}},
  revenue_per_ha:{
    TR:{wheat:1015,barley:662,maize:2662,sunflower:1481,cotton:3152,chickpea:1204,lentil:1316,sugar_beet:4127},
    IT:{wheat:1224,maize:2481},
    GR:{wheat:881,barley:580,maize:2744,sunflower:1091,cotton:1969,lentil:3195},
    MX:{wheat:1972,barley:914,maize:1150,cotton:2981,chickpea:1934,lentil:727},
    CL:{wheat:1450,maize:2577,barley:1814,sugar_beet:6365},
    ID:{maize:2214}, PH:{maize:985},
    JP:{wheat:1276,barley:2354,sugar_beet:7147},
    NZ:{wheat:3091,barley:2075,maize:3639}},
  area_m2:[15,3000], area_ha:[0.01,5000], built:[1900,new Date().getFullYear()], model_year:[1990,new Date().getFullYear()],
  // The protocol's own bounds for a declared figure, held here too so the
  // slider is right before /api/valuation has answered rather than after.
  trip:[50,20000], vehicle:[1000,250000]};
var VALUATION_READ=false;
function loadValuation(){
  if(VALUATION_READ||!link.live)return;
  VALUATION_READ=true;
  api("/api/valuation",{timeout:8000}).then(function(v){ VALUATION=v; if(flow.step===RISK_STEP)renderInterest(); },
    function(){ VALUATION_READ=false; });
}
var BUILDING_WORDS={flat:N("A flat"),house:N("A house"),shop:N("A shop or office")};
/* A crop word written for a dropdown, put back into a sentence.

   The list capitalises them the way a list does, Wheat and Sugar beet, and
   dropped straight into "A field of {crop} in {place}" that capital is wrong
   in the middle of a sentence. It is wrong in English, Turkish, Spanish,
   French and Russian, right in German where every noun carries one, and
   absent in Japanese, so the languages that lowercase are named rather than
   assumed. The i of Turkish is why toLocaleLowerCase takes the language. */
var LOWERCASES_NOUNS={en:true,tr:true,es:true,fr:true,ru:true};
function cropInSentence(key){
  var word=t(CROP_WORDS[key]||key);
  if(!LOWERCASES_NOUNS[LANG])return word;
  return word.charAt(0).toLocaleLowerCase(LOCALES[LANG]||"en-US")+word.slice(1);
}
var CROP_WORDS={wheat:N("Wheat"),barley:N("Barley"),maize:N("Maize"),sunflower:N("Sunflower"),
  cotton:N("Cotton"),chickpea:N("Chickpea"),lentil:N("Lentil"),sugar_beet:N("Sugar beet")};
/* Which crops can be covered here. A crop is on the list when the country
   publishes a producer price for it, because the cover is a season's income
   and there is no season's income without a price. Türkiye grows a lot of
   cotton and is missing from its own list for exactly that reason. */
function cropsHere(){
  var table=(VALUATION.revenue_per_ha||{})[riskCountry()]||{}, out=[];
  for(var k in CROP_WORDS){ if(table[k]>0) out.push(k); }
  return out;
}
var AREA_UNITS={decare:0.1,hectare:1,m2:0.0001};
var UNIT_WORDS={decare:N("decares"),hectare:N("hectares"),m2:N("square metres")};

function sizeState(){
  if(!flow.size||flow.size.peril!==flow.peril){
    flow.size = (flow.peril==="quake"||flow.peril==="storm")
      ? {peril:flow.peril, kind:"home", building:"flat", area:"", built:"", valid:false}
      : {peril:"drought", kind:"field", crop:"wheat", area:"", unit:"decare", valid:false};
  }
  return flow.size;
}
/* Age, as the protocol values it: an older home is worth less to rebuild
   like for like and is damaged by less shaking; an older car is worth less. */
/* The year the protocol is counting ages from, not the year this file was
   written in. Both of these had 2026 in them: on 1 January 2027 a building of
   2006 would have been priced at hazard 1.0 here and 1.25 on the server, and
   the cover ceiling on a worked example came out 779.78 apart. /api/valuation
   says which year it is; the browser's own is the answer until it has, and is
   right every day but the ones where a device's clock is wrong. */
function protocolYear(){
  return (VALUATION&&VALUATION.this_year)||new Date().getUTCFullYear();
}
function homeAge(built, country){
  var v=VALUATION.home_age||{ceiling_per_year:.01,ceiling_floor:.55,hazard:{}};
  var age=Math.max(0,protocolYear()-built), ceiling=Math.max(v.ceiling_floor,1-v.ceiling_per_year*age);
  var table=(v.hazard||{})[country]||(v.hazard||{})["*"]||[[0,1]], hazard=1;
  for(var i=0;i<table.length;i++){ if(built>=table[i][0]){ hazard=table[i][1]; break; } }
  return {ceiling:ceiling, hazard:hazard, shift:Math.min(.75,Math.max(0,(hazard-1)*.75))};
}
function carCap(year){
  var v=VALUATION.vehicle_age||{per_year:.85,floor:.2};
  return (VALUATION.vehicle_new_cap||250000)*
    Math.max(v.floor,Math.pow(v.per_year,Math.max(0,protocolYear()-year)));
}
/* Whole USDC, rounded down, once and here. Everything downstream carries this
   same number: the figure shown on the "at risk" line, the cover ceiling, the
   top preset and the contract. Rounding twice is how one quote came to read
   49,228 on one screen and 49,227 on the next. */
function sizeValue(){
  var z=sizeState(), v=VALUATION, area=parseFloat(String(z.area).replace(",", "."));
  z.valid=false; z.basis=""; z.problem="";
  if(!(area>0)){ z.problem=t("Give the area."); return 0; }
  if(z.kind==="home"){
    var table=v.rebuild_per_m2[riskCountry()];
    if(!table){ z.problem=t("There is no rebuild cost schedule for this country yet."); return 0; }
    if(area<v.area_m2[0]||area>v.area_m2[1]){ z.problem=t("The floor area must be between {min} and {max} m².",{min:f0.format(v.area_m2[0]),max:f0.format(v.area_m2[1])}); return 0; }
    var rate=table[z.building];
    var built=parseInt(z.built,10);
    if(z.built&&(!(built>=v.built[0]&&built<=v.built[1]))){ z.problem=t("The year built must be between {min} and {max}.",{min:v.built[0],max:v.built[1]}); return 0; }
    if(!z.built){ z.problem=t("Give the year it was built."); return 0; }
    var f=homeAge(built, riskCountry());
    z.valid=true; z.area_m2=area; z.builtYear=built; z.hazard=f.hazard;
    z.basis=t("{area} m² × {rate} per m² to rebuild, × {share} for a building of {year}",{area:f0.format(area),rate:f0.format(rate),share:pct(f.ceiling,0),year:built});
    return Math.floor(area*rate*f.ceiling);
  }
  var ha=area*AREA_UNITS[z.unit];
  if(ha<v.area_ha[0]||ha>v.area_ha[1]){ z.problem=t("The area must be between {min} and {max} hectares.",{min:f2.format(v.area_ha[0]),max:f0.format(v.area_ha[1])}); return 0; }
  var here=(v.revenue_per_ha||{})[riskCountry()]||{}, per=here[z.crop];
  if(!(per>0)){ z.problem=t("There is no published price for this crop here yet."); return 0; }
  z.valid=true; z.area_ha=Math.round(ha*10000)/10000;
  z.basis=t("{area} hectares × {rate} expected revenue per hectare",{area:f2.format(z.area_ha),rate:f0.format(per)});
  return Math.floor(z.area_ha*per);
}
/* Where the per square metre or per hectare figure came from. Asked once by
   someone who wanted to know why a flat in Istanbul was capped where it was,
   and a fair question: the answer is a ministry schedule with a date on it,
   so the page says which one rather than leaving a number to be taken on
   trust. The source names are the publishers' own and are not translated. */
function whereTheRateIsFrom(z){
  var country=riskCountry(), said=[], from;
  if(z.kind==="home"){
    from=((VALUATION.rebuild_basis||{})[country]||{})[z.building];
    if(!from||!from.figure)return "";
    said.push(f0.format(from.figure.amount)+" "+from.figure.currency+"/m², "+from.figure.source);
    /* What the figure leaves out, which is the answer to the question a buyer
       actually asks: my flat is worth a hundred times what you are offering.
       It is, and what it is worth is mostly the land under it. The schedule
       says so in its own words and the page was keeping them to itself. */
    if(from.figure.note) said.push(from.figure.note);
    if(from.stands_in) said.push(from.stands_in);
    if(from.carried_forward) said.push(from.carried_forward);
    if(from.region&&from.region.name) said.push(from.region.name+" ×"+from.region.factor);
    else if(from.region&&from.region.basis) said.push(from.region.basis);
  } else {
    from=((VALUATION.revenue_basis||{})[country]||{})[z.crop];
    if(!from)return "";
    said.push(f0.format(from.revenue)+" "+from.currency+"/ha in "+from.year+", "+from.source);
    if(from.note) said.push(from.note);
  }
  return '<span class="wsrc">'+esc(t("Where this figure comes from"))+": "+esc(said.join(" — "))+'</span>';
}
function sizeOk(){
  if(flow.peril==="car")return flow.interest.value>0&&!!flow.interest.modelYear;
  if(flow.peril==="flight")return flow.interest.value>0;
  sizeValue();
  var z=sizeState();
  return z.valid && flow.interest.value>=PERILS[flow.peril].limits[0];
}
function sizePayload(){
  if(flow.peril==="flight") return {kind:"trip", value:flow.interest.value};
  if(flow.peril==="car") return {kind:"vehicle", value:flow.interest.declared||flow.interest.value, model_year:flow.interest.modelYear||undefined};
  var z=sizeState();
  return z.kind==="home" ? {kind:"home", building:z.building, area_m2:z.area_m2, built:z.builtYear}
                         : {kind:"field", crop:z.crop, area_ha:z.area_ha};
}
function renderSize(){
  loadValuation();
  var z=sizeState(), box=$("size-box");
  var html;
  if(z.kind==="home"){
    html='<div class="sizegrid"><div class="field"><label class="label" for="size-building">'+esc(t("What kind of building"))+'</label>'+
      '<select id="size-building">'+Object.keys(BUILDING_WORDS).map(function(k){
        return '<option value="'+k+'"'+(k===z.building?' selected':'')+'>'+esc(t(BUILDING_WORDS[k]))+'</option>'; }).join("")+'</select></div>'+
      '<div class="field"><label class="label" for="size-area">'+esc(t("Floor area, m²"))+'</label>'+
      '<input id="size-area" class="dlg-input" inputmode="decimal" value="'+esc(z.area)+'" placeholder="'+esc(t("e.g. 110"))+'"></div>'+
      '<div class="field"><label class="label" for="size-built">'+esc(t("Year built"))+'</label>'+
      '<input id="size-built" class="dlg-input" inputmode="numeric" maxlength="4" value="'+esc(z.built||"")+'" placeholder="'+esc(t("e.g. 1998"))+'"></div></div>';
  } else {
    var grown=cropsHere();
    if(grown.length&&grown.indexOf(z.crop)<0) z.crop=grown[0];
    html='<div class="sizegrid"><div class="field"><label class="label" for="size-crop">'+esc(t("What grows there"))+'</label>'+
      '<select id="size-crop">'+grown.map(function(k){
        return '<option value="'+k+'"'+(k===z.crop?' selected':'')+'>'+esc(t(CROP_WORDS[k]))+'</option>'; }).join("")+'</select></div>'+
      '<div class="field"><label class="label" for="size-area">'+esc(t("Area"))+'</label><div class="unitrow">'+
      '<input id="size-area" class="dlg-input" inputmode="decimal" value="'+esc(z.area)+'" placeholder="'+esc(t("e.g. 40"))+'">'+
      '<select id="size-unit">'+Object.keys(UNIT_WORDS).map(function(k){
        return '<option value="'+k+'"'+(k===z.unit?' selected':'')+'>'+esc(t(UNIT_WORDS[k]))+'</option>'; }).join("")+'</select></div></div></div>';
  }
  html+='<div class="worth" id="size-worth" aria-live="polite"></div>';
  box.innerHTML=html;
  function update(){
    var value=sizeValue();
    flow.interest.value=value;
    if(z.valid) clampLimit();
    var min=PERILS[flow.peril].limits[0];
    var out=$("size-worth");
    if(!z.valid){ out.innerHTML='<span>'+esc(z.problem)+'</span>'; }
    else if(value<min){
      out.innerHTML='<b>'+money(value)+' USDC</b><span>'+esc(z.basis)+'</span><span>'+
        esc(t("Too small to insure here: the smallest cover is {min} USDC.",{min:f0.format(min)}))+'</span>';
    } else {
      out.innerHTML='<span>'+esc(t(z.kind==="home"?"What it would cost to rebuild":"A normal season's income"))+'</span>'+
        '<b>'+money(value)+' USDC</b><span>'+esc(z.basis)+'</span>'+
        (z.kind==="home"?'<span>'+esc(t("This is the building, not the land and not what it would sell for. An earthquake takes the building down; the land is still yours."))+'</span>':"")+
        whereTheRateIsFrom(z)+
        '<span>'+esc(t("This is the most cover it can carry. Figures are indicative; the insurer issuing the policy applies its own schedule."))+'</span>';
    }
    setNextLabel(); updatePriceBar();
  }
  $("size-area").addEventListener("input",function(e){ z.area=e.target.value.slice(0,12); update(); });
  if($("size-building"))$("size-building").addEventListener("change",function(e){ z.building=e.target.value; update(); });
  if($("size-built"))$("size-built").addEventListener("input",function(e){ z.built=e.target.value.replace(/\D/g,"").slice(0,4); update(); flow.quoted=null; if(flow.subject)loadHazard(); });
  if($("size-crop"))$("size-crop").addEventListener("change",function(e){ z.crop=e.target.value; update(); });
  if($("size-unit"))$("size-unit").addEventListener("change",function(e){ z.unit=e.target.value; update(); });
  update();
}

/* Cover is capped at the value just worked out: the slider stops there and the
   suggested amounts above it are not offered. */
function carYearHtml(){
  var y=flow.interest.modelYear||"";
  return '<div class="sizegrid"><div class="field"><label class="label" for="car-year">'+esc(t("Model year"))+'</label>'+
    '<input id="car-year" class="dlg-input" inputmode="numeric" maxlength="4" value="'+esc(y)+'" placeholder="'+esc(t("e.g. 2016"))+'"></div></div>'+
    '<div class="worth" id="car-worth" aria-live="polite"></div>';
}
function applyCarCap(){
  var i=flow.interest, out=$("car-worth"); if(!out)return;
  if(!i.declared) i.declared=i.value||valueFromSlider(+$("value").value)||flow.limit;
  var declared=i.declared;
  if(!i.modelYear){ out.innerHTML='<span>'+esc(t("Give the model year; it sets the most the car can be insured for."))+'</span>'; i.value=0; return; }
  var cap=Math.floor(carCap(i.modelYear));
  i.value=Math.min(declared,cap);
  out.innerHTML=(declared>cap
    ? '<b>'+money(cap)+' USDC</b><span>'+esc(t("A {year} model is worth at most about {cap}, so that is the most cover it can carry, whatever it is declared at.",{year:i.modelYear,cap:f0.format(cap)}))+'</span>'
    : '<b>'+money(i.value)+' USDC</b><span>'+esc(t("Declared at {value}, within what a {year} model can be worth (up to about {cap}).",{value:f0.format(declared),year:i.modelYear,cap:f0.format(cap)}))+'</span>');
  clampLimit();
}
function bindCarYear(){
  var f=$("car-year"); if(!f)return;
  f.addEventListener("input",function(e){
    var v=e.target.value.replace(/\D/g,"").slice(0,4); flow.interest.modelYear=v.length===4?parseInt(v,10):null;
    applyCarCap(); setNextLabel(); updatePriceBar();
  });
  applyCarCap();
}
function addressOk(){
  if(flow.peril!=="quake"&&flow.peril!=="car"&&flow.peril!=="storm")return true;
  var a=flow.interest.address||{};
  return !!(a.street&&a.street.trim().length>=3&&a.city&&a.city.trim().length>=2);
}
function coverCeiling(){
  var range=PERILS[flow.peril].limits;
  return Math.max(range[0], Math.min(range[1], flow.interest.value||range[1]));
}
function clampLimit(){
  var top=coverCeiling();
  if(flow.limit>top) flow.limit=top;
  if(flow.limit<PERILS[flow.peril].limits[0]) flow.limit=PERILS[flow.peril].limits[0];
}
function coverPresets(){
  var top=coverCeiling();
  var list=PERILS[flow.peril].presets.filter(function(v){ return v<top; });
  list.push(top);
  return list.slice(-4);
}

$("what").addEventListener("input",function(e){
  flow.interest.what=e.target.value.slice(0,80);
  // Their words now, so nothing offers over them again. Until they write, the
  // name follows the place: a buyer who looked at Mexico City and then chose
  // Osaka was carrying "a flat in Mexico City" into the declaration of what is
  // at risk, because the name was written once and never looked at the place
  // again.
  flow.interest.whatTouched=true;
  setNextLabel();
});
$("value").addEventListener("input",function(e){
  flow.interest.touched=true;
  flow.interest.value=valueFromSlider(+e.target.value);
  if(flow.peril==="car"){ flow.interest.declared=flow.interest.value; applyCarCap(); }
  $("value-val").textContent=f0.format(flow.interest.declared||flow.interest.value)+" USDC";
  renderInterest();
});
$("inside").addEventListener("click",function(){
  flow.interest.insideTouched=true;
  flow.interest.inside=!flow.interest.inside;
  $("inside").setAttribute("aria-pressed",String(flow.interest.inside));
  setNextLabel();
});
$("country").addEventListener("change",function(e){
  flow.interest.country=e.target.value;
  flow.statements={};        // a different country asks for different things
  renderInterest();
});

/* The address is written on one screen and the policy measures on another, and
   until this was written nothing joined them.

   A buyer choosing a home picks a place on the step before this one, and the
   list offers provinces, because the same list serves a drought policy that
   settles at a station. Pick "Adana" and the point the policy measures is the
   middle of Adana. Then type a street in Ceyhan, forty-four kilometres east,
   and nothing moves: the address is stored as text and the policy goes on
   measuring where it was.

   The two are not the same risk. The model puts intensity 7 at Adana's centre
   once in 581 years and at Ceyhan once in 305, and the expected loss on the
   same cover is 144.76 against 224.37, half as much again. The premium is the
   other way round, 456.74 against 380.24, because the middle of Adana is where
   the book is already concentrated and capital there costs more: the risk load
   is 300.39 against 137.92. So this is not a story about a buyer underpaying,
   and it would be wrong to tell it as one. What it reliably does is measure
   the policy forty-four kilometres from the building it is written on, so a
   shake that crosses the line over the building need not cross it where the
   policy is looking. That is basis risk, and it was made here rather than by
   the model.

   The address is looked up and what it finds is put in front of the buyer with
   the distance, and moving the measurement is one press. It is never moved on
   its own. A geocoder answers a street that does not exist with a street that
   does: "Ceyhan Caddesi 14, Ceyhan" comes back as an address in Ankara, 398 km
   away, with no hesitation at all. A policy silently moved there would be
   worse than the thing this fixes. */
var ADDR_HERE = {asked: "", found: null, seq: 0};
var addrHereTimer = null;

function addressAsTyped(){
  var a = (flow.interest && flow.interest.address) || {};
  var street = String(a.street || "").trim(), city = String(a.city || "").trim();
  if (street.length < 3 || city.length < 2) return "";
  return [street, a.number, city, a.postcode].filter(Boolean).join(" ").slice(0, 120);
}

function lookUpTheAddress(){
  var box = $("addr-far");
  if (!box) return;
  var measured = flow.peril === "quake" || flow.peril === "car" || flow.peril === "storm";
  var query = addressAsTyped(), at = coordinates();
  if (!measured || !link.live || !query || !at){ box.hidden = true; return; }
  if (ADDR_HERE.asked === query){ drawTheDistance(); return; }
  clearTimeout(addrHereTimer);
  addrHereTimer = setTimeout(function(){
    var seq = ++ADDR_HERE.seq;
    api("/api/geocode?q=" + encodeURIComponent(query) + "&lang=" + LANG +
        "&lat=" + at.latitude.toFixed(3) + "&lon=" + at.longitude.toFixed(3), {timeout: 9000})
      .then(function(reply){
        if (seq !== ADDR_HERE.seq) return;
        ADDR_HERE.asked = query;
        ADDR_HERE.found = (reply.places || [])[0] || null;
        drawTheDistance();
      }, function(){});
  }, 600);
}

function drawTheDistance(){
  var box = $("addr-far");
  if (!box) return;
  var found = ADDR_HERE.found, at = coordinates();
  if (!found || !at){ box.hidden = true; return; }
  var away = kmBetween([at.latitude, at.longitude], [found.latitude, found.longitude]);
  // Under a kilometre the two are the same building as far as any index here
  // can tell, and saying so would be noise on the screen that matters most.
  if (away < 1){ box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML =
    "<span>" + esc(t("The policy measures at {place}, which is {km} km from the address above.",
      {place: flow.place || t("the place you chose"), km: away < 10 ? f1.format(away) : f0.format(away)})) +
    "</span> <button type=\"button\" class=\"btn btn-sm\" id=\"addr-move\">" +
    esc(t("Measure at this address")) + "</button>" +
    "<span class=\"fine\">" + esc(t("Found: {what}", {what: found.name || ""})) + "</span>";
  $("addr-move").addEventListener("click", function(){
    setPoint(found.latitude, found.longitude, found.name || null, found.country || null);
    flow.quoted = null;
    ADDR_HERE.asked = "";
    drawTheDistance();
    renderInterest();
  });
}
