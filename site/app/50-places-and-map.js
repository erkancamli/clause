/* ---------------- addresses and the map ----------------
   The built in list knows provinces and the larger districts. Anything finer,
   "İstanbul Küçükçekmece" or a street, is asked of OpenStreetMap through the
   protocol's server, and the phone's own location is asked for once when the
   question is where. The map shows the point being insured; dragging the pin
   moves it. Tiles are OpenStreetMap's and credited on the map. */
var ADDR = {query:"", hits:[], seq:0}, addrTimer = null;
/* Where this cover can actually be priced, in the reader's own language and
   grammar. Named rather than implied: a buyer who cannot find their country
   is owed the list, not an empty box. */
function whereItIsWritten(){
  /* Read from what the protocol says it can price, per peril, rather than from
     a sentence written here. Rain and wind used to be Türkiye and only Türkiye,
     and the copy said so; they are now wherever a country's own daily record has
     been fitted and passed its backtest, which is a list that moves. */
  var priced=(COVERAGE&&COVERAGE.__priceable)||{};
  if(flow.peril!=="quake"){
    var here=priced[PERIL_KEYS[flow.peril]]||["TR"];
    var them=listText(here.map(function(c){ return regionName(c)||c; }).sort());
    return flow.peril==="car" ? t("Vehicle cover is written in {countries}: within 60 km of a place whose daily rainfall record has been fitted and tested.",{countries:them})
         : flow.peril==="storm" ? t("Storm cover is written in {countries}: within 60 km of a place whose daily wind record has been fitted and tested.",{countries:them})
         : t("Drought cover is written in {countries}, at the stations whose seasonal rainfall has been measured.",{countries:them});
  }
  var where=priced.earthquake||["TR"];
  var names=where.map(function(c){ return regionName(c)||c; }).sort();
  return t("Earthquake cover can be priced in {countries}: places where our own model passed its test, or where the country's own authority publishes the hazard at the address.",
           {countries:listText(names)});
}
function quakePriced(country){
  if(!country)return false;
  var p=(COVERAGE&&COVERAGE.__priceable&&COVERAGE.__priceable.earthquake);
  return p===null||p===undefined ? country==="TR" : p.indexOf(country)>=0;
}
function searchAddress(query){
  var key=String(query||"").trim();
  if((flow.peril!=="quake"&&flow.peril!=="car"&&flow.peril!=="storm")||!link.live||key.length<3||parseCoordinate(key)){
    ADDR.hits=[]; ADDR.query=key; return;
  }
  if(ADDR.query===key)return;
  clearTimeout(addrTimer);
  addrTimer=setTimeout(function(){
    var seq=++ADDR.seq, at=coordinates();
    /* A search is biased towards where the buyer already is. It used to fall back
     to the middle of Türkiye for the two daily covers, which put a buyer in
     Rome at the far end of every result list. With nothing to go on it now
     biases towards nothing. */
  var near=at?("&lat="+at.latitude.toFixed(3)+"&lon="+at.longitude.toFixed(3)):"";
    api("/api/geocode?q="+encodeURIComponent(key.slice(0,120))+"&lang="+LANG+near,{timeout:9000}).then(function(reply){
      if(seq!==ADDR.seq)return;
      ADDR.query=key; ADDR.hits=reply.places||[];
      if($("place")&&$("place").value.trim()===key&&flow.step===2)renderResults(key);
    },function(){
      // A refusal is an answer: without this the box goes on saying it is
      // still looking, for a call that has already stopped.
      if(seq!==ADDR.seq)return;
      ADDR.query=key; ADDR.hits=[];
      if($("place")&&$("place").value.trim()===key&&flow.step===2)renderResults(key);
    });
  },450);
}
/* The street and the town, as the place the buyer already found says them.
   They are an offer, not an answer: the fields stay editable, and a buyer who
   has typed their own is never overwritten. Somebody who searched their own
   address on the previous screen should not be made to type it again on this
   one; 6563 m.4(2) wants the answer correctable, and it stays correctable. */
function offerAddress(parts){
  if(!parts)return;
  var have=flow.interest.address||{};
  var kept={street:have.street||"", number:have.number||"", flat:have.flat||"",
            postcode:have.postcode||"", city:have.city||""};
  var touched=!!(flow.interest.addressTouched);
  if(!touched){
    if(parts.street)kept.street=String(parts.street).slice(0,80);
    if(parts.city)kept.city=String(parts.city).slice(0,60);
  }
  flow.interest.address=kept;
  flow.interest.addressOffered=!touched&&!!(parts.street||parts.city);
  // If the person is already looking at the fields, fill them in front of them.
  if($("addr-street")&&!touched){
    if(kept.street)$("addr-street").value=kept.street;
    if(kept.city)$("addr-city").value=kept.city;
  }
}
function setPoint(lat,lon,label,country){
  flow.subject=lat.toFixed(5)+","+lon.toFixed(5);
  flow.place=label||(lat.toFixed(4)+", "+lon.toFixed(4));
  flow.placeCountry=country||null;
  if($("place"))$("place").value=flow.place;
  // The label came from the map, not from typing: nothing to search for.
  ADDR.query=flow.place; ADDR.hits=[];
  renderResults($("place").value);
  loadHazard();
}
function locateMe(auto){
  var msg=$("locate-msg");
  if(!navigator.geolocation){ if(!auto)msg.textContent=t("This browser cannot tell where you are. Type your address instead."); return; }
  msg.textContent=t("Finding where you are…");
  navigator.geolocation.getCurrentPosition(function(pos){
    var lat=pos.coords.latitude, lon=pos.coords.longitude;
    var metres=Math.max(5,Math.round(pos.coords.accuracy||0));
    /* There is no pin yet. The browser answers in a moment and the address
       behind it takes a call with a nine second timeout and a retry, so
       "Check the pin, and drag it" was said for up to eighteen seconds about
       a pin that appears at the end of it. Said when there is one. */
    msg.textContent=t("Found where you are. Reading the address…");
    function pinned(){
      msg.textContent=t("Found, to within about {m} m. Check the pin, and drag it if it is not quite right.",
        {m:f0.format(metres)});
    }
    api("/api/reverse?latitude="+lat.toFixed(5)+"&longitude="+lon.toFixed(5)+"&lang="+LANG,{timeout:9000}).then(function(r){
      var p=r.place||{};
      setPoint(lat,lon,[p.name,p.region].filter(Boolean).join(", "),p.country);
      offerAddress({street:p.street,city:p.city});
      centreMap(16); pinned();
    },function(){ setPoint(lat,lon,null,null); centreMap(16); pinned(); });
  },function(error){
    msg.textContent=error&&error.code===1
      ? t("Location was not shared. Type your address, or allow location in the browser and try again.")
      : t("Your location could not be found just now. Type your address instead.");
  },{enableHighAccuracy:true,timeout:12000,maximumAge:60000});
}
$("locate-me").addEventListener("click",function(){ locateMe(false); });

var MAP={map:null,pin:null,ring:null,loading:null};
function leaflet(){
  if(window.L)return Promise.resolve(window.L);
  if(MAP.loading)return MAP.loading;
  MAP.loading=new Promise(function(resolve,reject){
    var css=document.createElement("link"); css.rel="stylesheet"; css.href="vendor/leaflet/leaflet.css";
    document.head.appendChild(css);
    var js=document.createElement("script"); js.src="vendor/leaflet/leaflet.js";
    js.onload=function(){ resolve(window.L); };
    js.onerror=function(e){ MAP.loading=null; js.remove(); reject(e); };
    document.head.appendChild(js);
  });
  return MAP.loading;
}
function showMap(){
  $("map-note").textContent=t("Map data © OpenStreetMap contributors. Drag the pin to the exact spot.");
  leaflet().then(function(L){
    if(!MAP.map){
      L.Icon.Default.imagePath="vendor/leaflet/images/";
      MAP.map=L.map("where-map",{zoomControl:true,attributionControl:true,scrollWheelZoom:false})
        .setView([39.0,35.2],5);
      MAP.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'}).addTo(MAP.map);
      MAP.map.on("click",function(e){ movePin(e.latlng); });
    }
    setTimeout(function(){ MAP.map.invalidateSize(); updateMap(); centreMap(); },50);
  },function(){ $("where-map").hidden=true; });
}
function movePin(latlng){
  var lat=latlng.lat, lon=latlng.lng;
  /* The pin used to be refused outside a Türkiye shaped box for the car and
     storm covers, which was true of the models and is not a thing the page can
     know any more: those covers are written wherever a country's own daily
     record has been fitted and passed. The point goes to the protocol, which
     answers with the countries and the distance, in the buyer's language. */
  setPoint(lat,lon,null,null);
  api("/api/reverse?latitude="+lat.toFixed(5)+"&longitude="+lon.toFixed(5)+"&lang="+LANG,{timeout:9000}).then(function(r){
    var p=r.place||{};
    if(coordinates()&&Math.abs(coordinates().latitude-lat)<1e-6){
      flow.place=[p.name,p.region].filter(Boolean).join(", ")||flow.place;
      flow.placeCountry=p.country||null;
      offerAddress({street:p.street,city:p.city});
      if($("place"))$("place").value=flow.place;
      loadHazard();
    }
  },function(){});
}
function updateMap(){
  if(!MAP.map||!window.L||flow.step!==2)return;
  var L=window.L, at=coordinates();
  if(!at){ if(MAP.pin){MAP.pin.remove();MAP.pin=null;} if(MAP.ring){MAP.ring.remove();MAP.ring=null;} return; }
  var ll=[at.latitude,at.longitude];
  if(!MAP.pin){
    MAP.pin=L.marker(ll,{draggable:true,autoPan:true}).addTo(MAP.map);
    MAP.pin.on("dragend",function(){ movePin(MAP.pin.getLatLng()); });
  }else MAP.pin.setLatLng(ll);
  var circle=flow.peril==="quake"&&!shakingIndex();
  if(circle){
    var metres=flow.radius*1000;
    if(!MAP.ring)MAP.ring=L.circle(ll,{radius:metres,color:"#d9480f",weight:1.5,fillOpacity:.07}).addTo(MAP.map);
    else{ MAP.ring.setLatLng(ll); MAP.ring.setRadius(metres); }
  }else if(MAP.ring){ MAP.ring.remove(); MAP.ring=null; }
  // Whenever the point or what is drawn around it changes, show it properly.
  var view=flow.subject+"|"+circle+"|"+flow.radius;
  if(MAP.view!==view){ MAP.view=view; frame(); }
}
function frame(){
  var at=coordinates(); if(!at||!MAP.map)return;
  if(MAP.ring) MAP.map.fitBounds(MAP.ring.getBounds(),{padding:[16,16]});
  else MAP.map.setView([at.latitude,at.longitude],flow.peril==="car"?15:16);
}
function centreMap(){
  // A circle is shown whole; a single point close enough to check the pin.
  if(!MAP.map)return;
  MAP.view=null; updateMap();
}


/* The companies that could issue this, side by side, the buyer's pick first. */
function chosenOffer(){
  return (flow.offers||[]).filter(function(o){return o.carrier_id===flow.carrier;})[0]||null;
}
/* The offer the price is struck on: the one chosen, or the one they would get
   if they chose nothing, which is the first because the list arrives sorted by
   what it costs. Companies price the same risk differently, so there is no
   such thing as the price until one of them is named. */
function offerForPrice(){
  return chosenOffer()||(flow.offers||[])[0]||null;
}
/* The companies that are licensed for this cover and still did not appear.
   A list that has quietly shrunk from five names to one reads exactly like a
   country with one insurer in it, and the difference matters to someone
   deciding whether to buy here. Shown only when the list is open, so it does
   not crowd the price. */
function heldBackSaid(){
  var held=flow.heldBack||[];
  if(!held.length||!flow.offersOpen)return "";
  return '<p class="fine held">'+esc(t("Also licensed here, but not offering:"))+' '+
    held.map(function(h){ return esc(ts(h.name))+" — "+esc(ts(h.why)); }).join("; ")+'</p>';
}
function renderOffers(){
  var box=$("offers-box"), list=flow.offers||[];
  if(!link.live||!list.length){ box.hidden=true; return; }
  box.hidden=false;
  // The chosen company in full; the others behind one line, so the page
  // is not three cards long before the buyer has read the price.
  var chosenId=flow.carrier||(list[0]&&list[0].carrier_id);
  var shown=(flow.offersOpen||list.length<2)?list:list.filter(function(o){return o.carrier_id===chosenId;});
  $("offers").innerHTML=shown.map(function(o){
    return '<button class="offer" type="button" data-carrier="'+esc(o.carrier_id)+'" aria-pressed="'+(o.carrier_id===flow.carrier)+'">'+
      '<span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg></span>'+
      '<span><span class="nm">'+esc(ts(o.name))+'</span>'+(o.cheapest?'<span class="tag">'+esc(t("cheapest"))+'</span>':'')+(o.fastest&&!o.cheapest?'<span class="tag">'+esc(t("fastest payout"))+'</span>':'')+
      '<br><span class="fine">'+esc(ts(o.authority))+'</span></span>'+
      '<span class="price">'+money(o.total)+' <small>'+esc(o.fee>0?t("{premium} + {fee} fee",{premium:money(o.premium),fee:money(o.fee)}):t("no fee"))+'</small></span>'+
      '<ul>'+o.plus.map(function(x){return '<li class="p">'+esc(ts(x))+'</li>';}).join("")+o.minus.map(function(x){return '<li class="m">'+esc(ts(x))+'</li>';}).join("")+'</ul>'+
      '</button>';
  }).join("")+
    /* The others, as a line each, when they are collapsed.
       One card and a link reading "compare five other companies" is a choice
       a buyer cannot see: it looks like the protocol found one insurer, and
       the only way to learn otherwise is to press something that sounds like
       extra work. The alternatives are named with their prices instead, in a
       row small enough that the page is still not three cards long before the
       price has been read. Pressing one chooses it; the card above becomes
       that company. */
    ((!flow.offersOpen&&list.length>1)
      ? '<div class="alts"><div class="label">'+esc(t("Also offering this cover"))+'</div>'+
        list.filter(function(o){return o.carrier_id!==chosenId;}).map(function(o){
          return '<button class="alt" type="button" data-carrier="'+esc(o.carrier_id)+'">'+
            '<span class="nm">'+esc(ts(o.name))+'</span>'+
            '<span class="pr">'+money(o.total)+'</span></button>';
        }).join("")+'</div>'
      : '')+
    (list.length>1?'<button class="btn btn-ghost btn-sm" type="button" id="offers-toggle" aria-expanded="'+(!!flow.offersOpen)+'">'+
    esc(flow.offersOpen?t("Keep this company and hide the others"):t("Compare all {n} side by side",{n:list.length}))+'</button>':'')+heldBackSaid();
  Array.prototype.forEach.call($("offers").querySelectorAll(".offer,.alt"),function(b){
    b.addEventListener("click",function(){
      flow.carrier=b.dataset.carrier; renderOffers(); renderPrice(); updatePriceBar();
    });
  });
  var toggle=$("offers-toggle"); if(toggle)toggle.addEventListener("click",function(){ flow.offersOpen=!flow.offersOpen; renderOffers(); });
}
/* Paying in parts, where the buyer's country does that. */
var PLANS={key:"",plans:[]};
function renderPlan(){
  var box=$("plan-box"); if(!link.live){ box.hidden=true; return; }
  var key=[flow.interest.country,PERILS[flow.peril].term].join("|");
  function draw(){
    var plans=PLANS.plans;
    if(plans.length<2){ box.hidden=true; flow.instalments=1; return; }
    box.hidden=false;
    if(!plans.some(function(p){return p.count===flow.instalments;}))flow.instalments=1;
    var q=priced(), offer=chosenOffer(), total=q.premium+(offer?offer.fee:0);
    $("plan-seg").innerHTML=plans.map(function(p){
      return '<button type="button" role="radio" data-n="'+p.count+'" aria-checked="'+(p.count===flow.instalments)+'">'+esc(ts(p.label))+
        (p.surcharge?'<br><small>+'+pct(p.surcharge,0)+'</small>':'')+'</button>';
    }).join("");
    var chosen=plans.filter(function(p){return p.count===flow.instalments;})[0];
    $("plan-note").textContent=chosen.count>1
      ? t("{count} payments of {amount}: the first when the insurer approves, then one every {days} days, taken from your address. A payment missed for more than 15 days ends the policy; anything still owed when a payout is made is deducted from it.",
          {count:chosen.count,amount:money(total*(1+chosen.surcharge)/chosen.count),days:Math.round(PERILS[flow.peril].term/chosen.count)})
      : t("Paid in full when the insurer approves.");
    Array.prototype.forEach.call($("plan-seg").querySelectorAll("button"),function(b){
      b.addEventListener("click",function(){ flow.instalments=+b.dataset.n; renderPlan(); renderContract(); updatePriceBar(); });
    });
  }
  if(PLANS.key===key){ draw(); return; }
  api("/api/instalments?country="+encodeURIComponent(flow.interest.country||"")+"&term_days="+PERILS[flow.peril].term).then(function(r){
    PLANS={key:key,plans:r.plans||[]}; draw();
  },function(){ box.hidden=true; });
}
/* The contract, in full, before the signature; its hash goes into the terms. */
var CONTRACT={key:"",text:"",hash:""};
/* What makes this contract a different contract.
   The premium used to be in here as the page's live figure, which meant the
   contract was invalidated -- and the acceptance silently un-ticked -- every
   time the price moved by a penny, for a reason that had nothing to do with
   the buyer: another policy written somewhere in the book. A person reading
   the contract, which is the longest thing on the page, could not get to the
   end of it before the thing they were about to accept had been replaced
   underneath them, and the tick box then answered to nothing.
   A held quote is a promise about the price for ten minutes, and the protocol
   keeps it: the contract is fetched with the lock's id and the purchase is
   sent with it. So while a lock is held, the lock is the price, and what the
   book does in the meantime is not the buyer's problem. Only when there is no
   lock does the live figure stand in, because then there is nothing else. */
function contractKey(){
  var lock=flow.quoted&&flow.quoted.lock;
  var held=lock&&lock.expires_at-Date.now()/1000>0;
  return JSON.stringify([PERIL_KEYS[flow.peril],subjectPayload(),flow.limit,flow.carrier,
                         flow.instalments,flow.interest.address,sizePayload(),
                         held?["lock",lock.id]:priced().premium]);
}
/* Two contract keys that differ only in their last element, which is the
   price or the lock that stands for it. Everything the buyer chose is in the
   elements before it. */
function onlyThePriceMoved(before, now){
  try {
    var a=JSON.parse(before), b=JSON.parse(now);
    return JSON.stringify(a.slice(0,-1))===JSON.stringify(b.slice(0,-1));
  } catch(e){ return false; }
}
function renderContract(){
  var box=$("contract-box"); if(!link.live){ box.hidden=true; return; }
  box.hidden=false;
  var key=contractKey();
  var note=$("accept-note");
  if(CONTRACT.key===key){ $("contract-text").textContent=CONTRACT.text; return; }
  /* The tick is about to be taken back. A buyer who changed something knows
     why; a buyer who was reading does not, and the contract is the longest
     text in the product. A held price lasts ten minutes, so anyone reading
     for longer than that had their acceptance undone and the button put back
     to "Read and accept the contract", with nothing on the screen saying so
     but the price bar's caption. */
  var undone=$("accept").checked&&CONTRACT.key&&onlyThePriceMoved(CONTRACT.key,key);
  $("contract-text").textContent=t("Preparing the contract…");
  $("accept").checked=false; setNextLabel();
  if(note){
    note.hidden=!undone;
    if(undone)note.textContent=t("The price was held for ten minutes and that time is up, so the contract has been drawn again at today's price. Read it and accept it again.");
  }
  // While the protocol is still pricing, wait for its price: the contract is
  // written on it, and carries its lock so the same policy is not priced
  // again for the text. renderPrice() comes back here when the price lands.
  if(flow.pricing)return;
  api("/api/contract",{method:"POST",timeout:25000,body:{
    peril:PERIL_KEYS[flow.peril], subject:subjectPayload(), limit:flow.limit, term_days:PERILS[flow.peril].term,
    carrier_id:flow.carrier||undefined, instalments:flow.instalments||1, quote_id:(flow.quoted&&flow.quoted.lock)?flow.quoted.lock.id:undefined, settlement:localRuling().asset,
    interest:{what:flow.interest.what, country:flow.interest.country, inside_trigger_area:true,
              value_at_risk:flow.interest.value, size:sizePayload(), address:flow.interest.address||undefined, professional:false},
  }}).then(function(r){
    if(contractKey()!==key){
      /* The terms moved while this was being fetched -- a price that changed,
         a company chosen, the lock renewed -- so this text is the contract
         for a policy nobody is buying. It used to be dropped here and nothing
         was asked again: the panel stayed on "preparing", the checkbox went
         dead, and ticking it did nothing at all, for ever, with no error to
         see and no way to tell. Ask again for the terms that are on the
         screen now, a few times, and then say so rather than sit there. */
      renderContract.chased=(renderContract.chased||0)+1;
      if(renderContract.chased<4){ renderContract(); return; }
      renderContract.chased=0;
      contractFailed(t("The price moved while the contract was being prepared."));
      return;
    }
    renderContract.chased=0;
    CONTRACT={key:key,text:r.text,hash:r.hash}; $("contract-text").textContent=r.text; setNextLabel(); showLaterBox();
  },function(e){
    /* A contract that could not be prepared is not a tick box that does
       nothing. What was held here before was the last contract's key, so the
       button went on asking to accept a contract the page did not have. */
    contractFailed(refusalText(e));
  });
}

/* No contract, and it says so. The box is cleared rather than left holding a
   key from a policy that is no longer on the screen, the button is told, and
   there is a way to ask again -- because the alternative, which is what
   shipped, is a checkbox that answers to nothing. */
function contractFailed(why){
  CONTRACT={key:"",text:"",hash:""};
  var el=$("contract-text");
  if(el){
    el.textContent=why;
    var ask=document.createElement("button");
    ask.type="button"; ask.className="linkish"; ask.style.marginTop="8px";
    ask.textContent=t("Try preparing it again");
    ask.addEventListener("click",function(){ renderContract(); });
    el.appendChild(document.createElement("br"));
    el.appendChild(ask);
  }
  if($("accept"))$("accept").checked=false;
  setNextLabel();
}
$("accept").addEventListener("change",function(){
  // Ticked again: the note has been read and answered.
  var note=$("accept-note");
  if(note&&$("accept").checked)note.hidden=true;
  setNextLabel();
});
/* What a buyer can do after buying, said before they buy. */
var CANCEL_TERMS={key:"",text:""};
function renderCancelTerms(){
  var el=$("cancel-terms"); if(!el)return;
  var key=[flow.interest.country,PERIL_KEYS[flow.peril],PERILS[flow.peril].term].join("|");
  if(CANCEL_TERMS.key===key){ el.textContent=CANCEL_TERMS.text; return; }
  if(!link.live){ el.textContent=""; return; }
  api("/api/cancellation/terms?country="+encodeURIComponent(flow.interest.country||"")+"&peril="+PERIL_KEYS[flow.peril]+"&term_days="+PERILS[flow.peril].term).then(function(r){
    var parts=[t("Changed your mind? Within an hour of buying, all of it comes back.")];
    if(r.cooling_off_days) parts.push(r.statutory
      ? t("Within {days} days, all of it comes back under {law}.",{days:r.cooling_off_days,law:ts(r.law)})
      : t("Within {days} days, all of it comes back, as this protocol's own rule.",{days:r.cooling_off_days}));
    parts.push(r.pro_rata_after
      ? t("After that, the unexpired part of the premium comes back when you cancel.")
      : t("After that the cover runs to the end of its term; rain and flights can be seen coming, so leaving early is not offered."));
    parts.push(t("Nothing can be cancelled once its trigger has been reached."));
    CANCEL_TERMS={key:key,text:parts.join(" ")}; el.textContent=CANCEL_TERMS.text;
  },function(){ el.textContent=""; });
}
/* What the same home would pay the country's own earthquake scheme, so a
   buyer can see the price against the one they know. Türkiye only, from the
   DASK tariff of 1 September 2025: a rate per thousand by risk zone and
   building type, on a set cost per square metre, with a ceiling. DASK is an
   indemnity policy with an assessor and a 2% deductible, backed by the state
   pool; this pays from the index, with no deductible and no assessor. */
var DASK={date:"2025-09-01", unit:{concrete:9180, other:6120}, max:1946155,
  rate:{concrete:[2.56,2.28,1.94,1.82,1.36,0.97,0.66], other:[4.51,3.86,3.39,3.17,2.54,1.69,0.99]}};
function marketHtml(){
  if(flow.peril!=="quake"||riskCountry()!=="TR")return "";
  var z=sizeState(); if(!z||z.kind!=="home"||!(z.area_m2>0))return "";
  var type="concrete";
  var insured=Math.min(DASK.max, z.area_m2*DASK.unit[type]);
  var lo=insured*DASK.rate[type][6]/1000, hi=insured*DASK.rate[type][0]/1000;
  return '<details class="more" style="margin:0"><summary>'+esc(t("For comparison: Türkiye's compulsory earthquake insurance"))+'</summary><div class="inner"><p>'+
    esc(t("DASK would charge about {low} to {high} lira a year for {area} m² in a reinforced concrete building, depending on the risk zone (tariff of 1 September 2025). It pays after an assessor has seen the damage, above a 2% deductible, up to {cap} lira. This cover pays from the reading alone, with no assessor and no deductible, which is why it costs more.",
      {low:f0.format(Math.round(lo)),high:f0.format(Math.round(hi)),area:f0.format(z.area_m2),cap:f0.format(DASK.max)}))+'</p></div></details>';
}


/* Your policy tokens, as a wallet would show them: one card per policy. */
function renderNfts(policies){
  var box=$("mine-nfts"); if(!box)return;
  // A burned token has left the wallet: the cancelled policy stays in the
  // list below as a record, its token does not.
  var minted=policies.filter(function(p){ var tk=(p.metadata||{}).token; return tk&&!tk.burned_at; });
  if(!minted.length){ box.innerHTML=""; return; }
  box.innerHTML='<div class="label" style="margin-top:22px">'+esc(t("Your policy tokens ({n})",{n:minted.length}))+'</div><div class="nfts">'+
    minted.map(function(p){ return '<button class="nft" type="button" data-token="'+esc(p.policy_id)+'"><img alt="'+esc(p.policy_id)+'" data-src="'+esc(p.policy_id)+'">'+
      '<span>'+esc(p.policy_id)+' · '+esc(t(POLICY_STATUS[p.status]||p.status))+'</span></button>'; }).join("")+'</div>';
  Array.prototype.forEach.call(box.querySelectorAll("img[data-src]"),function(img){
    api("/api/policies/"+encodeURIComponent(img.dataset.src)+"/token",{timeout:9000}).then(function(m){ img.src=m.image; },function(){});
  });
  bindTokens(box);
}
