/* ---------------- looking a place up ----------------
   The model works on coordinates, which is the right basis for it and the wrong
   thing to ask a person for. So this turns a name into a point, and nothing in
   the pricing depends on the name being in the list. */

var PLACE_INDEX = null;     // filled from the protocol when it is reachable

function loadPlaces(){
  if (PLACE_INDEX) return Promise.resolve(PLACE_INDEX);
  return api("/api/places", {timeout:8000}).then(function(reply){
    PLACE_INDEX = reply.places;
    return PLACE_INDEX;
  }, function(){
    PLACE_INDEX = LOCAL_PLACES;
    return PLACE_INDEX;
  });
}

function fold(text){
  return String(text)
    .replace(/[ıİI]/g, "i").replace(/[şŞ]/g, "s").replace(/[ğĞ]/g, "g")
    .replace(/[üÜ]/g, "u").replace(/[öÖ]/g, "o").replace(/[çÇ]/g, "c")
    .toLowerCase().trim();
}

function searchPlaces(query){
  var list = PLACE_INDEX || LOCAL_PLACES;
  var key = fold(query);
  // Nothing typed is not a reason to recommend eight places. It used to answer
  // an empty box with the first eight of the index, and the index is in
  // alphabetical order, so the most valuable space on this screen held Adana,
  // Adıyaman and Afyonkarahisar: three places chosen by the first letter of
  // their names, for a buyer who lives somewhere else. Nothing is offered now,
  // and the whole list is one press away for somebody who would rather look
  // than type.
  if (!key) return [];
  var hits = list.filter(function(p){ return fold(p.name).indexOf(key) >= 0; });
  hits.sort(function(a, b){
    var sa = fold(a.name).indexOf(key) === 0 ? 0 : 1;
    var sb = fold(b.name).indexOf(key) === 0 ? 0 : 1;
    return (sa - sb) || (a.name.length - b.name.length);
  });
  return hits.slice(0, 8);
}

function parseCoordinate(text){
  var m = String(text).match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!m) return null;
  var lat = parseFloat(m[1]), lon = parseFloat(m[2]);
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  // Drought settles at a named station rather than at a coordinate, so a typed
  // coordinate is not a subject for it. The two daily covers take one anywhere,
  // and the protocol answers with the countries and the distance.
  if (flow.peril === "drought" && !inTurkeyBox(lat, lon)) return null;
  return {name: lat.toFixed(3) + ", " + lon.toFixed(3), latitude: lat, longitude: lon,
          region: t("a coordinate you gave"), kind: "point"};
}

function inTurkeyBox(lat, lon){
  return lat >= 35.7 && lat <= 42.2 && lon >= 25.6 && lon <= 45.0;
}

/* Outside Türkiye the list of places lives on the protocol, not in this page:
   four thousand cities in the countries an earthquake model was built for.
   Asked as the buyer types, a moment after they stop. Each answer says whether
   that country's model passed its test, so a city that cannot be priced is
   shown as such rather than hidden or offered. */
var WORLD = {query:"", hits:[], seq:0, attribution:""}, worldTimer = null;
function searchWorld(query){
  var key = String(query || "").trim();
  if (flow.peril !== "quake" || !link.live || key.length < 2 || parseCoordinate(key)){
    WORLD.hits = []; WORLD.query = key; return;
  }
  if (WORLD.query === key) return;
  clearTimeout(worldTimer);
  worldTimer = setTimeout(function(){
    var seq = ++WORLD.seq;
    /* Which cover is being bought decides which places can be priced: the rain
       model passes in six countries and the wind model in another set, and the
       earthquake list answered for all three. */
    api("/api/places?query=" + encodeURIComponent(key.slice(0, 64)) +
        "&peril=" + encodeURIComponent(PERIL_KEYS[flow.peril] || ""), {timeout:8000}).then(function(reply){
      if (seq !== WORLD.seq) return;
      WORLD.query = key;
      WORLD.hits = (reply.places || []).filter(function(p){ return p.country && p.country !== "TR"; });
      WORLD.attribution = reply.attribution || "";
      if ($("place") && $("place").value.trim() === key && flow.step === 2) renderResults(key);
    }, function(){});
  }, 220);
}

function renderResults(query){
  var box = $("s2-opts");
  if (flow.peril === "flight"){
    box.innerHTML = subjectOptions();
    bindSubjectOptions();
    return;
  }

  var coordinate = parseCoordinate(query);
  var key = String(query || "").trim();
  var hits = coordinate ? [coordinate] : searchPlaces(query).map(function(p){
    return Object.assign({country:"TR", priced:true}, p);
  });
  var world = (!coordinate && flow.peril === "quake" && WORLD.query === key) ? WORLD.hits : [];
  searchAddress(key);
  var addresses = (!coordinate && ADDR.query === key) ? ADDR.hits.filter(function(a){
    return !hits.some(function(h){ return Math.abs(h.latitude-a.latitude)<0.01&&Math.abs(h.longitude-a.longitude)<0.01; });
  }).map(function(a){
    var priced = (flow.peril === "car" || flow.peril === "storm") ? a.country === "TR" : quakePriced(a.country);
    return Object.assign({}, a, {priced: priced});
  }) : [];
  if (world.length){
    // Exact and leading matches from anywhere first, the rest after.
    var lead = function(p){ return fold(p.name).indexOf(fold(key)) === 0 ? 0 : 1; };
    hits = hits.concat(world).sort(function(a, b){ return lead(a) - lead(b); }).slice(0, 10);
  }
  if (addresses.length) hits = hits.slice(0, 5).concat(addresses).slice(0, 11);
  searchWorld(query);
  if (!hits.length && !key){
    // Nothing typed yet. Say what the box takes and where cover can be
    // written, and put the whole list one press away rather than eight of it
    // on the screen. The list is built when it is opened: a hundred and three
    // places is five hundred nodes on the step that already has a map on it.
    var all = PLACE_INDEX || LOCAL_PLACES;
    box.innerHTML = '<div class="empty">' + esc(whereItIsWritten()) + " " +
      esc(flow.peril === "quake"
        ? t('Try a city there, or a coordinate as "35.68, 139.69".')
        : t('Try a province, a district, or a coordinate as "40.99, 29.03".')) + '</div>' +
      '<details class="more" id="all-places"><summary>' +
      // The catalogue is one country's provinces and districts, and cover is
      // priced in seven. "All 103 places" would say the opposite of that.
      esc(t("Browse the {n} places in {country}",
            {n: f0.format(all.length), country: regionName(all[0] && all[0].country || "TR") || "Türkiye"})) +
      '</summary><div class="inner" id="all-places-list"></div></details>';
    var more = $("all-places");
    more.addEventListener("toggle", function(){
      var into = $("all-places-list");
      if (!more.open || into.firstChild) return;
      into.innerHTML = placeButtons(all.map(function(p){
        return Object.assign({country: "TR", priced: true}, p);
      }));
      bindPlaceButtons(into);
    });
    return;
  }

  if (!hits.length){
    // Nothing matched, and for most of the world nothing ever will: the
    // catalogue only holds places in countries a model was built and tested
    // for. Somebody typing "Brasil" got an empty box and no reason for it,
    // which reads as a broken search rather than as an answer. So the empty
    // state says where the cover can be bought.
    box.innerHTML = '<div class="empty">' + esc(t("Nothing matched.")) + " " +
      esc(whereItIsWritten()) + " " + esc(flow.peril === "quake"
        ? t('Try a city there, or a coordinate as "35.68, 139.69".')
        : t('Try a province, a district, or a coordinate as "40.99, 29.03".')) + '</div>';
    return;
  }

  box.innerHTML = placeButtons(hits) + (world.length && WORLD.attribution
    ? '<p class="hint">' + esc(t("Place names outside Türkiye come from GeoNames (geonames.org), under CC BY 4.0.")) + '</p>' : '')
    + (addresses.length ? '<p class="hint">' + esc(t("Addresses from OpenStreetMap, © OpenStreetMap contributors, ODbL.")) + '</p>' : '');
  bindPlaceButtons(box);
}

function placeButtons(hits){
  return hits.map(function(place){
    var value = place.latitude + "," + place.longitude;
    var chosen = flow.subject === value;
    var off = place.priced === false;
    var abroad = place.country && place.country !== "TR";
    var sub = off ? (flow.peril === "car" || flow.peril === "storm"
                      ? whereItIsWritten()
                      : t("No tested earthquake model covers {country} yet, so cover cannot be priced here.",
                      {country:regionName(place.country)}))
            : abroad ? [place.region, regionName(place.country)].filter(Boolean).join(", ")
            : (place.region || "");
    return '<button class="opt' + (off ? ' off' : '') + '" type="button" data-value="' + esc(value) +
      '" data-name="' + esc(place.name) + '" data-kind="' + esc(place.kind || "") + '" data-country="' + esc(place.country || "") +
      '" data-street="' + esc(place.street || "") + '" data-city="' + esc(place.city || "") +
      '" aria-pressed="' + chosen + '"' + (off ? ' disabled' : '') + '>' +
      '<span class="lead">' + esc(place.kind === "point" ? "◎" : place.kind === "address" ? "⌂" : abroad ? place.country : place.name.slice(0,2).toUpperCase()) + '</span>' +
      '<span><span class="t">' + esc(place.name) + '</span>' +
      '<span class="s">' + esc(sub) + '</span></span>' +
      '<span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg></span>' +
      '</button>';
  }).join("");
}

function bindPlaceButtons(box){
  Array.prototype.forEach.call(box.querySelectorAll(".opt"), function(button){
    button.addEventListener("click", function(){
      if (button.disabled) return;
      flow.subject = button.dataset.value;
      flow.place = button.dataset.name;
      flow.placeCountry = button.dataset.country || null;
      offerAddress({street: button.dataset.street, city: button.dataset.city});
      markPressed(box, ".opt", function(n){ return n === button; });
      loadHazard(); centreMap(button.dataset.kind === "address" || button.dataset.kind === "point" ? 16 : 11);
    });
  });
}

/* Which model prices the chosen point, asked of the protocol. Türkiye's fault
   model runs in this page as well, so a Turkish place prices at once; any
   other point waits for the protocol's answer, and nothing is shown as a price
   until it arrives. A point no tested model covers is refused here, with the
   protocol's own reason, before the buyer goes any further. */
/* Two ways to measure an earthquake, chosen by the buyer. Shaking at the
   address is closer to what damages a house, and is the default wherever the
   protocol has published its shaking curve for the point. */
function indexToggle(){
  // Shaking by default once the protocol has published its curve for the
  // point; whatever the buyer picked, once they pick.
  var can=!!flow.shaking;
  var idx=!can?"magnitude":(flow.indexChosen?flow.index:"shaking");
  flow.index=idx;
  return '<div class="label">'+esc(t("What should the policy measure?"))+'</div>'+
    '<div class="seg" id="index-seg" role="radiogroup" style="margin:8px 0 14px">'+
    '<button type="button" role="radio" data-index="shaking" aria-checked="'+(idx==="shaking")+'"'+(can?'':' disabled')+'>'+esc(t("Shaking at my address"))+'</button>'+
    '<button type="button" role="radio" data-index="magnitude" aria-checked="'+(idx==="magnitude")+'">'+esc(t("Magnitude within a circle"))+'</button></div>';
}
function bindIndexToggle(){
  Array.prototype.forEach.call(document.querySelectorAll("#index-seg button"),function(b){
    b.addEventListener("click",function(){
      if(b.disabled)return;
      flow.index=b.dataset.index; flow.indexChosen=true; flow.quoted=null;
      renderRadius(); updatePriceBar(); updateMap();
    });
  });
}
function shakingHtml(){
  /* Every figure here comes from the policy: the levels it is written on, the
     share it pays at each, and the frequency of that level rather than of the
     round number beside it. All three were written down here instead -- VI,
     VII, VIII at 25, 60 and 100 per cent -- and all three were wrong. The
     contract pays 35, 75 and 100, and it pays them at 6.25 in Istanbul and
     6.62 in New York, because an older building is damaged by less shaking.
     Read at VI a New York policy looked as though it paid once in 1,788
     years; it pays once in about 3,100. */
  var sk=flow.shaking, qp=structure().pts, exc=shakingExc(365.25);
  function every(p){ return p>0?f0.format(Math.round(1/(-Math.log(1-p)))):"–"; }
  return '<p class="hint">'+esc(t("Pays on how hard the ground shook at the address itself, as the seismic networks' shaking maps record it, not on how large a distant earthquake was."))+'</p>'+
    '<div class="tbl-wrap" style="margin-top:10px"><table class="tbl" style="min-width:0"><tbody>'+
    [[qp[0][0],t("Intensity {level} or more: strong, light damage",{level:fLevel.format(qp[0][0])}),qp[0][1]],
     [qp[1][0],t("Intensity {level} or more: very strong, damage to ordinary buildings",{level:fLevel.format(qp[1][0])}),qp[1][1]],
     [qp[2][0],t("Intensity {level} or more: severe",{level:fLevel.format(qp[2][0])}),qp[2][1]]].map(function(r){
      return '<tr><td>'+esc(r[1])+'</td><td class="num">'+esc(t("about once in {n} years",{n:every(exc(r[0]))}))+'</td><td class="num">'+pct(r[2],0)+'</td></tr>';
    }).join("")+'</tbody></table></div>'+
    '<p class="fine" style="margin-top:8px">'+esc(shakingSource())+'</p>';
}
/* Where the frequencies above come from. A country that publishes its own
   national hazard model is the authority on its own ground, and the buyer is
   told whose figure priced the cover rather than left to assume it is ours. */
function shakingSource(){
  var from=flow.shaking&&flow.shaking.published;
  if(!from||!from.publisher) return t("Worked out from the same earthquake model, with a published intensity equation (Allen, Wald and Worden 2012) and its scatter.");
  var said=t("These frequencies are {publisher}'s own, the national hazard model published for {place}, converted to intensity with a published relation (Worden and others, 2012).",{publisher:from.publisher,place:from.place});
  /* The map is exact between their published points, so most of the time there
     is no factor worth printing. Where their curve reaches past ours far
     enough that the bound holds the map back, there is, and it is printed. */
  if((from.worst_ratio||1)>1.1) said+=" "+t("Ours follow theirs to within a factor of {factor} across the levels above.",{factor:f1.format(from.worst_ratio)});
  return said;
}
function hazardChanged(){ renderRadius(); updatePriceBar(); updateMap(); if (flow.step === 2) setNextLabel(); }
function loadHazard(){
  flow.grid = null; flow.gridError = null; flow.quoted = null; flow.shaking = null;
  var at = coordinates();
  if (at && flow.peril === "car"){ loadVehicle(); hazardChanged(); return; }
  if (at && flow.peril === "storm"){ loadStorm(); hazardChanged(); return; }
  if (!at || flow.peril !== "quake"){ hazardChanged(); return; }
  var local = flow.placeCountry === "TR" || (!flow.placeCountry && inTurkeyBox(at.latitude, at.longitude));
  flow.pointCountry = local ? "TR" : null;
  var seq = ++flow.hazardSeq;
  if (!link.live){
    if (!local) flow.gridError = t("Pricing outside Türkiye needs the protocol, which is not reachable right now.");
    hazardChanged();
    return;
  }
  hazardChanged();
  api("/api/hazard?latitude=" + at.latitude + "&longitude=" + at.longitude + "&radius_km=50", {timeout:12000})
    .then(function(reply){
      if (seq !== flow.hazardSeq) return;
      flow.pointCountry = reply.country || null;
      flow.grid = reply.grid || null;
      flow.shaking = reply.shaking || null;
      hazardChanged();
    }, function(error){
      if (seq !== flow.hazardSeq) return;
      var detail = error && error.payload && error.payload.detail;
      if (error && error.status === 400){
        flow.pointCountry = null;
        flow.gridError = typeof detail === "string" ? ts(detail) : t("No tested earthquake model covers this point yet.");
      } else if (!local){
        flow.gridError = t("Pricing outside Türkiye needs the protocol, which is not reachable right now.");
      }
      hazardChanged();
    });
}

/* Ready to price: a Turkish point (local model), or any point the protocol has
   answered for with a model, and never one it refused. */
function quakeReady(){
  if (flow.peril !== "quake" || !flow.subject) return true;
  if (flow.gridError) return false;
  return !!flow.grid || flow.pointCountry === "TR";
}

function flightReady(){
  if(flow.peril!=="flight")return true;
  return !!flow.flightFrom&&!!flow.flightTo&&flow.flightFrom!==flow.flightTo
    &&/^[A-Za-z0-9]{2}[0-9]{1,4}[A-Za-z]?$/.test(flow.flightNumber||"")
    &&/^\d{4}-\d{2}-\d{2}$/.test(flow.flightDate||"")&&/^\d{2}:\d{2}$/.test(flow.flightTime||"");
}
function bindSubjectOptions(){
  var box = $("s2-opts");
  markPressed(box, ".opt", function(n){ return n.dataset.value === flow.subject; });
  var no=$("flight-no"), date=$("flight-date");
  if(no)no.addEventListener("input",function(){ flow.flightNumber=no.value.toUpperCase().replace(/\s+/g,""); setNextLabel(); updatePriceBar(); });
  if(date)date.addEventListener("change",function(){ flow.flightDate=date.value; setNextLabel(); updatePriceBar(); });
  var clock=$("flight-time");
  if(clock)clock.addEventListener("change",function(){ flow.flightTime=clock.value; setNextLabel(); updatePriceBar(); });
  ["from","to"].forEach(function(side){
    var input=$("air-"+side);
    if(!input)return;
    input.addEventListener("input",function(){
      // Typing loosens what was chosen: the code and the words in the box
      // have to agree, or the buyer reads one flight and buys another.
      if(side==="from"){ flow.flightFrom=null; flow.flightFromText=input.value; }
      else { flow.flightTo=null; flow.flightToText=input.value; }
      flow.subject=null; flow.quoted=null;
      var said=$("air-"+side+"-said"); if(said)said.textContent="";
      airportHits(side);
      setNextLabel(); updatePriceBar();
    });
  });
  /* Delegated, not bound to each button.
     The airport suggestions are written into this box every time the reader
     types, long after this function ran, so a handler attached to the buttons
     that existed at bind time reached none of the ones a person actually
     clicks: the list appeared, the click did nothing, no error was raised,
     and the flight flow could not be completed at all. One listener on the
     box, which does not get replaced, answers for whatever is inside it now.
     Guarded so it is attached once even if this runs again. */
  if(!box.dataset.bound){
    box.dataset.bound="1";
    box.addEventListener("click", function(event){
      var button=event.target.closest?event.target.closest(".opt"):null;
      if(button&&box.contains(button))chose(button);
    });
  }
  function chose(button){
    {
      if(button.dataset.air){
        setAirport(button.dataset.side, button.dataset.air);
        renderResults($("place")?$("place").value:"");
        var next=$("air-to");
        if(button.dataset.side==="from"&&next&&!flow.flightTo)next.focus();
        updatePriceBar(); setNextLabel();
        return;
      }
      // A quick pick names both ends at once.
      var ends=String(button.dataset.value||"").split("-");
      if(ends.length===2){ setAirport("from",ends[0]); setAirport("to",ends[1]); }
      flow.place = null;
      if(!flow.flightNumber||!/^[A-Za-z]{2}/.test(flow.flightNumber)){
        var carrier=(Object.keys(ROUTES).filter(function(k){return k.endsWith("-"+ends[0]+"-"+ends[1]);})[0]||"XX-").split("-")[0];
        flow.flightNumber=carrier+"1979"; if(no)no.value=flow.flightNumber;
      }
      renderResults($("place")?$("place").value:"");
      updatePriceBar();
      setNextLabel();
    }
  }
}

function renderRadius(){
  var box=$("s2-extra");
  if(flow.peril==="car"){ renderCarInfo(); if(!flow.subject){box.hidden=true;box.innerHTML="";} return; }
  if(flow.peril==="storm"){ renderStormInfo(); if(!flow.subject){box.hidden=true;box.innerHTML="";} return; }
  if(flow.peril!=="quake"||!flow.subject){box.hidden=true;box.innerHTML="";return;}
  box.hidden=false;
  if(flow.gridError){
    box.innerHTML='<div class="verdict no"><p>'+esc(flow.gridError)+'</p></div>';
    return;
  }
  if(!quakeReady()){
    box.innerHTML='<p class="hint">'+esc(t("Asking the protocol which model prices this point…"))+'</p>';
    return;
  }
  box.innerHTML=indexToggle()+(shakingIndex()?shakingHtml():radiusOptions()+'<p class="hint" id="radius-note"></p>');
  bindIndexToggle();
  if(shakingIndex()){ return; }
  $("radius-note").innerHTML=radiusNoteHtml();
  markPressed(box,".opt",function(n){return +n.dataset.radius===flow.radius;});
  Array.prototype.forEach.call(box.querySelectorAll(".opt"),function(b){
    b.addEventListener("click",function(){
      flow.radius=+b.dataset.radius;
      markPressed(box,".opt",function(n){return n===b;});
      $("radius-note").innerHTML=radiusNoteHtml();
      updatePriceBar(); updateMap();
    });
  });
}

function renderAmount(){
  $("cover-amt").innerHTML=f0.format(flow.limit)+'<small>USDC</small>';
  $("cover-note").textContent=t("The most this policy can pay you.");
  markPressed($("cover-presets"),"button",function(n){return +n.dataset.v===flow.limit;});
}
/* The price counts to its new figure instead of jumping, so a change on the
   slider reads as movement, not a flicker. Set outright for anyone who asked
   for less motion, and when the figure is first shown. */
var MOTION_OK=!(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches);
function tweenAmount(el,value){
  var from=parseFloat(el.dataset.v);
  el.dataset.v=String(value);
  if(!MOTION_OK||isNaN(from)||from===value||Math.abs(from-value)<0.5){ el.textContent=money(value); return; }
  var t0=performance.now(), dur=420, token=(el._tw=(el._tw||0)+1);
  function frame(now){
    if(el._tw!==token)return;
    var k=Math.min(1,(now-t0)/dur), e=1-Math.pow(1-k,3);
    el.textContent=money(from+(value-from)*e);
    if(k<1)requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
/* The bar with no figure in it. The last figure is forgotten as well as
   erased: tweenAmount counts from whatever was there last, and a bar that has
   stood down and come back was counting down from the price of a policy
   nobody is buying any more -- 1,283 sweeping to 517 over four hundred
   milliseconds, which to anyone glancing at it is the price changing while
   they watch. It is the thing this bar was just taught not to do. */
function noAmount(el){ if(!el)return; delete el.dataset.v; el.textContent="—"; }
function skeleton(n){
  var out='<div class="skel" aria-busy="true" aria-label="'+esc(t("Reading…"))+'">'; for(var i=0;i<(n||3);i++)out+='<i></i>'; return out+'</div>';
}
/* At what reading this pays, in one clause.

   The price appears on the second question and until the fourth nothing on
   the screen said what has to happen for it to arrive. A premium without its
   trigger is a figure with nothing to judge it against: the reader was being
   asked to weigh 17,790 USDC against nothing at all. It is the first thing
   the caption says now, before the term and before the monthly figure. */
/* When the cover starts, and why that is not the day it is bought. Every peril
   here waits out the window in which the event is already public knowledge: a
   named storm is on the news a week before it lands, an aftershock sequence is
   felt from the moment the mainshock is, and a dry season is half over before
   anyone can see it. A policy bought inside that window is bought by someone
   who knows something the price does not, and the pool loses the difference on
   every one of them. The page carries the numbers so it can say the date
   before the protocol has answered; the protocol's own date replaces them the
   moment a price arrives, and it is the one that binds. */
var WAITING={quake:7,car:10,storm:10,flight:0};
function coverStartsAt(){
  // Only worth saying when it is a different day from today. Flight cover
  // starts the moment it is bought, and "cover starts today" beside the price
  // is a line that costs attention and answers nothing.
  var soon=Date.now()+86400000;
  var q=flow.quoted&&flow.quoted.cover;
  if(q&&q.starts_at)return q.starts_at*1000>soon?new Date(q.starts_at*1000):null;
  if(flow.peril==="drought"){
    var st=stationFor();
    if(!st||!st.opens)return null;
    var now=Date.now(), y=new Date(now).getUTCFullYear();
    var open=Date.UTC(y,st.opens[0]-1,st.opens[1]);
    if(open<now)open=Date.UTC(y+1,st.opens[0]-1,st.opens[1]);
    return new Date(open);
  }
  var days=WAITING[flow.peril];
  if(!days)return null;
  return new Date(Date.now()+days*86400000);
}
function waitWhy(){
  if(flow.peril==="quake")
    return t("An aftershock sequence is public knowledge from the moment the mainshock is felt, so cover starts seven days after it is bought.");
  if(flow.peril==="storm"||flow.peril==="car")
    return t("Weather this severe is forecast about a week ahead, so cover starts ten days after it is bought.");
  if(flow.peril==="drought")
    return t("The season this cover measures is the next one to open at the station, and sales for a season close fifteen days before it does.");
  return "";
}
function coverStartSaid(){
  var at=coverStartsAt();
  if(!at)return "";
  return t("cover starts {date}",{date:at.toLocaleDateString(LANG)});
}

/* The whole ladder, not only its bottom rung. "Pays from magnitude 5.5"
   answers half of what a buyer is asking; the other half is how much, and at
   which reading, and until now that half was only on the chart further down
   the page. Three rungs fit on the line beside the price. */
function rungWords(level){
  if(flow.peril==="quake")
    // The unit, then the reading, as the index itself is written: M5.5 for a
    // magnitude and MMI VII for shaking. A roman numeral on its own beside a
    // sum of money says nothing about what was measured.
    /* A roman numeral is a whole number and these steps are not. An older
       building pays at less shaking, so the first step sits at 6.25 in
       Istanbul and 6.62 in New York, and rounding it to the nearest numeral
       moved the threshold the buyer reads by up to half an intensity unit --
       New York's 6.62 was printed as VII, which is a level that happens half
       as often as the one the policy is written on. The numeral is kept where
       the step really is one, which is a building of the current code, and the
       number itself is printed otherwise. */
    return shakingIndex()
      ? "MMI "+(level === Math.round(level) ? (ROMAN[level]||String(level)) : fLevel.format(level))
      : "M"+fLevel.format(level);
  if(flow.peril==="storm")return fLevel.format(level)+" km/h";
  /* Rain to one decimal, as the sentence and the ladder write it, and the
     season's rainfall whole, as its own two write it.

     A day's rain threshold is not a round number: this place's once in ten
     years level is 47.6 mm. Rounding it here made the summary row say "48 mm
     2,500" between a sentence reading "If 47.6 mm or more of rain falls" and
     a ladder reading "47.6 mm or more in a day", all three on the paying
     screen. 48 and 47.6 are not the same threshold: a reader of the summary
     would think a 47.8 mm day pays nothing, and it pays 2,500.

     The season's levels are shares of a station's normal, hundreds of
     millimetres, where a tenth says nothing and both the other places that
     write them round. */
  if(flow.peril==="car")return fLevel.format(level)+" mm";
  if(flow.peril==="drought")return fLevel.format(level)+" mm";
  return level>=1440 ? t("cancelled") : t("{n}h late",{n:Math.round(level/60)});
}
function ladderSaid(){
  if(!flow.limit)return triggerSaid();
  // Whole amounts across the whole ladder. money() carries cents below a
  // thousand, which reads as an inconsistency when three rungs stand side by
  // side and only the top one is over it.
  function rung(v){ return f0.format(Math.round(v)); }
  var c=structure(), rungs=[];
  if(c.shape==="ramp")
    // A ramp has no rungs: it pays a little more for every millimetre below the
    // first point, so its two ends are the whole of what there is to say.
    return t("pays from {from}, and the full {amount} at {to}",
             {from:rungWords(c.pts[0][0]),to:rungWords(c.pts[c.pts.length-1][0]),
              amount:rung(flow.limit)});
  c.pts.forEach(function(pt){
    if(pt[1]>0)rungs.push(rungWords(pt[0])+" "+rung(pt[1]*flow.limit));
  });
  return rungs.length?rungs.join(" · "):triggerSaid();
}
/* What an index cover does not do, in the buyer's own numbers.
   Every peril here carries a basis_risk paragraph, written carefully, and
   the page never showed a word of it: it reached the policy document, which
   is read after paying, and the API sends it with every peril, which nothing
   on this page asks for. So the one thing a person most needs to have
   understood before they pay -- that this reads an index and not their loss,
   and that the gap runs in both directions -- was the one thing the flow
   never said.
   It is composed here rather than taken from the server's prose because it
   has to be true of this policy, with this ladder, and it has to exist in
   seven languages. The direction matters and is not uniform: drought pays
   when the season comes in under a figure, everything else when a reading
   comes in over one. Getting that backwards would print a false promise. */
function basisRiskSaid(){
  var c=structure(), pts=c.pts, first=null, i;
  for(i=0;i<pts.length;i++){ if(pts[i][1]>0){ first=pts[i][0]; break; } }
  if(first==null)first=pts[0][0];
  var level=rungWords(first);
  if(flow.peril==="drought")
    return [t("If the season's rainfall comes in above {level}, this pays nothing, even if the harvest fails.",{level:level}),
            t("If it comes in below {level}, it pays, even if the harvest is fine.",{level:level})];
  // A flight has nothing to damage, and the generic sentence would have said
  // so anyway. What is lost there is time and what the time cost.
  if(flow.peril==="flight")
    return [t("If the flight lands less than {level}, this pays nothing, even if the delay cost you a great deal.",{level:level}),
            t("If it is {level} or worse, it pays, even if the delay cost you nothing.",{level:level})];
  return [t("If the reading stays below {level}, this pays nothing, even if what you insured is damaged.",{level:level}),
          t("If the reading reaches {level}, it pays, even if nothing of yours is damaged.",{level:level})];
}

function triggerSaid(){
  var pts;
  // Both quake branches name the policy's own first step, as the three below
  // already did. Neither VI nor 5.5 is a fact about a policy: structure()
  // shifts the curve by the age of the building, so the trigger is 6.9 for a
  // flat built in 2005 and 5.2 for the same flat on the magnitude index built
  // in 1975.
  if(flow.peril==="quake"){ pts=structure().pts;
    return shakingIndex() ? t("pays from shaking of intensity {level}",{level:fLevel.format(pts[0][0])})
                          : t("pays from magnitude {level}",{level:fLevel.format(pts[0][0])}); }
  if(flow.peril==="car"){ pts=structure().pts;
    return t("pays from {mm} mm of rain in a day",{mm:fLevel.format(pts[0][0])}); }
  if(flow.peril==="storm"){ pts=structure().pts;
    return t("pays from wind of {kmh} km/h",{kmh:fLevel.format(pts[0][0])}); }
  if(flow.peril==="drought"){ var station=stationFor();
    return t("pays below {mm} mm of rain for the season",{mm:fLevel.format(.8*station.normal)}); }
  return t("pays from two hours late");
}
/* ---------------- the running summary ----------------
   Beside the question from the first step, in its empty state, filling as the
   reader answers. It is a view and never an input: every line is changed by
   going back to the step that set it, which is why nothing here is clickable.
   Rendered by the same call that paints the price bar, so the two can never
   disagree about what has been chosen. */
function perilTitle(){
  if(!flow.peril)return "";
  var card=document.querySelector('#home-picks .pick[data-peril="'+flow.peril+'"] h3');
  return card?card.textContent.trim():flow.peril;
}

function railRow(key,value,waiting){
  return '<div class="row"><dt>'+esc(key)+'</dt>'+
    '<dd'+(waiting?' class="waiting"':'')+'>'+esc(value)+'</dd></div>';
}

function updateRunRail(){
  var rail=$("runrail"), rows=$("runrail-rows"), foot=$("runrail-foot");
  if(!rail||!rows||!foot)return;
  /* Nothing to run once it is bought, and nothing to summarise on the step
     that is itself the summary: on the confirm step the whole deal is on the
     left in full, and a shorter copy of it beside that is noise. */
  rail.hidden=flow.step>=CONFIRM_STEP;
  /* The grid cannot see that the rail is hidden, so it is told. */
  if(rail.parentNode&&rail.parentNode.classList)
    rail.parentNode.classList.toggle("no-rail",rail.hidden);
  if(rail.hidden)return;

  var it=flow.interest||{}, where=subjectLabel();
  var html=railRow(t("Against"),flow.chosen?perilTitle():t("not chosen yet"),!flow.chosen);
  html+=railRow(t("Where"),where||t("not chosen yet"),!where);
  if(it.what||flow.step>=3)
    html+=railRow(t("What is at risk"),it.what||t("not described yet"),!it.what);
  if(flow.limit)
    html+=railRow(t("Pays up to"),money(flow.limit)+" USDC",false);
  rows.innerHTML=html;

  /* The premium, or the note that says where it will appear. A figure the
     protocol has not answered for yet is not shown as though it had. */
  var ready=flow.peril&&flow.subject&&flow.limit&&
            !(flow.peril==="quake"&&!quakeReady());
  if(!ready){
    foot.innerHTML='<p class="prompt">'+
      esc(t("Answer the questions and the price appears here."))+'</p>';
    return;
  }
  var q=priced(), current=flow.quoted&&flow.quotedFor===quoteKey();
  var offer=(current&&(flow.offers||[]).length)
    ? flow.offers.slice().sort(function(a,b){return a.fee-b.fee;})[0] : null;
  var days=PERILS[flow.peril].term;
  // The same rule as the bar, written the same way: a figure here is the one
  // that will be charged, so it waits for the quote and for the fee both.
  var settled=!link.live||(current&&!!offer);
  if(!settled){
    foot.innerHTML='<p class="prompt">'+
      esc(priceSaid(t("working out your price")))+'</p>';
    return;
  }
  var total=q.premium+(offer?offer.fee:0);
  foot.innerHTML='<div class="amt">'+esc(money(total))+'<small>'+esc(t("USDC"))+'</small></div>'+
    '<div class="prompt" style="font-style:normal">'+esc(t("for {days} days",{days:days}))+
      (offer?"":" · "+esc(t("before the company's fee")))+'</div>'+
    (offer?'<span class="runrail-chip">'+
      esc(t("This is the protocol's own price, including the company's fee."))+'</span>':'');
}

function updatePriceBar(){
  updateRunRail();
  // Whether the bar has a price in it yet. On a phone a bar with nothing to
  // say is not neutral: it is stuck to the bottom of the screen covering the
  // card below it, and everything in it -- an em dash, "choose a place to see
  // the price", and a disabled button repeating the heading word for word --
  // is already on the screen above. So it stands down until it has a figure.
  var bar=$("pricebar");
  function saying(price){ if(bar) bar.classList.toggle("empty",!price); }
  if(flow.peril==="quake"&&flow.subject&&!quakeReady()){
    noAmount($("pb-amt"));
    $("pb-cap").textContent=flow.gridError?t("cannot be priced here"):t("asking the protocol");
    // Waiting on a price is something to say: the bar stays.
    saying(true);
    return;
  }
  if(!flow.peril||!flow.subject||!flow.limit){
    noAmount($("pb-amt"));
    $("pb-cap").textContent=t("choose a place to see the price");
    saying(false);
    return;
  }
  saying(true);
  // priced(), not quote(), so the bar and the sentence above it can never show
  // two different prices: once the protocol has answered, both read from it.
  var q=priced(), current=flow.quoted&&flow.quotedFor===quoteKey();
  // Before the confirm step the cheapest company stands in for the one not yet
  // chosen, so the figure is the whole price: premium and fee, nothing to add later.
  var offer=flow.step===CONFIRM_STEP?chosenOffer():(current&&(flow.offers||[]).length?flow.offers.slice().sort(function(a,b){return a.fee-b.fee;})[0]:null);
  var days=PERILS[flow.peril].term;
  /* A figure appears when it is the figure that will be charged, and not
     before. This page can compute a premium of its own in a millisecond, and
     for a while it showed that while the protocol worked: captioned as
     provisional, and 70 per cent away from the answer. A buyer who glances at
     it and taps Continue has been quoted a price that was never on offer. The
     page cannot close that gap either, because the protocol prices the capital
     this policy adds to a book of a hundred thousand others and the browser
     does not have the book. So it waits, for the premium and for the company's
     fee both, because either arriving late moves the number.

     Not connected is the one case where the page's own figure is the price:
     the banner at the top says in so many words that everything below is
     computed in the browser and that nothing here is real, so there is no
     answer coming to replace it and nothing to wait for. */
  var settled=!link.live||(current&&!!offer);
  if(!settled){
    noAmount($("pb-amt"));
    $("pb-cap").textContent=ladderSaid()+" · "+
      t("{cover} of cover for {days} days",{cover:f0.format(flow.limit),days:days})+" · "+
      priceSaid(t("working out your price"));
    var waiting=$("pb-pays");
    if(waiting){ waiting.hidden=!flow.limit;
      waiting.innerHTML=esc(t("you receive up to"))+' <b>'+esc(money(flow.limit))+'</b>'; }
    saying(true);
    if(flow.step!==CONFIRM_STEP)scheduleQuote();
    return;
  }
  var total=q.premium+(offer?offer.fee:0);
  tweenAmount($("pb-amt"),total);
  var pays=$("pb-pays");
  if(pays){
    // What the policy pays at its top step, which is the limit: the figure
    // the price is actually buying, said beside it rather than further down.
    pays.hidden=!flow.limit;
    pays.innerHTML=esc(t("you receive up to"))+' <b>'+esc(money(flow.limit))+'</b>';
  }
  var cap=ladderSaid()+" · "+t("{cover} of cover for {days} days",{cover:f0.format(flow.limit),days:days});
  var starts=coverStartSaid();
  if(starts)cap+=" · "+starts;
  if(flow.step!==CONFIRM_STEP){
    cap+=" · "+(!offer?t("before the company's fee")
      :days>=60?t("all in, about {monthly} a month",{monthly:money(total*30/days)})
      :t("all in, nothing to add"));
    scheduleQuote();
  }
  if(offer&&offer.fee>0)cap+=" · "+t("includes the company's fee of {fee}",{fee:money(offer.fee)});
  if(flow.instalments>1){ var pl=(PLANS.plans||[]).filter(function(p){return p.count===flow.instalments;})[0]||{surcharge:0};
    cap+=" · "+t("{n} payments of {amount}",{n:flow.instalments,amount:money((q.premium+(offer?offer.fee:0))*(1+pl.surcharge)/flow.instalments)}); }
  var lock=flow.quoted&&flow.quoted.lock;
  if(lock&&flow.step===CONFIRM_STEP){
    var left=Math.max(0,Math.round(lock.expires_at-Date.now()/1000));
    cap+=" · "+(left>0?t("price held for {time}",{time:Math.floor(left/60)+":"+("0"+left%60).slice(-2)}):t("getting a fresh price"));
  }
  $("pb-cap").textContent=cap;
}
/* The price shown on the last step is promised for ten minutes: the bar counts
   it down, and a fresh one is asked for when it runs out. */
setInterval(function(){
  if(flow.step!==CONFIRM_STEP||!flow.quoted||!flow.quoted.lock||flow.busy)return;
  if(flow.quoted.lock.expires_at-Date.now()/1000<=0){ refreshQuote(); return; }
  updatePriceBar();
},1000);
/* Renewal: the same cover again. The buyer
   walks the same steps (address, declaration, contract), because a renewal is
   a new contract at today's price; what they insured is filled in for them. */
function renewFrom(policy){
  var pk=policy.peril_key||policy.peril;
  var key={earthquake:"quake",drought:"drought",vehicle_flood:"car",flight_delay:"flight",storm:"storm"}[pk]||pk;
  if(!PERILS[key])return;
  choosePeril(key);
  flow.limit=policy.limit; flow.renewing=policy.policy_id;
  var place=$("place"), text=policy.subject_text||"";
  if(place&&text&&key!=="flight"){ place.value=text.split(", within")[0]; place.dispatchEvent(new Event("input",{bubbles:true})); }
  var iw=(policy.metadata||{}).interest||{};
  if(iw.what)flow.interest.what=iw.what;
  renderStep();
}
function choosePeril(key){
  if(key!==flow.peril||!flow.chosen){
    // A different thing to protect starts its own declaration: "a flat in
    // Kadıköy" is not what is at risk on a flight.
    // The figure is part of the declaration too. It was the one field left
    // behind, so 150,000 declared against a flat rode along onto a flight,
    // where the protocol caps a trip at 20,000 -- and said so only at the
    // last step, as "http 422", after the price and the contract.
    flow.interest.what=""; flow.interest.touched=false; flow.interest.inside=false; flow.interest.value=0; flow.interest.declared=0; flow.interest.modelYear=null; flow.interest.address=null; flow.interest.documents=[]; flow.interest.insideTouched=false; flow.offersOpen=false;
    flow.place=null; flow.quoted=null; flow.refusal=null; flow.unreached=false;
    flow.offers=null; flow.carrier=null; flow.instalments=1; flow.index=null; flow.indexChosen=false; flow.pricing=false;
    flow.shaking=null; flow.vehicle=null; flow.storm=null; flow.renewing=null; CONTRACT={key:"",text:"",hash:""};
    flow.flightFrom=null; flow.flightTo=null; flow.flightFromText=""; flow.flightToText="";
    if($("place"))$("place").value="";
    flow.reached=1;
  }
  flow.peril=key; flow.chosen=true; flow.subject=null; flow.radius=50; flow.asset=null;
  flow.grid=null; flow.gridError=null; flow.placeCountry=null; flow.pointCountry=null; flow.size=null;
  flow.limit=PERILS[key].presets[1];
  goStep(2);
}

Array.prototype.forEach.call($("home-picks").querySelectorAll(".pick"),function(b){
  b.addEventListener("click",function(){choosePeril(b.dataset.peril);});
});
$("cover-range").addEventListener("input",function(e){
  flow.limit=limitFromSlider(+e.target.value);
  renderAmount(); updatePriceBar();
});
$("back").addEventListener("click",function(){if(flow.step>1)goStep(flow.step-1);});

/* "Get cover" means start: from the menu or the home page it opens on the first
   question with nothing chosen. It used to reopen whatever was chosen last in
   the tab, so someone who had looked at a flight earlier landed on a list of
   flights when they had come to insure a house. The picture cards on the home
   page still go straight to their own second step, because choosing one is
   the answer to the first question. */
function resetFlow(){
  if(flow.busy)return;
  flow.step=1; flow.reached=1; flow.chosen=false; flow.subject=null; flow.place=null;
  flow.grid=null; flow.gridError=null; flow.placeCountry=null; flow.pointCountry=null; flow.size=null;
  flow.quoted=null; flow.refusal=null; flow.unreached=false; flow.offers=null; flow.carrier=null;
  flow.instalments=1; flow.index=null; flow.indexChosen=false; flow.pricing=false; flow.shaking=null; flow.vehicle=null; flow.storm=null;
  flow.need=null; flow.statements=null; flow.renewing=null; flow.askedWhere=false;
  flow.interest.what=""; flow.interest.touched=false; flow.interest.inside=false; flow.interest.declared=0; flow.interest.modelYear=null; flow.interest.address=null; flow.interest.documents=[]; flow.interest.insideTouched=false; flow.offersOpen=false;
  CONTRACT={key:"",text:"",hash:""};
  if($("place"))$("place").value="";
}
// Delegated, because translating the page replaces the markup some of these
// links live in, and a listener on the old element would go with it.
document.addEventListener("click",function(e){
  var a=e.target&&e.target.closest?e.target.closest('a[href="#/cover"]'):null;
  if(!a)return;
  resetFlow();
  // Rendered whether or not the page was already on the flow: arriving from
  // elsewhere after a completed purchase must not show the old confirm panel.
  setTimeout(renderStep,0);
});
/* Takes the reader to the thing that is missing, and puts the caret in it. */
function takeTo(id){
  var el=id&&$(id); if(!el)return;
  el.scrollIntoView({behavior:"smooth",block:"center"});
  var into=el.matches("input,select,textarea,button")?el:el.querySelector("input,select,textarea,button");
  if(into)setTimeout(function(){ try{ into.focus({preventScroll:true}); }catch(e){ into.focus(); } },260);
}
$("next").addEventListener("click",function(){
  // The button is reachable even when it is not ready, so that pressing it
  // can say why. A press that cannot go on goes to what is holding it.
  if($("next").getAttribute("aria-disabled")==="true"){
    var missing=flow.step<CONFIRM_STEP?whatIsMissing():null;
    if(missing)takeTo(missing.at);
    else if(flow.step===CONFIRM_STEP&&!verified())takeTo("need-box");
    return;
  }
  if(flow.step<CONFIRM_STEP){goStep(flow.step+1);return;}
  var accepted=!link.live||(CONTRACT.hash&&CONTRACT.key===contractKey()&&$("accept").checked);
  if(!accepted){
    var box=$("contract-box"); box.hidden=false;
    box.scrollIntoView({behavior:"smooth",block:"center"});
    var label=$("accept").parentNode; label.classList.add("nudge");
    setTimeout(function(){ label.classList.remove("nudge"); },1800);
    setTimeout(function(){ $("accept").focus(); },500);
    return;
  }
  startPurchase();
});

