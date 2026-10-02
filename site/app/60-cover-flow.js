/* ================= the cover flow ================= */
var PERILS={
  quake:{where:N("Where do you live?"),hint:N("Cover pays on the strongest earthquake recorded inside a circle around this address."),
         term:365,limits:[2000,1000000],presets:[50000,100000,250000,500000]},
  drought:{where:N("Which weather station is closest to your land?"),hint:N("Cover pays on the rainfall this station records across the whole growing season."),
         term:150,limits:[100,1000000],presets:[25000,50000,80000,150000]},
  car:{where:N("Where is the car kept?"),hint:N("Cover pays when a single day's rain there is extreme for that place: the once in ten, twenty five or fifty years level."),
         term:365,limits:[500,250000],presets:[5000,10000,20000,40000]},
  storm:{where:N("Where is the home?"),hint:N("Cover pays when a single day's wind there is extreme for that place: the once in twenty five, fifty or a hundred years level."),
         term:365,limits:[2000,1000000],presets:[20000,50000,100000,250000]},
  flight:{where:N("Which flight?"),hint:N("Cover pays on how late the flight lands, and in full if it is cancelled."),
         term:2,limits:[200,5000],presets:[500,1000,1500,3000]}};
var flow={
  // The question being asked, and the furthest one ever asked. Going back to
  // a question already answered is free in both directions; going forward to
  // one never reached is not, and that is the difference the two record.
  step:1, reached:1,
  peril:"quake", subject:null, radius:50, limit:100000, instalments:1,
  // The declaration that separates cover from a wager.
  // Nothing is declared until somebody declares it. This opened at 150,000,
  // which is where that figure on a flight came from: the value a reader had
  // never entered, carried past a change of peril the reset did not cover.
  // Zero means "not yet", and the risk step starts it from the cover instead.
  interest:{what:"", value:0, inside:false, country:"TR", touched:false, declared:0, modelYear:null, address:null},
  place:null, busy:false, quoted:null, quotedFor:null, refusal:null, seq:0, stationKm:0,
  // Where the chosen point is, as the protocol answered: its country, and for
  // a point outside Türkiye the catalogue model's rates for each radius.
  placeCountry:null, pointCountry:null, grid:null, gridError:null, hazardSeq:0,
  // Signed statements this device is holding, by claim. They never leave except
  // to be checked, and nothing here is stored anywhere but this tab.
  statements:{}, need:null,
};

/* The rule, stated as a term of the policy rather than left to an aggregator
   nobody published. It is repeated here so the page can say it even when it
   cannot reach the protocol; when it can, the protocol's own sentence is used. */
var LOCAL_RULE=N("At least 3 of 4 validators must report the reading, the settled "+
  "figure is the median of what they report, and if their answers differ by more "+
  "than 5% the reading is refused rather than aggregated.");

/* Notes, not rules. Where cover may be written is decided by which companies
   have registered a licence, which this page reads from the protocol. These
   are the places whose law we have actually read, kept so a buyer there is told
   why their policy looks the way it does, with the statutes named. A country
   with no note here is not thereby closed, and a note here does not open one. */
var NOTES={
  TR:{name:"Türkiye",channel:"fronted",settlement:["fiat"],retail:true,
      authority:N("SEDDK, with the CBRT on settlement"),cash:N("lira"),
      note:N("Index cover is lawful here, but through a licensed insurer: the state "+
        "supported drought product runs under Agricultural Insurance Law 5363 through "+
        "the TARSİM pool. Writing cover without a licence is a criminal offence under "+
        "Article 35 of Law 5684, and Article 1401(2) of the Commercial Code makes such "+
        "a contract void and subject to the gambling provisions. Premium and claims "+
        "settle in lira: the 2021 central bank regulation prohibits using crypto assets "+
        "in payments, directly or indirectly.")},
  DE:{name:"Germany",channel:"fronted",settlement:["fiat"],retail:true,authority:"BaFin",cash:N("euro"),
      note:N("Distribution falls under the IDD and the carrier under Solvency II. "+
        "Parametric is permissible where it answers an economic need rather than "+
        "creating one, which is the insurable interest test under another name.")},
  GB:{name:"United Kingdom",channel:"fronted",settlement:["fiat"],retail:true,
      authority:N("FCA and PRA"),cash:N("pounds"),
      note:N("Insurable interest is required and at least nominal loss must exist at "+
        "claim time. A contract that is not insurance is likely caught as a contract "+
        "for differences instead, so there is no unregulated gap to sit in.")},
  AE:{name:"United Arab Emirates",channel:"index contract",settlement:["stablecoin","fiat"],
      retail:false,authority:N("DFSA and FSRA"),
      note:N("The DIFC and ADGM regimes are where crypto native risk transfer is usually "+
        "domiciled. Offered to professional counterparties as an index contract, not to "+
        "consumers as insurance.")},
  BM:{name:"Bermuda",channel:"direct",settlement:["stablecoin","fiat"],retail:false,
      authority:"BMA",
      note:N("Where this structure is actually licensed today. A reinsurer holding an "+
        "insurance licence and a digital asset business licence may take risk with "+
        "stablecoins as solvency capital, which is the layer this pool belongs at.")},
  US:{name:"the United States",channel:"refused",settlement:[],retail:false,
      authority:N("state insurance departments, and the CFTC on the derivative route"),
      note:N("Licensing is state by state and the federal product test requires insurable "+
        "interest maintained throughout, loss proven, and payment capped at that "+
        "interest. Pure parametric does not meet it. Not offered from here.")},
  ZZ:{name:"an unlisted country",channel:"refused",settlement:[],retail:false,
      authority:"unknown",
      note:N("No rule has been established for this country. Silence is not permission, "+
        "so nothing is offered until one is.")}
};

var STEPS=["s1","s2","si","s3","s4","s5"];
var RISK_STEP=3, AMOUNT_STEP=4;
var CONFIRM_STEP=5, DONE_STEP=6;

function stepsBar(){
  var names=[t("What"),t("Where"),t("At risk"),t("How much"),t("Confirm")],out="",i;
  for(i=0;i<names.length;i++){
    var cls=flow.step>i+1?"done":flow.step===i+1?"now":"";
    out+='<div class="step-dot '+cls+'"><i>'+(flow.step>i+1?"✓":(i+1))+'</i><span>'+esc(names[i])+'</span></div>';
    if(i<names.length-1)out+='<div class="step-line'+(flow.step>i+1?" done":"")+'"></div>';
  }
  $("steps").innerHTML=out;
  $("steps").hidden=flow.step>CONFIRM_STEP;
}

function optHtml(value,title,sub,lead,attr){
  return '<button class="opt" type="button" '+attr+'="'+esc(value)+'" aria-pressed="false">'+
    '<span class="lead">'+esc(lead)+'</span>'+
    '<span><span class="t">'+esc(title)+'</span><span class="s">'+esc(sub)+'</span></span>'+
    '<span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg></span>'+
    '</button>';
}
function flightDefaults(){
  if(!flow.flightDate){ var d=new Date(Date.now()+14*86400000); flow.flightDate=d.toISOString().slice(0,10); }
  // A route key names its airline first and the two ends after it, TK-IST-LHR.
  // Two airports chosen one at a time do not: that subject is SAW-ESB, and
  // taking the first part either way put an airport code where an airline code
  // goes. The box was filled with SAW1979, which no flight number can be, so
  // the page asked for a flight number over a field that already looked
  // answered and said nothing about what was wrong with it.
  //
  // Where the airline is not known it is left blank, and the placeholder shows
  // the shape of the thing to type.
  if(!flow.flightNumber&&flow.subject){
    var named=String(flow.subject).split("-");
    if(named.length===3&&/^[A-Za-z]{2}$/.test(named[0]))flow.flightNumber=named[0]+"1979";
  }
  // The scheduled departure, in the clock of the airport the flight leaves
  // from, which is how a ticket writes it. Cover has to be bought a day before
  // that moment, and a date on its own cannot say when the moment is.
  if(!flow.flightTime)flow.flightTime="09:00";
}
function subjectOptions(){
  // Only flights are a list. A place is a point, and there are too many points
  // in a country to put them in a list, so those are searched for instead.
  var out="",key;
  flightDefaults();
  var tomorrow=new Date(Date.now()+86400000).toISOString().slice(0,10), year=new Date(Date.now()+365*86400000).toISOString().slice(0,10);
  // The note belongs to the time field and not to its name, so it hangs off
  // aria-describedby rather than sitting inside the label, where it would be
  // read out as part of the field's own name every time.
  out+='<div class="tform"><label><span>'+esc(t("Flight number"))+'</span><input id="flight-no" maxlength="8" spellcheck="false" placeholder="TK1979" value="'+esc(flow.flightNumber||"")+'"></label>'+
       '<label><span>'+esc(t("Departure date"))+'</span><input id="flight-date" type="date" min="'+tomorrow+'" max="'+year+'" value="'+esc(flow.flightDate||"")+'"></label>'+
       '<label><span>'+esc(t("Scheduled departure"))+'</span><input id="flight-time" type="time" aria-describedby="flight-time-note" value="'+esc(flow.flightTime||"")+'"></label></div>'+
       '<p class="fine" id="flight-time-note" style="margin:6px 0 12px">'+
       esc(t("The time on the ticket, in the airport's own clock. Cover has to be bought 24 hours before it."))+'</p>';
  // Where it leaves from and where it lands, searched. The six routes below
  // used to be the whole offer, which is not a product: a traveller whose
  // flight is not one of them has nothing to insure. They are quick picks now,
  // and the two boxes above them reach every airport there is.
  out+='<div class="tform" style="align-items:flex-start">'+
       airportField("from",t("From"),flow.flightFrom,flow.flightFromText)+
       airportField("to",t("To"),flow.flightTo,flow.flightToText)+
       '</div>';
  out+='<p class="fine" style="margin:10px 0 6px">'+esc(t("Or one of the routes with a published record:"))+'</p>';
  for(key in ROUTES){ if(!Object.prototype.hasOwnProperty.call(ROUTES,key))continue;
    var r=ROUTES[key], ends=key.split("-");
    out+=optHtml(ends[1]+"-"+ends[2],t("{from} to {to}",{from:r.from,to:r.to}),
      t("{carrier} · {late} arrive late, median delay {minutes} minutes",
        {carrier:r.carrier,late:pct(r.late,0),minutes:f0.format(r.median)}),
      r.carrier.slice(0,2).toUpperCase(),"data-value");
  }
  return out;
}
/* One end of the flight: a box to search in, what was chosen, and room for
   the answers. Rendered as its own block so a keystroke redraws the list and
   not the step, which would take the focus out of the box being typed in. */
function airportField(side,label,code,text){
  return '<label style="flex:1 1 220px"><span>'+esc(label)+'</span>'+
    '<input id="air-'+side+'" type="text" autocomplete="off" spellcheck="false" '+
      'placeholder="'+esc(t("City or airport code"))+'" value="'+esc(text||"")+'">'+
    '<small class="fine" id="air-'+side+'-said">'+(code?esc(code):"")+'</small>'+
    '<span class="results" id="air-'+side+'-hits"></span></label>';
}
/* What the page knows about airports it has been told about, so a code chosen
   once can still be named after the list has moved on. */
var AIRPORTS={};
function airportHits(side){
  var input=$("air-"+side), box=$("air-"+side+"-hits");
  if(!input||!box)return;
  var q=input.value.trim();
  if(q.length<2){ box.innerHTML=""; return; }
  var seq=(airportHits.seq=(airportHits.seq||0)+1);
  api("/api/airports?query="+encodeURIComponent(q)).then(function(reply){
    if(seq!==airportHits.seq)return;
    var hits=(reply&&reply.airports)||[];
    hits.forEach(function(a){ AIRPORTS[a.iata]=a; });
    if(!hits.length){ box.innerHTML='<div class="empty">'+esc(t("No airport matched that."))+'</div>'; return; }
    // Whose data this is, under the results that came from it, which is where
    // the place search already puts GeoNames. The protocol has been sending
    // this line all along and the page was dropping it; the licence asks for
    // the notice, and a reader deserves to know who says an airport is where
    // it is.
    box.innerHTML=hits.map(function(a){
      return '<button class="opt" type="button" data-air="'+esc(a.iata)+'" data-side="'+esc(side)+'">'+
        '<span class="lead">'+esc(a.iata)+'</span><span class="opt-text"><b>'+
        esc([a.city,a.name].filter(Boolean).join(" · "))+'</b><small>'+
        esc(regionName(a.country)||a.country)+'</small></span></button>';
    }).join("")
      +(reply&&reply.attribution
        ? '<p class="hint">'+esc(t("Airport codes, names and time zones come from airportsdata (github.com/mborsetti/airportsdata), MIT licensed."))+'</p>'
        : "");
  },function(){ box.innerHTML=""; });
}
function setAirport(side,code){
  var a=AIRPORTS[code]||{iata:code,city:"",name:code};
  var text=[a.city||a.name,"("+code+")"].join(" ");
  if(side==="from"){ flow.flightFrom=code; flow.flightFromText=text; }
  else { flow.flightTo=code; flow.flightToText=text; }
  flow.subject=(flow.flightFrom&&flow.flightTo)?flow.flightFrom+"-"+flow.flightTo:null;
  flow.quoted=null; flow.offers=null;
}

function gapInside(system,centre,radius){
  // Is a stretch the model treats as overdue actually inside this circle? The
  // buyer is told why Istanbul costs more, rather than only charged for it.
  for(var e=0;e<system.elev.length;e++){
    for(var i=system.elev[e][0];i<system.elev[e][1]&&i<system.trace.length-1;i++){
      var a=system.trace[i],b=system.trace[i+1];
      for(var j=0;j<8;j++){
        var f=(j+0.5)/8;
        if(kmBetween([a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f],centre)<=radius)return true;
      }
    }
  }
  return false;
}

function radiusOptions(){
  var at=coordinates(),centre=[at.latitude,at.longitude];
  var out='<div class="label">'+esc(t("How wide a circle?"))+'</div>';
  if(flow.grid){
    [25,50,100].forEach(function(r){
      var century=gridRate(r)*gridShare(flow.grid,5.5)*100;
      var n=century>=10?f0.format(Math.round(century)):f1.format(century);
      out+=optHtml(String(r),t("{km} km around you",{km:r}),
        t("About {n} earthquakes of magnitude 5.5 or more a century inside this circle",{n:n}),
        String(r),"data-radius");
    });
    return out;
  }
  [25,50,100].forEach(function(r){
    var ch=characteristicRate(at.latitude,at.longitude,r),sub;
    if(ch.dominant){
      sub=t("{km} km of the {fault} runs inside this circle",
          {km:f0.format(Math.round(weightedLengthInside(ch.dominant,centre,r))),fault:t(ch.dominant.name)});
    }else{
      sub=t("No mapped fault crosses this circle. Background seismicity only.");
    }
    out+=optHtml(String(r),t("{km} km around you",{km:r}),sub,String(r),"data-radius");
  });
  return out;
}

function modelCardLink(code){
  return '<a href="'+esc(API+"/api/models/"+code)+'" target="_blank" rel="noopener">'+
    esc(t("Read the model card"))+'</a>';
}
function radiusNoteHtml(){
  if(!flow.grid)return esc(radiusNote());
  var g=flow.grid,bits=[];
  bits.push(t("Priced by the catalogue model for {country}. Before it priced anything, a version fitted to earthquakes up to {fit} was tested on {test} onward, and passed.",
    {country:regionName(g.country),fit:g.fitted_until,test:g.tested_from}));
  var small=gridRate(flow.radius),big=gridRate(Math.min(100,flow.radius*2));
  if(flow.radius<100&&small>0)
    bits.push(t("Doubling the radius takes in about {x} times as many.",{x:f1.format(big/small)}));
  /* The card of the model that priced this address, which is not always the
     country's. The United States is three catalogue models -- the lower forty
     eight, Alaska and Hawaii -- and a buyer in Anchorage reading the American
     card would be reading a model fitted on ground three thousand kilometres
     away, with a different b value and a smaller largest event. */
  return esc(bits.join(" "))+" "+modelCardLink(g.region||g.country);
}
function radiusNote(){
  var at=coordinates(); if(!at)return "";
  var centre=[at.latitude,at.longitude];
  var site=siteAt(at.latitude,at.longitude);
  var ch=characteristicRate(at.latitude,at.longitude,flow.radius);
  var bits=[];
  bits.push(site.nearest
    ? t("You are about {km} km from the {fault}, in {zone}.",
        {km:f0.format(Math.round(site.distance)),fault:t(site.nearest.name),zone:t(site.zoneName)})
    : t("No mapped fault runs within {km} km of here, so this price is background seismicity alone.",{km:INTERIOR_KM}));
  if(ch.dominant){
    bits.push(t("The radius is a lever rather than a guess: a wider circle takes in more fault length, and the rate rises with the length it takes in."));
    if(ch.dominant.gap&&gapInside(ch.dominant,centre,flow.radius))bits.push(t(ch.dominant.gap));
  }
  return bits.join(" ");
}

function limitFromSlider(v){
  var range=[PERILS[flow.peril].limits[0], coverCeiling()],f=(v-1)/99;
  if(range[1]<=range[0]) return range[0];
  var raw=range[0]*Math.pow(range[1]/range[0],f);
  var step=raw>200000?25000:raw>50000?10000:raw>5000?1000:100;
  return Math.min(range[1],Math.max(range[0],Math.round(raw/step)*step));
}
function sliderFromLimit(limit){
  var range=[PERILS[flow.peril].limits[0], coverCeiling()];
  if(range[1]<=range[0]) return 100;
  return Math.round(1+Math.log(limit/range[0])/Math.log(range[1]/range[0])*99);
}
function coordinates(){
  if (!flow.subject || flow.peril === "flight") return null;
  var parts = String(flow.subject).split(",");
  return {latitude: parseFloat(parts[0]), longitude: parseFloat(parts[1])};
}

/* A place name fits in 60 characters, the most a subject field may carry: the
   country goes first, then the street, never the district that says where. */
function placeLabel(){
  var parts=String(flow.place||"").split(", ").filter(Boolean);
  while(parts.join(", ").length>60&&parts.length>2)parts.pop();
  while(parts.join(", ").length>60&&parts.length>1)parts.shift();
  return parts.join(", ").slice(0,60);
}
function subjectPayload(){
  if (flow.peril === "flight"){ flightDefaults(); return {
    origin: flow.flightFrom, destination: flow.flightTo,
    flight_number: flow.flightNumber, departure_date: flow.flightDate,
    departure_time: flow.flightTime}; }
  var at = coordinates();
  if (flow.peril === "car" || flow.peril === "storm"){
    return {latitude: at.latitude, longitude: at.longitude, place: placeLabel()};
  }
  if (flow.peril === "drought"){
    var z = flow.size && flow.size.kind === "field" && flow.size.valid ? flow.size : null;
    return {station: nearestStation(at), distance_km: 6, hectares: z ? z.area_ha : 50};
  }
  var out = {latitude: at.latitude, longitude: at.longitude,
          radius_km: flow.radius, place: placeLabel()};
  if (shakingIndex()) out.index = "shaking";
  var z = flow.size && flow.size.kind === "home" && flow.size.valid ? flow.size : null;
  if (z && z.builtYear) out.built = z.builtYear;
  return out;
}

function nearestStation(at){
  // Drought settles on a named station, so the coordinate picks the closest one
  // and the buyer is told which, because basis risk lives in that distance.
  var best = null, bestKm = Infinity, code;
  for (code in STATIONS){
    if (!Object.prototype.hasOwnProperty.call(STATIONS, code)) continue;
    var km = kmBetween([at.latitude, at.longitude],
                       [STATIONS[code].lat, STATIONS[code].lon]);
    if (km < bestKm){ bestKm = km; best = code; }
  }
  flow.stationKm = bestKm;
  return best;
}

function structure(){
  if(flow.peril==="quake"){
    var z=flow.size&&flow.size.kind==="home"&&flow.size.valid?flow.size:null;
    // No year yet means the price bar before the building has been described,
    // and the protocol prices that as the oldest building rather than the
    // newest. The page's own figure has to say the same thing, or the bar
    // would fall when the protocol answered and rise again when the buyer
    // typed a year.
    var year=z&&z.builtYear?z.builtYear:(VALUATION.built||[1900])[0];
    /* Rounded where the protocol rounds it, and the protocol rounds twice:
       vulnerability() returns the shift to two places, curve_for subtracts it
       and rounds the level to two places, and for the magnitude index the
       magnitude step is rounded to two places before that. The page rounded
       once, at the end, which is a different number whenever the shift has a
       half cent in it. Outside Türkiye that is every building: measured across
       every year from 1900, 106 of 254 cases disagreed, a pre-1981 New York
       flat reading 6.63 / 7.63 / 8.63 on the page against 6.62 / 7.62 / 8.62
       on the contract and on the chain's own predicate. Turkish buildings
       happened to agree at every age, which is why this survived. With the
       rounding in the same places, 0 of 254 disagree. */
    var d=Math.round(homeAge(year,riskCountry()).shift*100)/100;
    var base=shakingIndex()?CURVES.shake:CURVES.quake;
    var step=shakingIndex()?d:Math.round(d*.4*100)/100;
    return {shape:base.shape, pts:base.pts.map(function(p){ return [Math.round((p[0]-step)*100)/100, p[1]]; })};
  }
  if(flow.peril==="flight")return CURVES.flight;
  if(flow.peril==="car")return carCurve();
  if(flow.peril==="storm")return stormCurve();
  var st=STATIONS[nearestStation(coordinates())];
  return {shape:"ramp",pts:CURVES.drought.pts.map(function(pt){return [pt[0]*st.normal,pt[1]];})};
}
function exceedance(){
  if(flow.peril==="flight"){
    // The protocol tells the page how long the sector is; until it has, the
    // middle band stands in, and the bar says the figure is the page's own.
    var q=flow.quoted&&flow.quoted.flight;
    var key=(flow.flightNumber||"").slice(0,2).toUpperCase()+"-"+flow.flightFrom+"-"+flow.flightTo;
    return flightExc(key,q?q.sector_km:null);
  }
  if(flow.peril==="car")return carExc(PERILS.car.term);
  if(flow.peril==="storm")return stormExc(PERILS.storm.term);
  var at = coordinates();
  if(flow.peril==="quake")
    return quakeExcAt(at.latitude, at.longitude, flow.radius, PERILS.quake.term);
  return droughtExc(nearestStation(at));
}
function quote(){return priceIt(structure(),exceedance(),flow.limit,PERILS[flow.peril].term);}

/* quote() is the model running in this page: instant, and what the slider moves
   against. priced() is what the confirm step shows, which is the protocol's own
   figure whenever the protocol answered. The two are never mixed inside one
   panel, and the bar at the top of the page says which you are looking at. */
var PERIL_KEYS={quake:"earthquake",drought:"drought",flight:"flight_delay",car:"vehicle_flood",storm:"storm"};

var COUNTRIES=[["AF","Afghanistan"],["AL","Albania"],["DZ","Algeria"],["AS","American Samoa"],["AD","Andorra"],["AO","Angola"],["AI","Anguilla"],["AQ","Antarctica"],["AG","Antigua and Barbuda"],["AR","Argentina"],["AM","Armenia"],["AW","Aruba"],["AU","Australia"],["AT","Austria"],["AZ","Azerbaijan"],["BS","Bahamas"],["BH","Bahrain"],["BD","Bangladesh"],["BB","Barbados"],["BY","Belarus"],["BE","Belgium"],["BZ","Belize"],["BJ","Benin"],["BM","Bermuda"],["BT","Bhutan"],["BO","Bolivia"],["BQ","Bonaire, Sint Eustatius and Saba"],["BA","Bosnia and Herzegovina"],["BW","Botswana"],["BV","Bouvet Island"],["BR","Brazil"],["IO","British Indian Ocean Territory"],["BN","Brunei Darussalam"],["BG","Bulgaria"],["BF","Burkina Faso"],["BI","Burundi"],["CV","Cabo Verde"],["KH","Cambodia"],["CM","Cameroon"],["CA","Canada"],["KY","Cayman Islands"],["CF","Central African Republic"],["TD","Chad"],["CL","Chile"],["CN","China"],["CX","Christmas Island"],["CC","Cocos (Keeling) Islands"],["CO","Colombia"],["KM","Comoros"],["CG","Congo"],["CD","Congo, The Democratic Republic of the"],["CK","Cook Islands"],["CR","Costa Rica"],["HR","Croatia"],["CU","Cuba"],["CW","Curaçao"],["CY","Cyprus"],["CZ","Czechia"],["CI","Côte d'Ivoire"],["DK","Denmark"],["DJ","Djibouti"],["DM","Dominica"],["DO","Dominican Republic"],["EC","Ecuador"],["EG","Egypt"],["SV","El Salvador"],["GQ","Equatorial Guinea"],["ER","Eritrea"],["EE","Estonia"],["SZ","Eswatini"],["ET","Ethiopia"],["FK","Falkland Islands (Malvinas)"],["FO","Faroe Islands"],["FJ","Fiji"],["FI","Finland"],["FR","France"],["GF","French Guiana"],["PF","French Polynesia"],["TF","French Southern Territories"],["GA","Gabon"],["GM","Gambia"],["GE","Georgia"],["DE","Germany"],["GH","Ghana"],["GI","Gibraltar"],["GR","Greece"],["GL","Greenland"],["GD","Grenada"],["GP","Guadeloupe"],["GU","Guam"],["GT","Guatemala"],["GG","Guernsey"],["GN","Guinea"],["GW","Guinea-Bissau"],["GY","Guyana"],["HT","Haiti"],["HM","Heard Island and McDonald Islands"],["VA","Holy See (Vatican City State)"],["HN","Honduras"],["HK","Hong Kong"],["HU","Hungary"],["IS","Iceland"],["IN","India"],["ID","Indonesia"],["IR","Iran"],["IQ","Iraq"],["IE","Ireland"],["IM","Isle of Man"],["IL","Israel"],["IT","Italy"],["JM","Jamaica"],["JP","Japan"],["JE","Jersey"],["JO","Jordan"],["KZ","Kazakhstan"],["KE","Kenya"],["KI","Kiribati"],["KP","North Korea"],["KR","South Korea"],["KW","Kuwait"],["KG","Kyrgyzstan"],["LA","Laos"],["LV","Latvia"],["LB","Lebanon"],["LS","Lesotho"],["LR","Liberia"],["LY","Libya"],["LI","Liechtenstein"],["LT","Lithuania"],["LU","Luxembourg"],["MO","Macao"],["MG","Madagascar"],["MW","Malawi"],["MY","Malaysia"],["MV","Maldives"],["ML","Mali"],["MT","Malta"],["MH","Marshall Islands"],["MQ","Martinique"],["MR","Mauritania"],["MU","Mauritius"],["YT","Mayotte"],["MX","Mexico"],["FM","Micronesia, Federated States of"],["MD","Moldova"],["MC","Monaco"],["MN","Mongolia"],["ME","Montenegro"],["MS","Montserrat"],["MA","Morocco"],["MZ","Mozambique"],["MM","Myanmar"],["NA","Namibia"],["NR","Nauru"],["NP","Nepal"],["NL","Netherlands"],["NC","New Caledonia"],["NZ","New Zealand"],["NI","Nicaragua"],["NE","Niger"],["NG","Nigeria"],["NU","Niue"],["NF","Norfolk Island"],["MK","North Macedonia"],["MP","Northern Mariana Islands"],["NO","Norway"],["OM","Oman"],["PK","Pakistan"],["PW","Palau"],["PS","Palestine, State of"],["PA","Panama"],["PG","Papua New Guinea"],["PY","Paraguay"],["PE","Peru"],["PH","Philippines"],["PN","Pitcairn"],["PL","Poland"],["PT","Portugal"],["PR","Puerto Rico"],["QA","Qatar"],["RO","Romania"],["RU","Russian Federation"],["RW","Rwanda"],["RE","Réunion"],["BL","Saint Barthélemy"],["SH","Saint Helena, Ascension and Tristan da Cunha"],["KN","Saint Kitts and Nevis"],["LC","Saint Lucia"],["MF","Saint Martin (French part)"],["PM","Saint Pierre and Miquelon"],["VC","Saint Vincent and the Grenadines"],["WS","Samoa"],["SM","San Marino"],["ST","Sao Tome and Principe"],["SA","Saudi Arabia"],["SN","Senegal"],["RS","Serbia"],["SC","Seychelles"],["SL","Sierra Leone"],["SG","Singapore"],["SX","Sint Maarten (Dutch part)"],["SK","Slovakia"],["SI","Slovenia"],["SB","Solomon Islands"],["SO","Somalia"],["ZA","South Africa"],["GS","South Georgia and the South Sandwich Islands"],["SS","South Sudan"],["ES","Spain"],["LK","Sri Lanka"],["SD","Sudan"],["SR","Suriname"],["SJ","Svalbard and Jan Mayen"],["SE","Sweden"],["CH","Switzerland"],["SY","Syria"],["TW","Taiwan"],["TJ","Tajikistan"],["TZ","Tanzania"],["TH","Thailand"],["TL","Timor-Leste"],["TG","Togo"],["TK","Tokelau"],["TO","Tonga"],["TT","Trinidad and Tobago"],["TN","Tunisia"],["TM","Turkmenistan"],["TC","Turks and Caicos Islands"],["TV","Tuvalu"],["TR","Türkiye"],["UG","Uganda"],["UA","Ukraine"],["AE","United Arab Emirates"],["GB","United Kingdom"],["US","United States"],["UM","United States Minor Outlying Islands"],["UY","Uruguay"],["UZ","Uzbekistan"],["VU","Vanuatu"],["VE","Venezuela"],["VN","Vietnam"],["VG","Virgin Islands, British"],["VI","Virgin Islands, U.S."],["WF","Wallis and Futuna"],["EH","Western Sahara"],["YE","Yemen"],["ZM","Zambia"],["ZW","Zimbabwe"],["AX","Åland Islands"]];

/* Where cover can actually be written. Read from the protocol, because it is a
   consequence of which companies have registered rather than a list anyone
   maintains here. Until it is read, no country is claimed to be open. */
var COVERAGE=null;

/* Read again whenever a screen that depends on it opens, rather than once per
   page load. The first version cached it, so a country activated while the
   page was open stayed shut until a reload, and the reviewer testing it was
   told nobody was registered by a page that had simply not asked. A short
   window stops a burst of re-renders asking five times. */
var COVERAGE_AT=0, COVERAGE_PENDING=null;
function loadCoverage(force){
  var fresh = COVERAGE && (Date.now()-COVERAGE_AT < 8000);
  if(COVERAGE && (fresh || !force)) return Promise.resolve(COVERAGE);
  if(COVERAGE_PENDING) return COVERAGE_PENDING;
  COVERAGE_PENDING = api("/api/compliance",{timeout:9000}).then(function(reply){
    COVERAGE={};
    (reply.coverage||[]).forEach(function(row){COVERAGE[row.country]=row;});
    COVERAGE.__waiting={};
    (reply.waiting||[]).forEach(function(row){COVERAGE.__waiting[row.country]=row;});
    COVERAGE.__priceable=reply.priceable||{};
    COVERAGE.__registry=reply.registry||{};
    COVERAGE.__unlisted=reply.unlisted||"";
    COVERAGE.__aggregation=reply.aggregation_rule||"";
    COVERAGE_AT=Date.now(); COVERAGE_PENDING=null;
    return COVERAGE;
  },function(){ COVERAGE_PENDING=null; return COVERAGE; });
  return COVERAGE_PENDING;
}

/* Where the licence has to be. For something tied to a place, the place: a
   flat in Istanbul needs paper licensed in Türkiye whoever owns it. For a
   flight, which follows the person, where they live. The protocol applies the
   same rule when the policy is bound, so the page and the protocol cannot give
   two different answers. */
function riskCountry(){
  if(flow.peril==="quake") return flow.pointCountry||flow.placeCountry||"TR";
  if(flow.peril==="car"||flow.peril==="storm") return "TR";
  if(flow.peril==="drought"){
    var code=nearestStation(coordinates());
    return code ? code.split("-")[0] : flow.interest.country;
  }
  return flow.interest.country;
}
function tiedToPlace(){ return flow.peril!=="flight"; }

function coverFor(code){
  return (COVERAGE&&COVERAGE[code])||null;
}

function countryName(code){ return regionName(code); }

function fillCountries(select,selected){
  if(!select||select.dataset.filled===LANG){
    if(select&&selected)select.value=selected;
    return;
  }
  var keep=select.value||selected;
  var collator=new Intl.Collator(LOCALES[LANG]||"en-US");
  var rows=COUNTRIES.map(function(row){ return [row[0], regionName(row[0])]; })
    .sort(function(a,b){ return collator.compare(a[1],b[1]); });
  select.innerHTML=rows.map(function(row){
    return '<option value="'+row[0]+'">'+esc(row[1])+'</option>';
  }).join("");
  select.dataset.filled=LANG;
  if(keep)select.value=keep;
}

function quoteKey(){
  return JSON.stringify([PERIL_KEYS[flow.peril],subjectPayload(),flow.limit,PERILS[flow.peril].term]);
}
function priced(){
  var q=flow.quoted;
  // The protocol's price stands only for the cover it priced: move the
  // slider or the pin and the page's own model answers until the protocol does.
  if(!q||flow.quotedFor!==quoteKey())return quote();
  // The company that issues it prices it. The expected loss and the capital
  // the cover ties up are the protocol's measurement of the risk and the same
  // whoever writes it; what is charged for them is the company's own, and it
  // is what the buyer chose from the list. Reading the pool's figure here
  // instead put one price on the screen and sent a different one to be paid.
  var mine=offerForPrice();
  return {el:q.expected_loss, riskLoad:mine?mine.risk_load:q.risk_load,
          expenses:mine?mine.expense_load:q.expense_load,
          premium:mine?mine.premium:q.premium, trigger:q.trigger_probability,
          capital:q.marginal_capital, basis:q.risk_basis, fromProtocol:true};
}


function refreshQuote(){
  /* Asked once on arrival at the confirm step, and whenever what is being
     bought changes. Until it answers there is no price on the screen at all,
     because this page's own model prices the capital one policy needs on its
     own while the protocol prices the capital this policy adds to a book of a
     hundred thousand others, and those are different numbers -- far enough
     apart that showing the first and then replacing it with the second is
     quoting a price that was never on offer. A buyer who moves on is still
     not overwritten by a late reply.

     What is already in hand is kept while this runs. It used to be thrown
     away first, which meant the confirm step -- the page somebody signs on --
     opened on the browser's own figure for as long as the round trip took,
     even though the protocol had already answered for exactly this policy one
     step earlier. priced() checks that an answer belongs to what is on the
     screen before it uses it, so nothing stale can be shown by keeping it. */
  flow.refusal=null; flow.unreached=false;
  var atConfirm=flow.step===CONFIRM_STEP, done=atConfirm?renderPrice:updatePriceBar;
  if(!link.live){done();return;}
  // Nor until the subject is whole. A flight without its number is refused
  // every time -- the protocol answers "that cover cannot be priced" -- and
  // asking anyway spends a call to be told what this page already knows: the
  // same four checks the Continue button reads to say what is missing. Nothing
  // waits on this: an answer refused every time is not an answer worth waiting
  // for, and the page already says which question is unfinished.
  if(!flightReady()||!quakeReady()||!stormReady()||!carReady()){done();return;}
  /* The key is taken once the company is known, not before. The offers come
     back first and name the company the price will be struck on, and the key
     carries that company; keying on the empty choice made the answer stale the
     moment it arrived, and cost a second round trip to say the same number. */
  var seq=++flow.seq, key=null;
  flow.pricing=true;
  api("/api/offers?country="+encodeURIComponent(flow.interest.country||"")+"&professional="+(flow.interest.professional?"true":"false"),{method:"POST",timeout:25000,body:{
    peril:PERIL_KEYS[flow.peril], subject:subjectPayload(),
    limit:flow.limit, term_days:PERILS[flow.peril].term,
  }}).then(function(offers){
    if(seq!==flow.seq)return;
    flow.offers=offers.offers||[];
    flow.heldBack=offers.held_back||[];
    if(!flow.carrier||!flow.offers.some(function(o){return o.carrier_id===flow.carrier;}))
      flow.carrier=flow.offers.length?flow.offers[0].carrier_id:null;
    key=quoteKey();
    return api("/api/quote",{method:"POST",timeout:25000,body:{
      peril:PERIL_KEYS[flow.peril], subject:subjectPayload(),
      limit:flow.limit, term_days:PERILS[flow.peril].term,
    }});
  }).then(function(reply){
    if(seq!==flow.seq||!reply)return;
    flow.pricing=false;
    flow.quoted=reply; flow.quotedFor=key;
    (flow.step===CONFIRM_STEP?renderPrice:updatePriceBar)();
  },function(error){
    if(seq!==flow.seq)return;
    flow.pricing=false;
    /* A refusal and a silence are not the same answer, and the page had no
       way to tell them apart. It read "the protocol sent no reason" as "the
       protocol has not answered yet", so a quote that timed out, a connection
       that dropped, or any error whose body carries no detail left every one
       of the five places a price goes reading "working out your price".
       Measured: a quote held unanswered leaves the paying screen saying
       "Pricing…" for as long as the buyer is willing to look at it, with
       nothing else on the screen and no way forward. Seventy-five seconds
       was as long as the measurement was willing to look.

       A refusal is the protocol's decision and it is final. A silence is not
       a decision at all, so it is told apart here, said differently, and
       offered the one thing a decision cannot be offered: another go. */
    flow.refusal=(error&&error.payload&&error.payload.detail)||null;
    flow.unreached=!flow.refusal;
    (flow.step===CONFIRM_STEP?renderPrice:updatePriceBar)();
  });
}
/* The whole price, the moment there is a place: the pool's premium and the
   company's fee together, before anything personal is asked. Asked again,
   after a pause, whenever the cover or the pin moves; the page's own model
   fills the bar in the meantime, so it is never empty and never stale. */
var quoteTimer=null;
function scheduleQuote(){
  if(!link.live||flow.step>=CONFIRM_STEP)return;
  if(flow.quotedFor===quoteKey()&&flow.quoted)return;
  clearTimeout(quoteTimer);
  quoteTimer=setTimeout(function(){
    if(flow.step>=CONFIRM_STEP||flow.quotedFor===quoteKey()&&flow.quoted)return;
    if(!flow.peril||!flow.subject||!flow.limit||!quakeReady())return;
    refreshQuote();
  },450);
}

function stationFor(){return STATIONS[nearestStation(coordinates())];}

function subjectLabel(){
  if(flow.peril==="flight"){
    if(flow.flightFrom&&flow.flightTo)
      return t("{from} to {to}",{from:flow.flightFromText||flow.flightFrom,
                                 to:flow.flightToText||flow.flightTo});
    return String(flow.subject||"");
  }
  return flow.place||String(flow.subject||"").replace(",",", ");
}
function sourceName(){
  if(flow.peril==="quake")return t("the national seismic network");
  if(flow.peril==="drought")return t("the meteorological station");
  if(flow.peril==="car")return t("the rainfall record for the place");
  if(flow.peril==="storm")return t("the wind record for the place");
  return t("the airline's published arrival time");
}
function deadlineText(){
  return t("Premium returned in full after {days} days",
    {days:flow.peril==="quake"?7:flow.peril==="drought"?21:(flow.peril==="car"||flow.peril==="storm")?14:3});
}

/* The whole price: the pool's premium and the issuing company's fee.

   The most read sentence on the page said "You pay N USDC now, and nothing
   else ever" and passed the premium alone, while the price row below it, the
   price bar and payableNow all add the fee, and the server debits it.
   Measured on one Istanbul earthquake policy -- 100,000 limit, 365 days, a
   1975 building -- the sentence said 11,758.31 and the address was debited
   12,087.54; against the carrier charging nine per cent the gap is 1,061.36.
   Six sentences, one per peril, in seven languages. */
function wholePrice(){
  var offer=offerForPrice();
  return priced().premium+(offer?offer.fee:0);
}

/* What the buyer pays, as its own clause.

   Every sentence ended with "and nothing else ever", which is true of a
   single payment and false of every plan: measured on a Tokyo policy, the
   sentence said 10,143.15 now and nothing else ever for cover the contract
   priced at 10,948.52 in twelve instalments of 912.38. The plan box, the
   price row and the price bar all knew; the sentence above them did not. */
function payClause(){
  var whole=wholePrice(), n=flow.instalments||1;
  if(n<2)return t("You pay <b>{premium} USDC</b> now, and nothing else ever.",{premium:money(whole)});
  var plan=(PLANS.plans||[]).filter(function(p){return p.count===n;})[0]||{surcharge:0};
  var total=whole*(1+plan.surcharge);
  return t("You pay <b>{each} USDC</b> today, then {rest} more payments of the same, <b>{total} USDC</b> in all.",
    {each:money(total/n), rest:n-1, total:money(total)});
}
function plainSentence(){
  var q=priced(),l=flow.limit;
  /* The levels and the first payment come from the policy's own curve, as the
     car and storm sentences below have always taken theirs. This one had all
     three written into it: intensity VI, intensity VIII, and a quarter of the
     limit. The shaking cover pays 35 per cent at its first step, not 25, and
     that step is 6.25 in Istanbul and 6.62 in New York rather than VI, because
     an older building is damaged by less shaking. The most read sentence on
     the page was wrong about what the policy pays and about when. */
  if(flow.peril==="quake"&&shakingIndex()){
    var qc=structure().pts;
    return t("If the ground at {place} shakes at <b>intensity {level} or more</b> in the next year, as the seismic networks' shaking maps record it, you receive <em>{first} USDC</em>, rising to <em>{full}</em> at intensity {top}. {pay}",
      {place:esc(subjectLabel()), level:fLevel.format(qc[0][0]), top:fLevel.format(qc[2][0]),
       first:money(qc[0][1]*l), full:money(l), pay:payClause()});
  }
  if(flow.peril==="quake"){
    var mc=structure().pts;
    return t("If an earthquake of <b>magnitude {mag} or more</b> is recorded within <b>{km} km</b> of {place} in the next year, you receive <em>{first} USDC</em>, rising to <em>{full}</em> for a magnitude {top}. {pay}",
      {mag:fLevel.format(mc[0][0]), top:fLevel.format(mc[2][0]), km:flow.radius,
       place:esc(subjectLabel()), first:money(mc[0][1]*l), full:money(l), pay:payClause()});
  }
  if(flow.peril==="car"){
    var cc=structure().pts;
    return t("If <b>{mm} mm or more</b> of rain falls in one day at {place} in the next year, you receive <em>{first} USDC</em>, rising to <em>{full}</em> at {top} mm. {pay}",
      {mm:f1.format(cc[0][0]), place:esc(subjectLabel()), first:money(cc[0][1]*l), full:money(l), top:f1.format(cc[2][0]), pay:payClause()});
  }
  if(flow.peril==="storm"){
    var sc=structure().pts;
    return t("If the wind at {place} reaches <b>{kmh} km/h or more</b> on one day in the next year, you receive <em>{first} USDC</em>, rising to <em>{full}</em> at {top} km/h. {pay}",
      {kmh:fLevel.format(sc[0][0]), place:esc(subjectLabel()), first:money(sc[0][1]*l), full:money(l), top:fLevel.format(sc[2][0]), pay:payClause()});
  }
  if(flow.peril==="drought"){
    var s=stationFor();
    return t("If the station at {station}, <b>{km} km</b> from {place}, records less than <b>{mm} mm</b> of rain across the {season} season, you start receiving money, up to <em>{full} USDC</em> if the season comes in at 40% of normal. {pay}",
      {station:esc(s.name), km:f0.format(Math.round(flow.stationKm)), place:esc(subjectLabel()),
       mm:fLevel.format(.8*s.normal), season:esc(t(s.season)), full:money(l), pay:payClause()});
  }
  // The two ends, named the way the rest of the step names them. This read
  // ROUTES[flow.subject], and could not ever hit: the subject of a flight is
  // "IST-GZT" while that table is keyed "TK-IST-LHR", and the table only holds
  // six routes in any case. So the lookup was undefined and this line threw on
  // every flight policy -- and renderPrice stops where it throws, which left
  // the sentence, the chart, the table, the company and the contract all
  // showing the policy before this one, with the summary beside them showing
  // this one. The page the buyer signs on cannot be pieced together from two
  // different policies.
  return t("If your flight from {from} to {to} arrives <b>more than two hours late</b>, you receive <em>{first} USDC</em>, rising to <em>{full}</em> if it is cancelled. {pay}",
    {from:esc(flow.flightFromText||flow.flightFrom||""),
     to:esc(flow.flightToText||flow.flightTo||""),
     first:money(.30*l), full:money(l), pay:payClause()});
}
function payRows(){
  var c=structure(),l=flow.limit,rows=[];
  if(flow.peril==="quake"&&shakingIndex()){
    /* The steps this contract is written on, not the round numbers they sit
       near. An older building pays at a lower shaking than a new one, and the
       policy carries that: in Istanbul the first step is 6.25, in New York
       6.62. This table read the curve at VI, VII and VIII instead, so it said
       intensity VI pays nothing -- true of 6.0 and false of the policy, whose
       first step is below 6.5 -- and that intensity VII pays 35 per cent,
       which is the first step's share at the second step's name. The car and
       storm rows below have always been built from the curve's own points;
       this one now is too. */
    var qp=c.pts;
    rows.push([t("Shaking below intensity {level}",{level:fLevel.format(qp[0][0])}),0,null]);
    rows.push([t("Intensity {level} or more: strong, light damage",{level:fLevel.format(qp[0][0])}),shareAt(c,qp[0][0])*l,qp[0][0]]);
    rows.push([t("Intensity {level} or more: very strong, damage to ordinary buildings",{level:fLevel.format(qp[1][0])}),shareAt(c,qp[1][0])*l,qp[1][0]]);
    rows.push([t("Intensity {level} or more: severe",{level:fLevel.format(qp[2][0])}),l,qp[2][0]]);
  } else if(flow.peril==="quake"){
    /* The same fix the shaking rows above were given, which this branch never
       got. A quake policy's steps move with the building: structure() shifts
       the curve by the age of what is insured, for the magnitude index as
       well, so a flat built in 1975 in Türkiye pays from 5.2 and not from
       5.5. These four rows named 5.5, 6.5 and 7.0 whatever the policy said,
       and read the curve at those levels too, so the chance column was
       answered at a level the contract does not use either.

       Driven on the live site for a 1975 building: the ladder read "A
       magnitude 5.5 to 6.5, 8,574 USDC" while the summary row two inches
       above it read "M5.2 8,574", the same money at a different level, on the
       same screen. The summary was right. The first row was worse than
       inconsistent: "Nothing above magnitude 5.5 happens, nothing" is false
       when a 5.3 pays 8,574. */
    var mp=c.pts;
    rows.push([t("A magnitude below {level}",{level:fLevel.format(mp[0][0])}),0,null]);
    rows.push([t("A magnitude {from} to {to}",{from:fLevel.format(mp[0][0]),to:fLevel.format(mp[1][0])}),
               shareAt(c,mp[0][0])*l,mp[0][0]]);
    rows.push([t("A magnitude {from} to {to}",{from:fLevel.format(mp[1][0]),to:fLevel.format(mp[2][0])}),
               shareAt(c,mp[1][0])*l,mp[1][0]]);
    rows.push([t("A magnitude {level} or more",{level:fLevel.format(mp[2][0])}),l,mp[2][0]]);
  } else if(flow.peril==="car"){
    var cp=c.pts;
    rows.push([t("Less than {mm} mm in a day",{mm:f1.format(cp[0][0])}),0]);
    rows.push([t("{mm} mm or more in a day",{mm:f1.format(cp[0][0])}),shareAt(c,cp[0][0])*l]);
    rows.push([t("{mm} mm or more in a day",{mm:f1.format(cp[1][0])}),shareAt(c,cp[1][0])*l]);
    rows.push([t("{mm} mm or more in a day",{mm:f1.format(cp[2][0])}),l]);
  } else if(flow.peril==="storm"){
    var sp=c.pts;
    rows.push([t("Less than {kmh} km/h in a day",{kmh:fLevel.format(sp[0][0])}),0]);
    rows.push([t("{kmh} km/h or more in a day",{kmh:fLevel.format(sp[0][0])}),shareAt(c,sp[0][0])*l]);
    rows.push([t("{kmh} km/h or more in a day",{kmh:fLevel.format(sp[1][0])}),shareAt(c,sp[1][0])*l]);
    rows.push([t("{kmh} km/h or more in a day",{kmh:fLevel.format(sp[2][0])}),l]);
  } else if(flow.peril==="drought"){
    var s=stationFor();
    rows.push([t("A normal season, at or above {mm} mm",{mm:fLevel.format(.8*s.normal)}),0]);
    [.7,.6,.5,.4].forEach(function(f){
      rows.push([t("The season comes in at {share}% of normal ({mm} mm)",
        {share:Math.round(f*100),mm:fLevel.format(f*s.normal)}),shareAt(c,f*s.normal)*l]);
    });
  } else {
    rows.push([t("On time, or under two hours late"),0]);
    rows.push([t("Between two and four hours late"),shareAt(c,120)*l]);
    rows.push([t("More than four hours late"),shareAt(c,240)*l]);
    rows.push([t("Cancelled"),l]);
  }
  // How often the level in each row happens at this place, from the same
  // exceedance curve the price is made of. It is the answer to the question
  // the ladder raises and never answered: why this much at this level. The
  // table that said it was folded inside "show how this price was worked
  // out", closed, which is the one place a buyer deciding will not look.
  var exc=null;
  try{ exc=exceedance(); }catch(err){ exc=null; }
  /* Each step carries the share of the limit it pays, as a number between 0
     and 1, so the ladder can be drawn as steps rather than read as a table.
     On a wide screen the rows were already indented into a staircase; at 390px
     the indent went and four rows sat flush left, which is a list. The share
     is the thing that differs between them, so it is the thing the drawing
     should carry, at either width.

     "In the recorded earthquakes since 1973" was on every row, four times, and
     at 390px it wrapped to two lines every time: twelve lines of the same six
     words on the screen where the buyer decides. It is said once, under the
     ladder. */
  var top=0;
  rows.forEach(function(r){ if(r[1]>top)top=r[1]; });
  var said=false;
  var body=rows.map(function(r){
    var often="";
    if(exc&&r[2]!=null){
      var chance=exc(r[2]);
      if(chance>0&&chance<1){
        often='<span class="fine often">'+esc(t("about 1 in {n} years",
          {n:f0.format(Math.round(1/chance))}))+'</span>';
        said=true;
      }
    }
    var share=top>0?(r[1]||0)/top:0;
    return '<div class="pay-row'+(r[1]?"":" none")+'" data-share="'+share.toFixed(4)+'"'+
      ' style="--share:'+share.toFixed(4)+'">'+
      '<span class="step" aria-hidden="true"></span>'+
      '<span>'+esc(r[0])+often+'</span><span class="amt">'+
      (r[1]?money(r[1])+" USDC":esc(t("nothing")))+'</span></div>';
  }).join("");
  return body + (said
    ? '<p class="fine pay-since">'+esc(t("How often, in the earthquakes recorded since 1973."))+'</p>'
    : "");
}
function hazardRows(){
  var exc=exceedance(),c=structure();
  var rows='<tr><th>'+esc(t("If the index reaches"))+'</th><th>'+esc(t("How often"))+'</th><th>'+esc(t("You receive"))+'</th></tr>';
  if(flow.peril==="quake"){
    /* The policy's own steps, as the rain and wind tables below already do.

       This sampled six magnitudes from 5.0 to 7.5 whichever index the policy
       was written on. Read on the live site for the default cover, which is
       shaking at the address with steps at 6.9, 7.9 and 8.9: four rows said
       "-", the two that paid both said 17,242, the two upper steps were past
       the end of the grid and never appeared at all, and every row was
       labelled M, which is the notation for a magnitude and not for an
       intensity. A table headed "how this price was worked out" showed one
       of the three amounts it is made of.

       rungWords writes each level the way its own index writes it, MMI 6.9
       or M5.2, and it is the same call the summary row uses. */
    c.pts.forEach(function(pt){
      var p=exc(pt[0]);
      rows+='<tr><td>'+esc(rungWords(pt[0]))+'</td><td>'+esc(p<=0?t("never"):t("1 in {n} years",{n:f0.format(Math.round(1/p))}))+
            '</td><td>'+money(pt[1]*flow.limit)+'</td></tr>';
    });
  } else if(flow.peril==="car"){
    c.pts.forEach(function(pt){
      var p=exc(pt[0]);
      rows+='<tr><td>'+f1.format(pt[0])+' mm</td><td>'+esc(p<=0?t("never"):t("1 in {n} years",{n:f0.format(Math.round(1/p))}))+
            '</td><td>'+money(pt[1]*flow.limit)+'</td></tr>';
    });
  } else if(flow.peril==="storm"){
    c.pts.forEach(function(pt){
      var p=exc(pt[0]);
      rows+='<tr><td>'+fLevel.format(pt[0])+' km/h</td><td>'+esc(p<=0?t("never"):t("1 in {n} years",{n:f0.format(Math.round(1/p))}))+
            '</td><td>'+money(pt[1]*flow.limit)+'</td></tr>';
    });
  } else if(flow.peril==="drought"){
    var s=stationFor();
    [.8,.7,.6,.5,.4].forEach(function(f){
      var mm=f*s.normal,p=exc(mm),sh=shareAt(c,mm);
      rows+='<tr><td>'+fLevel.format(mm)+' mm</td><td>'+esc(p<=0?t("never"):t("1 in {n} seasons",{n:f1.format(1/p)}))+
            '</td><td>'+(sh?money(sh*flow.limit):"–")+'</td></tr>';
    });
  } else {
    [[60,t("1 hour late")],[120,t("2 hours late")],[240,t("4 hours late")],[1440,t("Cancelled")]].forEach(function(r){
      var p=exc(r[0]),sh=shareAt(c,r[0]);
      rows+='<tr><td>'+esc(r[1])+'</td><td>'+esc(t("{share} of flights",{share:pct(p,1)}))+'</td><td>'+(sh?money(sh*flow.limit):"–")+'</td></tr>';
    });
  }
  return rows;
}
function reference(){
  /* The protocol's own, where it has answered. Every address below names a
     .example host, which is the demonstration's reserved domain and is
     deliberately unresolvable; the reference a policy actually carries names
     the agency -- earthquake.usgs.gov, archive-api.open-meteo.com -- and the
     quote has been returning it all along under data_source. Printing the
     demonstration's address under "what the chain is actually asked to hold"
     told a buyer the cover reads a source that does not exist. The invented
     ones stay as the answer before the protocol has answered. */
  var q=flow.quoted&&flow.quotedFor===quoteKey()&&flow.quoted.data_source;
  if(q&&q.reference)return q.reference;
  if(flow.peril==="quake"){
    var at=coordinates();
    return "api.seismic.example/v1/max-magnitude?lat="+(+at.latitude)+"&lon="+(+at.longitude)+
           "&radius_km="+flow.radius;
  }
  if(flow.peril==="drought")
    return "api.meteo.example/v1/station/"+nearestStation(coordinates())+"/cumulative";
  if(flow.peril==="car"){
    var ca=coordinates();
    return "api.rain.example/v1/daily-max?lat="+(+ca.latitude)+"&lon="+(+ca.longitude);
  }
  if(flow.peril==="storm"){
    var sa=coordinates();
    return "api.wind.example/v1/daily-max?lat="+(+sa.latitude)+"&lon="+(+sa.longitude);
  }
  flightDefaults(); return "api.flightstatus.example/v1/"+flow.subject+"/"+flow.flightDate;
}

function predicateHtml(){
  // What the chain is actually asked to hold. On Rialo a subscription names a
  // topic and the instructions to run when it fires, so the reading is the
  // topic and the comparison is what the settlement instruction checks.
  var ref=esc(reference()),body, T=esc(t("topic")), W=esc(t("settles when"));
  if(flow.peril==="quake"){
    /* The field and the level this policy's own curve is written on. Both were
       written in: max_magnitude and 5.5, for both indices, under the heading
       "what the chain is actually asked to hold". For a 1975 Istanbul flat on
       the shaking index the chain is asked to hold
       edge("...?index=mmi&...").mmi >= 6.25 -- a different field, a different
       level, and a different topic. The three rows below it have always been
       built from the curve; this one now is too. */
    var qf=shakingIndex()?"mmi":"max_magnitude";
    body='<b>'+T+'</b> <em>'+ref+'</em> · '+qf+'<br>'+
         '<b>'+W+'</b> '+qf+' &gt;= '+structure().pts[0][0].toFixed(2);
  } else if(flow.peril==="car"){
    body='<b>'+T+'</b> <em>'+ref+'</em> · rain_24h_mm<br>'+
         '<b>'+W+'</b> rain_24h_mm &gt;= '+structure().pts[0][0].toFixed(1);
  } else if(flow.peril==="storm"){
    body='<b>'+T+'</b> <em>'+ref+'</em> · wind_24h_kmh<br>'+
         '<b>'+W+'</b> wind_24h_kmh &gt;= '+structure().pts[0][0].toFixed(1);
  } else if(flow.peril==="drought"){
    var s=stationFor();
    body='<b>'+T+'</b> <em>'+ref+'</em> · rainfall_mm<br>'+
         '<b>'+W+'</b> window_closed &gt;= 1 <b>'+esc(t("and"))+'</b> rainfall_mm &lt;= '+(.8*s.normal).toFixed(1);
  } else {
    body='<b>'+T+'</b> <em>'+ref+'</em> · arrival_delay_minutes<br>'+
         '<b>'+W+'</b> arrival_delay_minutes &gt;= 120';
  }
  return body+'<br><b>'+esc(t("kind"))+'</b> OneShot · <b>'+esc(t("holder"))+'</b> '+
         esc(identity.address?short(identity.address):t("the address you sign with"));
}

function short(address){
  return String(address).slice(0,6)+"…"+String(address).slice(-4);
}

function markPressed(container,selector,match){
  Array.prototype.forEach.call(container.querySelectorAll(selector),function(node){
    node.setAttribute("aria-pressed",String(match(node)));
  });
}


/* ---- the payout curve ----
   One series, so the title names it and no legend box is needed. The steps are
   direct laballed rather than given a value axis full of numbers, because what
   the reader wants is the amount at each band, not a ruler. */
var ROMAN={5:"V",6:"VI",7:"VII",8:"VIII",9:"IX"};
/* What the numbers on the chart are measured on, where that is not what a
   reader will assume. Only the two perils read from a reanalysis need it; the
   magnitude of an earthquake and the minutes a flight is late are the same
   figure everywhere. */
function scaleSaid(){
  if(flow.peril==="car")
    return t("These millimetres are the average over a grid cell of about fifty kilometres, not a reading from a rain gauge in your street: a gauge would show more on the same day. The trigger is set on the same figures the policy settles on, so the two agree.");
  if(flow.peril==="storm")
    return t("These wind speeds are the strongest hour's mean over a grid cell of about fifty kilometres, not the gust a weather station records: a station would show more on the same day. The trigger is set on the same figures the policy settles on, so the two agree.");
  return "";
}
function drawCurve(){
  var svg=$("curve"); if(!svg)return;
  var W=540,H=272,L=58,R=20,T=34,B=50;
  var iw=W-L-R, ih=H-T-B, c=structure(), exc=exceedance(), l=flow.limit;
  var x0,x1,xlabel,ticks,note;
  if(flow.peril==="quake"){
    x0=4.5;x1=7.5;xlabel=t("EARTHQUAKE MAGNITUDE");ticks=[5,5.5,6,6.5,7,7.5];
    if(shakingIndex()){ x0=5;x1=9;xlabel=t("SHAKING AT THE ADDRESS (MMI)");ticks=[5,6,7,8,9]; }
    note=t("The step at {level} is your trigger. Nothing below it pays, and the payout does not grow smoothly: it steps, which is what makes settlement a yes or no a validator can check.",
      {level:fLevel.format(structure().pts[0][0])});
    /* The policy's own first step, not the numeral six.

       A roman numeral is a whole number and these steps are not: an older
       building pays at less shaking, so the first step sits at 6.9 for this
       flat and at 6.25 in Istanbul and 6.62 in New York. This sentence named
       VI whatever the policy said, so it sat under a ladder whose first
       paying row read "Intensity 6.9 or more" and told the buyer their
       trigger was a different, lower level. rungWords was written to avoid
       exactly this and payRows was fixed for it; this was the last place
       still carrying it.

       It says intensity rather than MMI because the ladder immediately above
       it says intensity, and one screen should call a thing one name. The
       unit is named where naming it is the point: in the sentence about what
       the cover does not pay for, and in the contract. */
    if(shakingIndex()) note=t("The step at intensity {level} is your trigger. Each step up pays more, so a reading just short of one level still pays the level below.",
      {level:fLevel.format(structure().pts[0][0])});
  } else if(flow.peril==="car"){
    var cps=structure().pts;
    x0=Math.max(0,Math.floor(cps[0][0]*0.6/10)*10); x1=Math.ceil(cps[2][0]*1.2/10)*10;
    xlabel=t("RAIN IN ONE DAY, MM");
    ticks=[x0,Math.round(cps[0][0]),Math.round(cps[1][0]),Math.round(cps[2][0]),x1];
    note=t("Steps at this place's own once in ten, twenty five and fifty years levels, so a wet coast and a dry plateau each pay on what is extreme for them. That is also why the price is about the same in Rize as in Konya: what changes between them is how many millimetres it takes, not how often it happens.");
  } else if(flow.peril==="storm"){
    var sps=structure().pts;
    x0=Math.max(0,Math.floor(sps[0][0]*0.6/10)*10); x1=Math.ceil(sps[2][0]*1.2/10)*10;
    xlabel=t("WIND IN ONE DAY, KM/H");
    ticks=[x0,Math.round(sps[0][0]),Math.round(sps[1][0]),Math.round(sps[2][0]),x1];
    note=t("Steps at this place's own once in twenty five, fifty and a hundred years levels, so an exposed coast and a sheltered valley each pay on what is extreme for them. That is also why the price barely moves between two places: what changes is the wind it takes, not how often it comes.");
  } else if(flow.peril==="drought"){
    var st=stationFor();
    x0=Math.round(st.normal*.30);x1=Math.round(st.normal*1.05);
    xlabel=t("SEASON RAINFALL, MM");
    ticks=[x0,Math.round(st.normal*.5),Math.round(st.normal*.7),Math.round(st.normal*.9),x1];
    note=t("Reading right to left, as the season dries out. Payment starts at 80% of the station's normal and reaches the full amount at 40%, rising smoothly rather than in steps.");
  } else {
    x0=0;x1=300;xlabel=t("ARRIVAL DELAY, MINUTES");ticks=[0,60,120,180,240,300];
    note=t("Two steps: two hours late, then four. A cancelled flight settles at the top of the scale and pays the full amount.");
  }
  function sx(v){return L+(v-x0)/(x1-x0)*iw;}
  function sy(v){return T+ih-(v/l)*ih;}

  var out="",i;
  // recessive grid and the value ticks that the curve actually reaches
  var yvals=[0];
  c.pts.forEach(function(pt){ if(pt[1]>0) yvals.push(pt[1]*l); });
  yvals.forEach(function(v){
    out+='<line class="a-edge-soft" x1="'+L+'" y1="'+sy(v).toFixed(1)+'" x2="'+(L+iw)+'" y2="'+sy(v).toFixed(1)+'" stroke-width="1"/>';
    out+='<text x="'+(L-9)+'" y="'+(sy(v)+3.5).toFixed(1)+'" font-size="9.5" text-anchor="end">'+(v?money(v):"0")+'</text>';
  });
  ticks.forEach(function(tick){
    out+='<text x="'+sx(tick).toFixed(1)+'" y="'+(T+ih+17)+'" font-size="9.5" text-anchor="middle">'+
         (flow.peril==="quake"?(shakingIndex()?ROMAN[tick]||tick:"M"+tick.toFixed(1)):f0.format(tick))+'</text>';
  });
  out+='<text x="'+L+'" y="'+(T+ih+34)+'" font-size="8.5" letter-spacing="1.3">'+esc(xlabel)+'</text>';

  // the curve, sampled densely so a step reads as a step
  var N=460,d="",area="",first=true;
  for(i=0;i<=N;i++){
    var xv=x0+(x1-x0)*i/N, yv=shareAt(c,xv)*l;
    d+=(first?"M":"L")+sx(xv).toFixed(1)+" "+sy(yv).toFixed(1);
    first=false;
  }
  area=d+"L"+sx(x1).toFixed(1)+" "+sy(0).toFixed(1)+"L"+sx(x0).toFixed(1)+" "+sy(0).toFixed(1)+"Z";
  out+='<path class="a-settled-w" d="'+area+'"/>';
  out+='<path class="a-settled" stroke-width="2" stroke-linejoin="round" d="'+d+'"/>';

  // your trigger
  var trig=(flow.peril==="drought")?c.pts[0][0]:c.pts[0][0];
  if(trig>=x0&&trig<=x1){
    out+='<line class="a-signal a-dash" x1="'+sx(trig).toFixed(1)+'" y1="'+T+'" x2="'+sx(trig).toFixed(1)+'" y2="'+(T+ih)+'" stroke-width="1.2"/>';
    out+='<text x="'+(sx(trig)+6).toFixed(1)+'" y="'+(T+11)+'" font-size="9" class="t-2">'+esc(t("YOUR TRIGGER"))+'</text>';
  }
  // direct labels on the bands the policy actually pays
  c.pts.forEach(function(pt){
    if(pt[1]<=0)return;
    var xv=pt[0], yv=pt[1]*l;
    if(xv<x0||xv>x1)return;
    var anchor=(sx(xv)>L+iw-70)?"end":"start";
    var dx=anchor==="end"?-8:8;
    // a point near the top gets its label underneath, so it never lands on the title
    var ly=(sy(yv)-T<18)?sy(yv)+17:sy(yv)-9;
    out+='<circle class="a-settled-f" cx="'+sx(xv).toFixed(1)+'" cy="'+sy(yv).toFixed(1)+'" r="3.6"/>';
    out+='<circle cx="'+sx(xv).toFixed(1)+'" cy="'+sy(yv).toFixed(1)+'" r="5.6" fill="none" stroke="var(--panel)" stroke-width="2"/>';
    out+='<circle class="a-settled-f" cx="'+sx(xv).toFixed(1)+'" cy="'+sy(yv).toFixed(1)+'" r="3.6"><title>'+
         esc(money(yv))+' USDC</title></circle>';
    out+='<text x="'+(sx(xv)+dx).toFixed(1)+'" y="'+ly.toFixed(1)+'" font-size="10" text-anchor="'+anchor+'" class="t-ink">'+
         esc(money(yv))+'</text>';
  });
  if(flow.peril==="flight"){
    out+='<text x="'+(L+iw)+'" y="'+(T+13)+'" font-size="9" text-anchor="end" class="t-2">'+esc(t("CANCELLED: {amount}",{amount:money(l)}))+'</text>';
  }
  out+='<text x="'+L+'" y="15" font-size="10.5" class="t-ink">'+esc(t("What this policy pays, at every level of the index"))+'</text>';
  svg.innerHTML=out;
  svg.setAttribute("aria-label",t("What this policy pays at every level of the index, from nothing below the trigger up to {amount} USDC",{amount:money(l)}));
  // The millimetres and the kilometres an hour on this chart are grid cell
  // averages from a reanalysis, and a person reads them against a rain gauge
  // or a weather report. Said here, beside the figure, rather than left in the
  // basis risk paragraph: 53 mm in Rize is an ordinary wet day on a gauge and
  // a once in ten years day on this scale, and a buyer who does not know that
  // will expect to be paid several times a year.
  // The note says why the payout steps and where the trigger sits; that
  // belongs beside the ladder, which shows the steps and not the reason. The
  // scale caveat says the millimetres are a fifty kilometre average, which is
  // basis risk in one sentence, so it goes to the part that names it. The
  // figure keeps no caption: everything it said is now said where it is read,
  // and repeating it under the drawing is how this screen came to hold two of
  // everything in the first place.
  var payNote=$("pay-note"); if(payNote)payNote.textContent=note;
  var scaleBox=$("basis-scale"); if(scaleBox)scaleBox.textContent=scaleSaid();
  $("curve-cap").textContent="";
}

function renderStep(){
  stepsBar();
  STEPS.forEach(function(id,i){$(id).hidden=flow.step!==i+1;});

  if(flow.step===1){
    $("s1-picks").innerHTML=$("home-picks").innerHTML;
    // Copied from the home page, where they rise into view; here they are simply there.
    Array.prototype.forEach.call($("s1-picks").querySelectorAll(".reveal"),function(e){ e.classList.remove("reveal","in"); e.style.removeProperty("--i"); });
    markPressed($("s1-picks"),".pick",function(n){return flow.chosen&&n.dataset.peril===flow.peril;});
    Array.prototype.forEach.call($("s1-picks").querySelectorAll(".pick"),function(b){
      b.addEventListener("click",function(){choosePeril(b.dataset.peril);});
    });
  }
  if(flow.step===2){
    $("s2-title").textContent=t(PERILS[flow.peril].where);
    $("s2-hint").textContent=t(PERILS[flow.peril].hint);
    renderAssetChips(); if(identity.token)loadAssets().then(function(){ if(flow.step===2)renderAssetChips(); });
    $("s2-search").hidden = flow.peril==="flight";
    if(!$("s2-search").hidden && !$("place").value && flow.place){
      $("place").value = flow.place;
    }
    renderResults($("place").value);
    renderRadius();
    var byAddress=flow.peril==="quake"||flow.peril==="car"||flow.peril==="storm";
    $("s2-locate").hidden=!byAddress;
    $("where-map").hidden=!byAddress; $("map-note").hidden=!byAddress;
    if(byAddress){
      showMap();
      // Asked once, when the question is where: the phone knows the answer.
      // The browser's location prompt waits for the person to press "Use my
      // location": a prompt with no gesture behind it is refused by browsers
      // and unwelcome to people.
      if(!flow.subject&&!flow.askedWhere){ flow.askedWhere=true; }
    }
  }
  if(flow.step===AMOUNT_STEP){
    clampLimit();
    $("s3-hint").textContent = flow.peril==="quake"
      ? t("This is the most the policy can pay you. What it would cost to rebuild is the usual guide.")
      : flow.peril==="drought" ? t("A season's income is the usual guide.")
      : flow.peril==="car" ? t("What the car is worth is the most it can carry.")
      : flow.peril==="storm" ? t("This is the most the policy can pay you. What it would cost to make the home weathertight again is the usual guide.")
      : t("Enough for a hotel, a meal and a missed connection is the usual guide.");
    $("cover-range").value=sliderFromLimit(flow.limit);
    $("cover-presets").innerHTML=coverPresets().map(function(v){
      return '<button type="button" data-v="'+v+'" aria-pressed="false">'+f0.format(v)+'</button>';
    }).join("");
    Array.prototype.forEach.call($("cover-presets").querySelectorAll("button"),function(b){
      b.addEventListener("click",function(){
        flow.limit=+b.dataset.v;
        $("cover-range").value=sliderFromLimit(flow.limit);
        renderAmount(); updatePriceBar();
      });
    });
    renderAmount();
  }
  if(flow.step===RISK_STEP){
    renderInterest();
    loadCoverage(true).then(function(){ if(flow.step===RISK_STEP)renderInterest(); });
  }
  if(flow.step===CONFIRM_STEP){
    // A quote whose price lock is still running is kept: a language change
    // or a redraw must not throw away the price the buyer was promised.
    var lockLive=flow.quoted&&flow.quoted.lock&&flow.quoted.lock.expires_at-Date.now()/1000>0;
    // The quote starts before the panel is drawn, so the contract the panel
    // asks for waits for the protocol's price instead of pricing on its own.
    if(!lockLive)refreshQuote(); renderPrice(); refreshNeed();
    loadCoverage(true).then(function(){
      if(flow.step===CONFIRM_STEP){ renderPrice(); setNextLabel(); }
    });
  }

  $("pricebar").hidden=flow.step>CONFIRM_STEP;
  $("back").hidden=flow.step===1;
  setNextLabel();
  updatePriceBar();
}

/* What is standing between the reader and the next question, named.

   The confirm step has always said what was left to do -- "Read and accept
   the contract", "Verify the items above". The four questions before it said
   nothing: the button simply went grey, and on the third question, with the
   floor area the only box left empty and a scroll away, nothing on the screen
   said which box was wanted. Baymard's testing and NN/g's guidelines reach the
   same place from different methods: a disabled button with no reason is a
   dead end, because the reader cannot tell what to fix.

   Each answer carries the thing it is about, so pressing the button that is
   not ready takes the reader to it instead of doing nothing. */
function whatIsMissing(){
  var it=flow.interest;
  if(flow.step===1)return flow.chosen?null:{say:t("Choose what to protect"),at:"s1-picks"};
  if(flow.step===2){
    if(flow.peril==="flight"){
      // Each end named separately, because "choose a place" is no help when
      // what is missing is the airport it lands at.
      if(!flow.flightFrom)return {say:t("Choose the airport it leaves from"),at:"air-from"};
      if(!flow.flightTo)return {say:t("Choose the airport it lands at"),at:"air-to"};
      if(flow.flightFrom===flow.flightTo)return {say:t("Choose two different airports"),at:"air-to"};
      if(!flightReady())return {say:t("Enter the flight number and date"),at:"flight-no"};
      return null;
    }
    if(!flow.subject)return {say:t("Choose a place"),at:"place"};
    if(!flightReady())return {say:t("Enter the flight number and date"),at:"flight-no"};
    // A reading that came back refused is not a reading still coming. The
    // protocol says why -- "storm cover is written only within 60 km of a
    // Türkiye provincial centre, where the wind model is tested" -- and the
    // page prints that under the map. The button, which is where a buyer
    // looks to know what to do next, went on saying the place was still being
    // read, and never stopped, because one sentence covered both the wait and
    // the refusal. Only the wait ends on its own.
    if(flow.gridError||flow.stormError||flow.vehicleError)
      return {say:t("Choose another place"),at:"place"};
    if(!quakeReady()||!stormReady()||!carReady())return {say:t("Still reading the place"),at:""};
    return null;
  }
  if(flow.step===RISK_STEP){
    if(!it.what)return {say:t("Say what is at risk"),at:"what"};
    if(flow.peril==="car"){
      if(!(it.value>0))return {say:t("Enter what the car is worth"),at:"value"};
      if(!it.modelYear)return {say:t("Enter the model year"),at:"value"};
    }else if(flow.peril==="flight"){
      if(!(it.value>0))return {say:t("Enter what the trip is worth"),at:"value"};
    }else{
      var z=sizeState();
      if(!String(z.area).trim())return {say:flow.peril==="drought"?t("Enter the size of the field"):t("Enter the floor area"),at:"size-area"};
      if(z.kind==="home"&&!String(z.built).trim())return {say:t("Enter the year it was built"),at:"size-built"};
      if(!sizeOk())return {say:t("Check the size above"),at:"size-area"};
    }
    /* Whichever of the two is missing, and the field that is missing it.

       Choosing a place or pressing "use my location" fills the town, so by
       the time most readers meet this message the town is already there. It
       asked for it anyway, and sent the cursor to the street even when the
       street was the part that was filled. Measured on the live site after
       the locator answered: the button read "Sokağı ve şehri girin" with
       Küçükçekmece already in the town field. */
    if(!addressOk()){
      var a=flow.interest.address||{};
      var noStreet=!(a.street&&a.street.trim().length>=3);
      var noTown=!(a.city&&a.city.trim().length>=2);
      return {say: noStreet&&noTown ? t("Enter the street and the town")
                 : noStreet ? t("Enter the street")
                 : t("Enter the town"),
              at: noStreet ? "addr-street" : "addr-city"};
    }
    if(!it.inside)return {say:t("Confirm it is inside the area"),at:"inside"};
    // Last, because the ruling reads the answers above it: asked before they
    // exist it refuses everything, and "Cannot be written" was the first thing
    // an empty third question said.
    if(!localRuling().allowed)return {say:t("Cannot be written"),at:""};
    return null;
  }
  return null;
}
function setNextLabel(){
  if(flow.busy)return;
  var button=$("next");
  if(flow.step!==CONFIRM_STEP){
    var missing=whatIsMissing();
    button.disabled=false;
    button.setAttribute("aria-disabled", missing?"true":"false");
    button.textContent=missing?missing.say:t("Continue");
    return;
  }
  // Nothing below a redraw that did not finish is this policy, so there is
  // nothing here to agree to, whatever the rest of the gate would have said.
  if(flow.unshowable){
    button.disabled=true;
    button.setAttribute("aria-disabled","true");
    button.textContent=t("This cover cannot be shown");
    return;
  }
  var ruling=localRuling();
  var carried=!(flow.quoted&&flow.quoted.can_write===false);
  // The same test the bar and the panel use: an answer to a different question
  // is not an answer to this one, and while it is outstanding this says so.
  var priced=!link.live||!!(flow.quoted&&flow.quotedFor===quoteKey());
  var proved=verified();
  var accepted=!link.live||(CONTRACT.hash&&CONTRACT.key===contractKey()&&$("accept").checked);
  // Not yet accepted is not a dead end: the button is live and takes the
  // buyer to the contract, where the one thing left to do is. Nor is any of
  // the rest one, for the same reason — pressing it goes to what is missing.
  button.disabled=false;
  button.setAttribute("aria-disabled",
    (!ruling.allowed||!carried||!priced||!proved) ? "true" : "false");
  button.textContent=!ruling.allowed ? t("Cannot be written")
    : !carried ? t("The pool cannot carry this")
    : !priced ? priceSaid(t("Pricing…"))
    : !proved ? t("Verify the items above")
    : !accepted ? t("Read and accept the contract")
    : identity.token ? t("Sign and apply, paying {amount}",{amount:money(payableNow())})
                     : t("Sign in and apply, paying {amount}",{amount:money(payableNow())});
}

/* What stands where a price would be. The waiting word differs by place --
   a button says "Pricing…" and a sentence says "working out your price" --
   so the caller brings its own; what it must not do is decide on its own
   which of the three states it is in. */
function priceSaid(waiting){
  if(flow.refusal)return t("The protocol did not price this");
  if(flow.unreached)return t("Clause could not be reached");
  return waiting;
}
function payableNow(){
  // What leaves the account when this is signed: the whole price, or the
  // first instalment where one was chosen.
  var q=priced(), offer=chosenOffer(), total=q.premium+(offer?offer.fee:0);
  if(flow.instalments>1){
    var plan=(PLANS.plans||[]).filter(function(p){return p.count===flow.instalments;})[0]||{surcharge:0};
    return total*(1+plan.surcharge)/flow.instalments;
  }
  return total;
}

function setBusy(text){
  flow.busy=!!text;
  $("next").disabled=!!text;
  if(text)$("next").textContent=text; else setNextLabel();
}

/* ---- the confirm panel ----
   Drawn from priced(), which on this step is always the protocol's own figure:
   the panel is not drawn at all until the protocol has answered for exactly
   this policy. The page's own model still runs, and still answers the slider
   on the steps before this one, but it never reaches a page anybody signs. */
/* The confirm step opens with what was chosen, line by line, each with its
   way back (WCAG 3.3.4: a purchase can be reviewed and corrected before it
   is made). The peril's name is the card's own, so it reads the same here. */
function renderAnswers(){
  var box=$("answers-rows"); if(!box)return;
  var q=priced(), offer=chosenOffer(), days=PERILS[flow.peril].term, rows=[];
  function row(label,value,step,id){
    return '<div class="ans"><span class="k">'+esc(label)+'</span><span class="v">'+value+'</span>'+
      (step?'<button type="button" class="linkish ans-change" data-step="'+step+'"'+(id?' data-to="'+id+'"':'')+'>'+esc(t("Change"))+'</button>':'<span></span>')+'</div>';
  }
  var card=$("home-picks").querySelector('.pick[data-peril="'+flow.peril+'"] h3');
  rows.push(row(t("What"),esc(card?card.textContent:flow.peril),1));
  var it=flow.interest, ad=it.address, addr=ad?[ad.street,ad.number,ad.flat,ad.postcode,ad.city].filter(Boolean).join(" "):"";
  // Where, unless what is at risk already says where it is. A saved asset is
  // labelled with its own place -- "a flat in 222. Cadde, Atakent Mahallesi,
  // Kucukcekmece, Istanbul" -- so the summary was printing that address once
  // under Where and again, word for word, under At risk. Two rows, one fact.
  // The At risk row is the one that keeps it, because it also carries the
  // street address, and the row above it would have been the poorer of the two.
  var where=subjectLabel(), saidTwice=!!(it.what&&where&&it.what.indexOf(where)>=0);
  if(!saidTwice)rows.push(row(t("Where"),esc(where),2));
  if(it.what||addr)rows.push(row(t("At risk"),esc(it.what||"")+(addr?(it.what?"<br>":"")+'<small>'+esc(addr)+'</small>':""),RISK_STEP));
  if(it.value)rows.push(row(t("Declared at risk"),money(it.value)+" USDC",RISK_STEP));
  rows.push(row(t("How much"),esc(t("{cover} of cover for {days} days",{cover:f0.format(flow.limit),days:days})),AMOUNT_STEP));
  // What it pays at each reading, and the day it starts paying at all. Both
  // were things a buyer could only find by reading the contract or the chart,
  // and both decide whether the cover is the cover they think they are buying.
  rows.push(row(t("Pays"),esc(ladderSaid()),AMOUNT_STEP));
  var startsOn=coverStartsAt(), why=waitWhy();
  if(startsOn)rows.push(row(t("Cover starts"),
    esc(startsOn.toLocaleDateString(LANG))+(why?'<br><small>'+esc(why)+'</small>':""),0));
  if(offer)rows.push(row(t("Company"),esc(ts(offer.name)),CONFIRM_STEP,"offers-box"));
  // The same rule as everywhere else: this row carries a figure only when it
  // is the figure that will be charged.
  var settled=!link.live||!!(flow.quoted&&flow.quotedFor===quoteKey());
  var total=offer?q.premium+offer.fee:q.premium;
  var price=settled?money(total)+" USDC"
    :esc(priceSaid(t("working out your price")));
  if(settled&&offer&&offer.fee>0)price+=' <small>'+esc(t("includes the company's fee of {fee}",{fee:money(offer.fee)}))+'</small>';
  if(settled&&flow.instalments>1){ var pl=(PLANS.plans||[]).filter(function(p){return p.count===flow.instalments;})[0]||{surcharge:0};
    price+=' <small>'+esc(t("{n} payments of {amount}",{n:flow.instalments,amount:money(total*(1+pl.surcharge)/flow.instalments)}))+'</small>'; }
  rows.push(row(t("Price"),price,flow.instalments>1||($("plan-box")&&!$("plan-box").hidden)?CONFIRM_STEP:0,"plan-box"));
  box.innerHTML=rows.join("");
  // And what it does not cover, in the numbers on this policy. It was the
  // last row of this table, under a 10px uppercase label, which is the
  // typography of a field name and not of the one thing on this screen a
  // buyer is most likely to be wrong about. It has its own part now, and
  // reads as two sentences rather than a value in a column.
  var says=basisRiskSaid(), basis=$("basis-box");
  if(basis)basis.innerHTML='<p class="basis-cut">'+esc(says[0])+'</p>'+
    '<p class="basis-cut">'+esc(says[1])+'</p>';
  Array.prototype.forEach.call(box.querySelectorAll(".ans-change"),function(b){
    b.addEventListener("click",function(){
      var to=b.dataset.to, step=+b.dataset.step;
      if(step===CONFIRM_STEP&&to){
        if(to==="offers-box"){ flow.offersOpen=true; renderOffers(); }
        var target=$(to); if(target){ target.scrollIntoView({behavior:"smooth",block:"start"}); var f=target.querySelector("button,[tabindex]"); if(f)f.focus({preventScroll:true}); }
        return;
      }
      goStep(step); window.scrollTo({top:0,behavior:"smooth"});
      var h=$(STEPS[step-1])&&$(STEPS[step-1]).querySelector("h2"); if(h){ h.setAttribute("tabindex","-1"); h.focus({preventScroll:true}); }
    });
  });
}
/* The page a buyer signs on, drawn top to bottom from one policy.

   Drawn top to bottom, a redraw that stops halfway leaves everything below the
   stop showing the policy before this one. That is not a cosmetic state: a
   reader who moved from a home to a flight was shown an earthquake sentence,
   an earthquake payout table and an earthquake contract underneath a summary
   of their flight, and could not go on, because the contract on screen was not
   the contract the gate was hashing -- so the button asked them to accept a
   contract they had just accepted.

   Nothing below a redraw that did not finish belongs to this policy, so
   nothing below it is shown, and the purchase stops rather than leaving
   somebody to agree to terms that are not theirs. The fault still reaches the
   console, because a page that swallows its own errors is how this one stayed
   hidden. */
function renderPrice(){
  try{
    renderPriceBody();
  }catch(err){
    if(window.console&&console.error)console.error(err);
    confirmUnshowable();
  }
}
function confirmUnshowable(){
  // A flag rather than a disabled button: the button's state is written by
  // setNextLabel, which half a dozen other things call, so disabling it here
  // lasts only until the next of them runs. The gate has to know.
  flow.unshowable=true;
  partsWaiting(false);
  var blanks=["plain","pay-rows","market-box","offers","contract-text","curve","basis-box"];
  for(var i=0;i<blanks.length;i++){ var el=$(blanks[i]); if(el)el.innerHTML=""; }
  var cap=$("curve-cap"); if(cap)cap.textContent="";
  ["pay-note","basis-scale"].forEach(function(id){ var e=$(id); if(e)e.textContent=""; });
  var said=$("confirm-broken");
  if(said){ said.hidden=false; said.textContent=t("This cover cannot be shown, so it cannot be bought. Go back a step and choose again; nothing has been charged."); }
  var button=$("next");
  if(button){ button.disabled=true; button.setAttribute("aria-disabled","true");
              button.textContent=t("This cover cannot be shown"); }
}
/* The confirm step with nothing to confirm yet. Every figure below is drawn
   from a price, and this page's own price is not the one that will be charged,
   so while the protocol is still answering none of them is drawn: the step
   says it is waiting, the button says it too, and renderPrice comes back here
   the moment the answer lands. */
/* What the step shows while the protocol is still answering.

   Six headings over six empty parts, each with a rule above it, reads as a
   page that failed to load rather than one that is working. Each part carries
   a slot the shape of what will land in it -- four steps of a ladder, two
   sentences of basis risk, three lines of a company card -- so the wait shows
   the document arriving rather than an outline of one that never did. Part
   one says in words what is happening, because a shape cannot say "working
   out your price", and the parts below it are shapes, because five more lines
   of the same sentence would say nothing five more times. */
function partFilled(part){
  // Anything in the part that is not its heading and not the waiting shape.
  return Array.prototype.some.call(part.children,function(child){
    // A disclosure is a control, not content: the curve's summary line is the
    // same height whether the drawing behind it has been made or not.
    if(child.tagName==="DETAILS")return false;
    if(child.classList.contains("part-t")||child.classList.contains("part-wait"))return false;
    if(child.hidden||getComputedStyle(child).display==="none")return false;
    // Asked of the box, not of its geometry. The empty ladder is 8px tall
    // because .pay-rows carries 4px of padding either side, so a height test
    // called it full and the payout part, alone of the six, never showed what
    // it was waiting for. What is being asked is whether there is anything in
    // it, and that is a question about its contents.
    return child.childElementCount>0||child.textContent.trim()!=="";
  });
}
function partsWaiting(waiting){
  Array.prototype.forEach.call(document.querySelectorAll("#s4 .part"),function(part){
    var slot=part.querySelector(".part-wait"); if(!slot)return;
    // Not every part waits for the price. The screening panel is drawn from
    // who the buyer is and lands seconds before the protocol answers, so this
    // one measured a heading, three grey bars and the real panel underneath
    // them, at once, for the rest of the wait. A part that already has
    // something to show never shows a shape instead.
    var show=waiting&&!partFilled(part);
    slot.hidden=!show;
    slot.innerHTML=show?skeleton(+slot.dataset.bars||3):"";
    if(!show)return;
    // And it stops the moment its own content lands, rather than at the moment
    // the price does: the two are not the same moment for every part.
    if(slot.watching)return;
    slot.watching=new MutationObserver(function(){
      if(!slot.hidden&&partFilled(part)){ slot.hidden=true; slot.innerHTML=""; }
    });
    slot.watching.observe(part,{childList:true,subtree:true,attributes:true,
      attributeFilter:["hidden","style","class"]});
  });
}
function confirmPricing(){
  flow.unshowable=false;
  /* A silence gets the one thing a refusal cannot be offered: another go.
     It is said at the top of the step rather than in the verdict box lower
     down, because until the protocol answers there is nothing below it worth
     scrolling to, and because a buyer who has just been told the connection
     dropped should not have to find the button. */
  var said=$("confirm-broken");
  if(said&&flow.unreached){
    said.hidden=false;
    said.innerHTML='<b>'+esc(t("Clause could not be reached."))+'</b> '+
      esc(t("Nothing has been charged and nothing has been signed. The connection may have dropped, or the protocol may be busy."))+
      ' <button type="button" class="btn btn-line btn-sm" id="price-again">'+esc(t("Try again"))+'</button>';
    var again=$("price-again");
    if(again)again.addEventListener("click",function(){
      again.disabled=true; refreshQuote(); confirmPricing();
    });
  } else if(said)said.hidden=true;
  var blanks=["pay-rows","market-box","offers","contract-text","curve","basis-box"];
  for(var i=0;i<blanks.length;i++){ var el=$(blanks[i]); if(el)el.innerHTML=""; }
  var cap=$("curve-cap"); if(cap)cap.textContent="";
  ["pay-note","basis-scale"].forEach(function(id){ var e=$(id); if(e)e.textContent=""; });
  var plain=$("plain");
  if(plain)plain.innerHTML='<p class="prompt">'+
    esc(priceSaid(t("working out your price")))+'</p>';
  partsWaiting(!flow.unreached);
  CONTRACT={key:"",text:"",hash:""};
  if($("accept"))$("accept").checked=false;
  // What was chosen is still shown: it is what the buyer answered, not what
  // the protocol said, and it is the one thing on this step that is already
  // known. Its price row waits with everything else.
  renderAnswers();
  setNextLabel();
  updatePriceBar();
}
function renderPriceBody(){
  if(link.live&&!(flow.quoted&&flow.quotedFor===quoteKey())){ confirmPricing(); return; }
  flow.unshowable=false;
  partsWaiting(false);
  var said=$("confirm-broken"); if(said)said.hidden=true;
  var q=priced(),total=Math.max(q.premium,1e-9);
  renderAnswers();
  $("plain").innerHTML=plainSentence();
  $("pay-rows").innerHTML=payRows();
  $("bar-el").style.width=(q.el/total*100)+"%";
  $("bar-rl").style.width=(q.riskLoad/total*100)+"%";
  $("bar-ex").style.width=(q.expenses/total*100)+"%";
  $("k-el").textContent=money(q.el);
  $("k-rl").textContent=money(q.riskLoad);
  $("k-rl-name").textContent=q.basis==="reinsurance"?t("Reinsurance"):t("Cost of capital");
  $("market-box").innerHTML=marketHtml();
  renderOffers();
  renderCancelTerms();
  renderPlan();
  renderContract();
  $("k-ex").textContent=money(q.expenses);
  $("d-prob").textContent=t("{share} over the term",{share:pct(q.trigger,2)});
  $("d-cap").textContent=money(q.capital)+" USDC";
  $("d-src").textContent=sourceName();
  $("d-deadline").textContent=deadlineText();
  $("hazard").querySelector("tbody").innerHTML=hazardRows();
  $("pred").innerHTML=predicateHtml();
  $("agg-rule").textContent=ts((flow.quoted&&flow.quoted.aggregation_rule)||LOCAL_RULE);
  renderVerdict();
  renderVerify();
  drawCurve();
  setNextLabel();
  updatePriceBar();
}

/* ---- the gate ----
   Mirrors the protocol's compliance module, so a refusal can be shown with the
   sentence that caused it before anything is signed. The protocol runs the same
   rule again when the policy is bound, and once more before a payout leaves. */
function localRuling(){
  var code=riskCountry(), cover=coverFor(code), note=NOTES[code]||null;
  var name=countryName(code);
  function no(reason){
    return {allowed:false, cover:cover, note:note, name:name, asset:null,
            reasons:[reason]};
  }

  // The three tests no licence cures, in the order the protocol applies them.
  if(!flow.interest.inside)
    return no(t("What you are insuring is not inside the area this index measures, "+
      "so a payout would not answer a loss you could actually suffer. That is the "+
      "line between insurance and a wager, and it is the one line this protocol "+
      "will not cross for you."));
  if(!flow.interest.what)
    return no(t("Say what is at risk. Cover is capped by it."));
  if(flow.limit>flow.interest.value+1e-9)
    return no(t("Cover of {cover} exceeds the {value} you declared at risk. Cover above the value at risk is a wager rather than an indemnity, so it is refused rather than priced.",
      {cover:f0.format(flow.limit),value:f0.format(flow.interest.value)}));

  // Then the licensing question, which only the protocol can answer.
  if(!link.live)
    return {allowed:true, offline:true, cover:null, note:note, name:name,
            asset:"stablecoin", reasons:[
      t("This page cannot reach the protocol, so it cannot tell you whether a "+
      "company is licensed to issue this where you are. Nothing below is real.")]};

  var refusal=licensing(code);
  if(refusal) return no(refusal);

  var asset=cover.settlement.indexOf("stablecoin")>=0?"stablecoin":cover.settlement[0];
  return {allowed:true, cover:cover, note:note, name:name, asset:asset, reasons:[
    t("Issued in {country} by {carriers}, supervised by {authorities}, paid in {cash}.",
      {country:name,carriers:listText(cover.carriers.map(ts)),authorities:listText(cover.authorities.map(ts)),
       cash:cashName(code,asset)})]};
}

/* The licensing half of the ruling on its own, so the step that asks where
   you are can show it before the rest of the form is filled in. Null when a
   company may issue this here; otherwise the sentence saying why not. */
function licensing(code){
  var cover=coverFor(code), name=countryName(code), key=PERIL_KEYS[flow.peril];
  var waiting=(COVERAGE&&COVERAGE.__waiting&&COVERAGE.__waiting[code])||null;
  if(!cover&&waiting)
    return t("A company is licensed in {country}, but cover cannot be bought there yet: it is waiting on {missing}.",
      {country:name,missing:listText(waiting.waiting_on.map(ts))});
  if(!cover)
    return t("No licensed carrier is registered to write cover in {country} yet. That is a fact about this registry rather than about {country}: the day a licensed company registers for it, this page starts working there, and no code changes.",
      {country:name});
  if(cover.perils.indexOf(key)<0)
    return (cover.unpriced||[]).indexOf(key)>=0
      ? t("A company is licensed to write this in {country}, but this protocol has no model that can price it there yet. A licence to sell something nobody can price is not cover.",{country:name})
      : t("A carrier is registered in {country}, but not for this peril.",{country:name});
  if(!cover.retail&&!flow.interest.professional)
    return t("In {country} the registered company may write only for professional counterparties, as an index contract rather than consumer insurance.",{country:name});
  return null;
}

function cashName(code,asset){
  // The protocol keeps one unit of account. What actually moves in and out of a
  // buyer's hands is whatever the licence of whoever issues the policy permits,
  // which in Türkiye is lira and not a crypto asset.
  if(asset==="stablecoin")return "USDC";
  var note=NOTES[code];
  return t((note&&note.cash)||"local currency");
}

function verdictHtml(ruling, compact){
  var out="";
  out+='<div class="vrow"><span class="pill '+(ruling.allowed?"ok":"no")+'">'+
       esc(ruling.offline?t("Unverified"):ruling.allowed?t("May be written"):t("Refused"))+'</span>'+
       '<span>'+esc(ruling.name||"")+
       (ruling.cover?' · '+esc(listText(ruling.cover.authorities.map(ts))):"")+'</span></div>';
  // Allowed: the one line above says it; the law behind it is a click
  // away. Refused: every reason, in full, because the buyer is stopped.
  if(compact&&ruling.allowed){
    var rest="";
    ruling.reasons.forEach(function(reason){ rest+='<p>'+esc(reason)+'</p>'; });
    if(ruling.cover&&ruling.cover.specimen)rest+='<p>'+t("<b>The company named here is a stand in, not a company.</b> It "+
      "holds no licence, no regulator supervises it, and nothing written "+
      "against it is cover. This deployment is a demonstration of how the "+
      "protocol works, not a place to buy insurance.")+'</p>';
    if(ruling.cover){
      var ours2=ruling.cover.carriers.some(function(n){return /^Clause /.test(n);});
      rest+='<p><b>'+esc(ours2?t("The insurer is Clause's own licensed entity."):t("Clause is not the insurer."))+'</b> '+
        t("The policy is issued by {carriers}, supervised by {authorities}, and this pool stands behind it as capital. Every figure on this page is in the protocol's unit of account; your premium and any payout move in {cash}.",
          {carriers:esc(listText(ruling.cover.carriers.map(ts))),authorities:esc(listText(ruling.cover.authorities.map(ts))),
           cash:esc(cashName(riskCountry(),ruling.asset))})+'</p>';
    }
    if(ruling.note)rest+='<p class="fine">'+esc(t(ruling.note.note))+'</p>';
    return out+'<details class="more" style="margin-top:8px"><summary>'+esc(t("Why this can be written here, and by whom"))+'</summary><div class="inner">'+rest+'</div></details>';
  }
  ruling.reasons.forEach(function(reason){ out+='<p>'+esc(reason)+'</p>'; });

  if(ruling.allowed&&ruling.cover&&ruling.cover.specimen){
    out+='<p>'+t("<b>The company named here is a stand in, not a company.</b> It "+
      "holds no licence, no regulator supervises it, and nothing written "+
      "against it is cover. This deployment is a demonstration of how the "+
      "protocol works, not a place to buy insurance.")+'</p>';
  }
  if(ruling.allowed&&ruling.cover){
    var ours=ruling.cover.carriers.some(function(n){return /^Clause /.test(n);});
    out+='<p><b>'+esc(ours
      ? t("The insurer is Clause's own licensed entity.")
      : t("Clause is not the insurer."))+'</b> '+
      t("The policy is issued by {carriers}, supervised by {authorities}, and this pool stands behind it as capital. Every figure on this page is in the protocol's unit of account; your premium and any payout move in {cash}.",
        {carriers:esc(listText(ruling.cover.carriers.map(ts))),authorities:esc(listText(ruling.cover.authorities.map(ts))),
         cash:esc(cashName(riskCountry(),ruling.asset))})+'</p>';
  }
  if(ruling.note)out+='<p class="fine">'+esc(t(ruling.note.note))+'</p>';
  return out;
}

/* ---- what has to be proved ----
   Asked of the protocol rather than decided here, because the answer depends on
   the size of the cover and on where the buyer is, and because a page that
   invents its own identity requirements is a page nobody should trust with
   one. Small policies ask for almost nothing, which is the point. */

var CLAIM_NAMES={
  sanctions_clear:N("You are not on a sanctions list"),
  identity_basic:N("Somebody has checked who you are"),
  identity_enhanced:N("Checked to the enhanced standard"),
  professional:N("You are a professional counterparty"),
  residency:N("You live in the country issuing this"),
};
/* The same checks, named as something the insurer will do rather than has done. */
var CHECK_NAMES={
  sanctions_clear:N("Screening against sanctions lists"),
  identity_basic:N("Confirming who you are"),
  identity_enhanced:N("Confirming who you are, to the enhanced standard"),
  professional:N("Confirming you buy as a professional"),
  residency:N("Confirming where you live"),
  ownership:N("Confirming it is yours: title deed, lease or vehicle registration"),
};

function refreshNeed(){
  if(!link.live){ flow.need=null; renderVerify(); return; }
  var seq=flow.seq;
  api("/api/eligibility?limit="+encodeURIComponent(flow.limit)+
      "&country="+encodeURIComponent(flow.interest.country)+
      "&professional="+(flow.interest.professional?"true":"false"),
      {timeout:9000}).then(function(reply){
    if(seq!==flow.seq)return;
    flow.need=reply.requirement;
    flow.heldBy=reply.held_by_us;
    renderVerify();
  },function(){ if(seq===flow.seq){ flow.need=null; renderVerify(); } });
}

function renderVerify(){
  var box=$("verify-box");
  if(!flow.need||!link.live){ box.hidden=true; setNextLabel(); return; }
  box.hidden=false;

  $("verify-why").textContent=
    t("The company that issues this policy checks the following before it does, because an insurer may not knowingly cover a sanctioned person and, above a certain size, must know whose policy it issues. Until it has decided, nothing is written and your premium is held, not taken; if it says no, all of it comes back.",
      {cover:f0.format(flow.limit)});

  $("verify-rows").innerHTML=flow.need.claims.map(function(claim,i){
    return '<div class="vrule">'+
      '<span class="mark">'+(i+1)+'</span>'+
      '<span><span class="t">'+esc(t(CHECK_NAMES[claim]||claim))+'</span>'+
      '<span class="s">'+esc(ts(flow.need.because[i]||""))+'</span></span>'+
      '<span class="pill">'+esc(t("the insurer checks"))+'</span>'+
      '</div>';
  }).join("");

  $("verify-held").textContent=
    t("You will see the decision on your My cover page, with who decided and what they checked. The price you agree to now is the price if it is approved.");

  Array.prototype.forEach.call($("verify-rows").querySelectorAll("button"),function(b){
    b.addEventListener("click",function(){ getStatement(b.dataset.claim, b); });
  });
  setNextLabel();
}

function getStatement(claim,button){
  button.disabled=true; button.textContent="…";
  var work=identity.address?Promise.resolve():chooseSignIn("verify");
  work.then(function(){
    return api("/api/eligibility/demo",{method:"POST",body:{
      address:identity.address, purpose:claim,
      terms:claim==="residency"?{country:flow.interest.country}:null,
    }});
  }).then(function(reply){
    flow.statements[claim]=reply.attestation;
    flow.demoNote=reply.demonstration;
    renderVerify();
  },function(){
    button.disabled=false; button.textContent=t("Try again");
  });
}

function verified(){
  // The checks are the issuing company's, after the application; nothing has
  // to be fetched first.
  return true;
}

function renderVerdict(){
  var box=$("compliance-box"),ruling=localRuling();
  box.hidden=false;
  box.className="verdict "+(ruling.allowed?"ok":"no");
  box.innerHTML=verdictHtml(ruling,true);
  if(flow.quoted&&flow.quoted.can_write===false){
    box.className="verdict no";
    box.innerHTML+='<p><b>'+esc(t("The pool will not carry this."))+'</b> '+
      (flow.quoted.refusal_reasons||[]).map(tsHtml).join(" ")+'</p>';
  }
  if(link.live&&!flow.quoted&&flow.refusal){
    // The protocol answered with a refusal: shown, and nothing is signed on
    // a browser figure while the protocol is the one that decides.
    box.className="verdict no";
    box.innerHTML+='<p><b>'+esc(t("The protocol did not price this."))+'</b> '+tsHtml(String(flow.refusal))+'</p>';
  }
}


