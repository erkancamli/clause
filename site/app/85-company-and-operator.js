/* ---------------- the company side ----------------
   Where an insurer looks at this protocol and sees what it would be joining:
   which countries are open and who opened them, what everyone else is charging
   to front, and a form that records a statement and grants nothing. */

function renderInsurers(){
  fillCountries($("co-domicile"), "JP");
  fillCountries($("co-country"), "JP");
  bindCarrierForm();


  var coverage=$("coverage-out"), companies=$("carriers-out");
  coverage.innerHTML='<div class="panel" style="padding:22px">'+esc(t("Reading the registry…"))+'</div>';
  companies.innerHTML="";

  whenLinked().then(function(){
    if(!link.live){
      coverage.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("This page cannot reach the protocol, so there is no registry to read. It will not show you a coverage map it invented."))+'</p></div>';
      return;
    }
    return Promise.all([
      api("/api/compliance",{timeout:9000}),
      api("/api/carriers",{timeout:9000}),
    ]).then(function(both){
      coverage.innerHTML=coverageHtml(both[0]);
      companies.innerHTML=companiesHtml(both[1]);
    },function(){
      coverage.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("The protocol did not answer."))+'</p></div>';
    });
  });
}

function coverageHtml(payload){
  var rows=payload.coverage||[], registry=payload.registry||{};
  var waiting=payload.waiting||[];
  var out='<div class="stats stats-lg" style="margin:0 0 20px">'+
    '<div class="stat"><b>'+f0.format(registry.countries||0)+'</b><span>'+esc(t("Countries open"))+'</span></div>'+
    '<div class="stat"><b>'+f0.format(registry.carriers||0)+'</b><span>'+esc(t("Carriers"))+'</span></div>'+
    '<div class="stat"><b>'+f0.format(registry.reinsurers||0)+'</b><span>'+esc(t("Reinsurers"))+'</span></div>'+
    '<div class="stat"><b>'+money(registry.capacity||0)+'</b><span>'+esc(t("Capacity"))+' · USDC</span></div>'+
    '</div>';

  if(!rows.length&&!waiting.length){
    out+='<div class="panel" style="padding:22px"><p>'+esc(t("Nobody is registered, so nothing can be written anywhere. That is the honest starting state of a protocol that will not sell without a licence."))+'</p></div>';
    return out;
  }
  if(!rows.length){
    out+='<div class="panel" style="padding:22px;margin-bottom:14px"><p>'+esc(t("Nothing can be bought anywhere yet. A country opens when a licensed carrier, a reinsurer behind it, and a model that can price the risk are all in place."))+'</p></div>';
  }

  // Countries with the most on offer first; past a dozen, the rest fold away.
  rows=rows.slice().sort(function(a,b){
    return (b.perils.length-a.perils.length)||(a.specimen-b.specimen)||
      countryName(a.country).localeCompare(countryName(b.country));
  });
  var FOLD=12;
  if(rows.length)
    out+='<div class="cov"><div class="head"><span>'+esc(t("Country"))+'</span><span>'+esc(t("Who is licensed"))+'</span>'+
       '<span>'+esc(t("Payout currency"))+'</span><span>'+esc(t("Buyers"))+'</span></div>';
  rows.forEach(function(row,i){
    if(i===FOLD&&rows.length>FOLD+2)
      out+='</div><details class="more"><summary>'+esc(t("Every country ({n})",{n:f0.format(rows.length)}))+
        '</summary><div class="inner"><div class="cov">';
    out+='<div><b>'+esc(countryName(row.country))+
      (row.specimen?' <span class="pill no">'+esc(t("specimen"))+'</span>':'')+
      '<br><span class="fine">'+esc(perilWords(row.perils))+
      ((row.unpriced||[]).length?' · '+esc(t("not yet {perils}",{perils:perilWords(row.unpriced)})):'')+'</span></b>'+
      '<span class="licensed">'+esc(listText(row.carriers.map(ts)))+
      '<br><span class="fine auth">'+esc(listText(row.authorities.map(ts)))+'</span></span>'+
      '<span class="auth">'+esc(listText(row.settlement.map(localValue)))+'</span>'+
      '<span class="pill '+(row.retail?"ok":"")+'">'+
      esc(row.retail?t("anyone"):t("professional"))+'</span></div>';
  });
  if(rows.length) out+='</div>';
  if(rows.length>FOLD+2) out+='</div></details>';
  if(waiting.length){
    out+='<h2 style="font-size:16px;margin:26px 0 10px">'+esc(t("Licensed, not yet open"))+'</h2>'+
      '<p class="fine" style="margin-bottom:10px">'+esc(t("A company is licensed in each of these, and something else is still missing. Nothing can be bought here until it is in place."))+'</p><div class="cov">';
    waiting.forEach(function(row){
      out+='<div><b>'+esc(countryName(row.country))+
        (row.specimen?' <span class="pill no">'+esc(t("specimen"))+'</span>':'')+'</b>'+
        '<span class="licensed">'+esc(listText(row.carriers.map(ts)))+'</span>'+
        '<span class="auth">'+esc(t("waiting on {missing}",{missing:listText(row.waiting_on.map(ts))}))+'</span>'+
        '<span class="pill no">'+esc(t("not open"))+'</span></div>';
    });
    out+='</div>';
  }
  out+='<p class="fine" style="margin-top:12px">'+tsHtml(payload.unlisted||"")+'</p>';
  return out;
}

var REACH_WORDS={retail:N("consumers"),professional:N("professionals only")};
var ROLE_WORDS={carrier:N("carrier"),reinsurer:N("reinsurer")};
var COMPANY_STATUS={pending:N("pending"),active:N("active"),suspended:N("suspended"),withdrawn:N("withdrawn")};
function perilWords(list){ return listText((list||[]).map(localValue)); }

function specimenList(list){
  if(list.length<6) return null;
  return '<details class="more"><summary>'+esc(t("Stand in companies, not real ({n})",{n:f0.format(list.length)}))+'</summary>'+
    '<div class="inner"><p class="fine">'+esc(t("Every one of these is a specimen: no licence, no regulator, no company. They exist so the protocol can be shown working in every country; a real deployment has none of them."))+'</p>'+
    '<div class="spec-list">'+list.map(function(c){
      return '<span><b>'+esc(regionName(c.domicile))+'</b> '+esc(ts(c.name))+'</span>';
    }).join("")+'</div></div></details>';
}
function companiesHtml(payload){
  var all=payload.companies||[];
  /* Every stand in this build ships, folded behind one line. The test used to
     match only the unsuffixed id, so when each country gained a second and a
     third the page grew four hundred cards nobody asked for. */
  var stand=all.filter(function(c){ return c.specimen&&c.folded; });
  var folded=specimenList(stand);
  var companies=folded?all.filter(function(c){ return stand.indexOf(c)<0; }):all;
  return companies.map(function(c){
    var licences=(c.licences||[]).map(function(l){
      return '<div class="vrule"><span class="mark">'+esc(l.country)+'</span>'+
        '<span><span class="t">'+esc(ts(l.authority))+'</span>'+
        '<span class="s">'+esc(ts(l.reference))+' · '+esc(perilWords(l.perils))+
        ' · '+esc(t(REACH_WORDS[l.reach]||l.reach))+' · '+
        esc(t("settles {assets}",{assets:listText(l.settlement.map(localValue))}))+'</span></span>'+
        '<span class="pill '+(l.live?(l.expiring_soon?"":"ok"):"no")+'">'+
        esc(l.live?(l.expiring_soon?t("renewing"):t("live")):t("out of force"))+'</span></div>';
    }).join("");
    return '<div class="co-card">'+
      '<div><div class="co-head"><span class="nm">'+esc(ts(c.name))+'</span>'+
        '<span class="pill '+(c.status==="active"?"ok":c.status==="pending"?"":"no")+'">'+
        esc(t(COMPANY_STATUS[c.status]||c.status))+'</span>'+
        (c.specimen?'<span class="pill no">'+esc(t("specimen"))+'</span>':'')+
        '<span class="fine">'+esc(t(ROLE_WORDS[c.role]||c.role))+' · '+
          esc(t("domiciled in {country}",{country:regionName(c.domicile)}))+'</span></div></div>'+
      (licences?'<div>'+licences+'</div>':'')+
      '<div><div class="kvs">'+
        kv(t("Capacity"),money(c.capacity))+
        kv(t("In force"),money(c.in_force))+
        kv(t("Policies"),f0.format(c.policies_written))+
        kv(t("Fronting fee"),c.fronting_fee?pct(c.fronting_fee,2):esc(t("none")))+
      '</div></div></div>';
  }).join("")+(folded||"") || '<div class="panel" style="padding:22px"><p>'+esc(t("Nobody yet."))+'</p></div>';
}

var CARRIER_BOUND=false;

function carrierAmount(v,lo,hi){
  var f=(v-1)/99, raw=lo*Math.pow(hi/lo,f);
  var step=raw>2000000?250000:raw>200000?25000:raw>20000?5000:1000;
  return Math.max(lo,Math.round(raw/step)*step);
}

function bindCarrierForm(){
  if(CARRIER_BOUND)return;
  CARRIER_BOUND=true;

  var PERIL_LABELS={
    earthquake:[N("Earthquake"),N("largest magnitude inside a radius of the insured address")],
    drought:[N("Drought"),N("cumulative rainfall over a growing season at a station")],
    flight_delay:[N("Flight delay"),N("arrival delay in minutes, and cancellation")],
    vehicle_flood:[N("Vehicle flood"),N("largest daily rainfall where the vehicle is kept")],
    storm:[N("Storm"),N("largest daily wind speed where the home stands")],
  };
  $("co-perils").innerHTML=Object.keys(PERIL_LABELS).map(function(key){
    return '<button class="opt" type="button" data-peril="'+key+'" aria-pressed="true">'+
      '<span class="lead">'+esc(key.slice(0,2).toUpperCase())+'</span>'+
      '<span><span class="t">'+tspan(PERIL_LABELS[key][0])+'</span>'+
      '<span class="s">'+tspan(PERIL_LABELS[key][1])+'</span></span>'+
      '<span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg></span></button>';
  }).join("");
  $("co-settlement").innerHTML=["fiat","stablecoin"].map(function(a,i){
    return '<button class="opt" type="button" data-asset="'+a+'" aria-pressed="'+(i===0)+'">'+
      '<span class="lead">'+(a==="fiat"?"¤":"$")+'</span>'+
      '<span><span class="t">'+tspan(a==="fiat"?N("Local currency"):N("Stablecoin"))+'</span>'+
      '<span class="s">'+tspan(a==="fiat"
        ? N("what most regulators require of a consumer policy")
        : N("where the law permits settling in a digital asset"))+'</span></span>'+
      '<span class="tick"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5 9 17.5 20 6.5"/></svg></span></button>';
  }).join("");

  Array.prototype.forEach.call(
    document.querySelectorAll("#co-perils .opt, #co-settlement .opt"),
    function(b){
      b.addEventListener("click",function(){
        b.setAttribute("aria-pressed", b.getAttribute("aria-pressed")==="true"?"false":"true");
      });
    });

  function money3(id,valueId,lo,hi){
    var input=$(id);
    function show(){
      $(valueId).textContent=f0.format(carrierAmount(+input.value,lo,hi))+" USDC";
    }
    input.addEventListener("input",show); show();
  }
  money3("co-limit","co-limit-val",25000,5000000);
  money3("co-capacity","co-capacity-val",500000,200000000);
  $("co-fee").addEventListener("input",function(){
    $("co-fee-val").textContent=pct(+$("co-fee").value/200,1);
  });
  $("co-fee-val").textContent=pct(+$("co-fee").value/200,1);

  $("carrier-form").addEventListener("submit",function(e){
    e.preventDefault(); submitCarrier();
  });

  // A reinsurer holds no licence where the buyer is, so the licence fields
  // are hidden rather than left there looking as if they needed filling in.
  function roleChanged(){
    var re=$("co-role").value==="reinsurer";
    $("co-licence").hidden=re;
    $("co-settlement-field").hidden=re;
    $("co-reinsurer-note").hidden=!re;
  }
  $("co-role").addEventListener("change",roleChanged);
  roleChanged();
}

function pressedValues(selector,attribute){
  return Array.prototype.filter.call(
    document.querySelectorAll(selector),
    function(n){ return n.getAttribute("aria-pressed")==="true"; }
  ).map(function(n){ return n.dataset[attribute]; });
}

/* What each uploaded document is, chosen by the company rather than guessed
   from a file name, because the operator's checklist reads it by kind. */
var DOC_KINDS={licence_certificate:N("licence certificate"),register_extract:N("register extract"),authorisation_letter:N("letter of authorisation"),
  trade_registry_gazette:N("trade registry gazette"),signature_circular:N("signature circular"),membership_proof:N("association membership proof"),
  solvency_report:N("solvency report or audited accounts"),data_agreement:N("data processing agreement"),other:N("other document")};
function guessKind(name){
  return /licen|ruhsat|lizenz/i.test(name)?"licence_certificate":/gazete|gazette/i.test(name)?"trade_registry_gazette":
    /imza|signat|zirk/i.test(name)?"signature_circular":/regist|sicil|kay/i.test(name)?"register_extract":
    /tsb|birli|member|mitglied/i.test(name)?"membership_proof":/solven|yeterli|denetim|audit/i.test(name)?"solvency_report":
    /kvkk|gdpr|veri|data/i.test(name)?"data_agreement":"other";
}
function evidenceKindFor(file){
  var sel=document.querySelector('.files select[data-file="'+CSS.escape(file.name)+'"]')
       || document.querySelector('#co-evidence-kinds select[data-file="'+CSS.escape(file.name)+'"]');
  return sel?sel.value:guessKind(file.name);
}
/* ---------------- choosing files ----------------
   The browser's own file control is a grey button and a sentence saying
   nothing was chosen. In its place: an area to drop onto or press, and what
   was chosen listed as rows that say how large each one is and can be taken
   back out. The input itself stays where it was and keeps the files, so
   everything that reads input.files reads the same thing; only its own
   control is covered. It stays reachable by keyboard, since the input is
   what is focused and the area draws the ring. */
var FILE_ICON='<svg class="doc" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M14 3v5h5"/><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/></svg>';
function fileSize(n){
  return n >= 1048576 ? (n/1048576).toFixed(1)+" MB" : Math.max(1,Math.round(n/1024))+" KB";
}
function setFiles(input, files){
  var box=new DataTransfer();
  files.forEach(function(f){ box.items.add(f); });
  input.files=box.files;
  input.dispatchEvent(new Event("change",{bubbles:true}));
}
function renderChosen(input){
  var list=input._chosen; if(!list)return;
  var files=Array.prototype.slice.call(input.files||[]);
  list.innerHTML=files.map(function(f,i){
    return '<div class="filerow">'+FILE_ICON+
      '<span class="nm">'+esc(f.name)+'<small>'+esc(fileSize(f.size))+'</small></span>'+
      '<span data-slot="'+i+'"></span>'+
      '<button type="button" class="drop-out" data-out="'+i+'" aria-label="'+esc(t("Remove"))+'">×</button></div>';
  }).join("");
  Array.prototype.forEach.call(list.querySelectorAll("[data-out]"),function(b){
    b.addEventListener("click",function(){
      var keep=Array.prototype.slice.call(input.files||[]).filter(function(_,i){ return i!==+b.dataset.out; });
      setFiles(input,keep);
    });
  });
}
var DROPS=[];
function dropWords(zone){
  var words=zone.querySelector(".drop-words");
  if(words)words.innerHTML='<b>'+esc(t("Drop your files here"))+'</b>'+
    '<span class="fine">'+esc(t("or"))+' <u>'+esc(t("choose from this device"))+'</u></span>';
}
LANG_LISTENERS.push(function(){ DROPS.forEach(dropWords); });
function upgradeFileInput(input){
  if(!input||input._dropped)return;
  input._dropped=true;
  var zone=document.createElement("label");
  zone.className="drop";
  zone.innerHTML='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+
    '<path d="M12 16V4m0 0L8 8m4-4 4 4"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>'+
    '<span class="drop-words" style="display:grid;gap:4px;justify-items:center"></span>';
  input.parentNode.insertBefore(zone,input);
  zone.appendChild(input);
  DROPS.push(zone);
  dropWords(zone);
  var list=document.createElement("div");
  list.className="files";
  zone.parentNode.insertBefore(list,zone.nextSibling);
  input._chosen=list;
  ["dragenter","dragover"].forEach(function(name){
    zone.addEventListener(name,function(ev){ ev.preventDefault(); zone.classList.add("over"); });
  });
  ["dragleave","drop"].forEach(function(name){
    zone.addEventListener(name,function(ev){ ev.preventDefault(); zone.classList.remove("over"); });
  });
  zone.addEventListener("drop",function(ev){
    var dropped=Array.prototype.slice.call((ev.dataTransfer&&ev.dataTransfer.files)||[]);
    if(!dropped.length)return;
    var have=Array.prototype.slice.call(input.files||[]);
    setFiles(input, input.multiple ? have.concat(dropped) : dropped.slice(0,1));
  });
  input.addEventListener("change",function(){ renderChosen(input); });
  renderChosen(input);
}
function upgradeFileInputs(root){
  Array.prototype.forEach.call((root||document).querySelectorAll('input[type=file]'),function(input){
    upgradeFileInput(input);
  });
}
/* Every file control on the page, including the ones a render puts there
   later: watched rather than called for at each site, so a new one is never
   left as the browser's grey button by an oversight. */
(function(){
  upgradeFileInputs(document);
  if(!("MutationObserver" in window))return;
  var waiting=false;
  new MutationObserver(function(){
    if(waiting)return;
    waiting=true;
    requestAnimationFrame(function(){ waiting=false; upgradeFileInputs(document); });
  }).observe(document.body,{childList:true,subtree:true});
})();

/* What this company is asked for, from the protocol rather than from a list
   in the page, so a country is never shown a document it does not issue. */
var CO_DOCS={key:"",list:[]};
function carrierDocuments(){
  var country=($("co-domicile")||{}).value||"", role=($("co-role")||{}).value||"carrier";
  var key=country+"/"+role;
  if(CO_DOCS.key===key)return Promise.resolve(CO_DOCS.list);
  return api("/api/carriers/documents?country="+encodeURIComponent(country)+"&role="+encodeURIComponent(role))
    .then(function(r){ CO_DOCS={key:key,list:r.documents||[]}; return CO_DOCS.list; },
          function(){ return CO_DOCS.list; });
}
function renderAskedDocuments(){
  var box=$("co-docs-asked");
  if(!box)return Promise.resolve();
  return carrierDocuments().then(function(list){
    box.innerHTML=list.filter(function(d){ return d.kind!=="other"; }).map(function(d){
      return '<li><b>'+esc(t(DOC_KINDS[d.kind]||d.kind))+'</b>'+
        (d.required?'':' <span class="pill">'+esc(t("if you have it"))+'</span>')+
        '<span class="fine">'+esc(ts(d.why||""))+'</span></li>';
    }).join("");
    renderEvidenceKinds();
  });
}
function renderEvidenceKinds(){
  var input=$("co-evidence"); if(!input)return;
  upgradeFileInput(input);
  var rows=input._chosen?input._chosen.querySelectorAll("[data-slot]"):[];
  var files=Array.prototype.slice.call(input.files||[]);
  var kinds=(CO_DOCS.list.length?CO_DOCS.list.map(function(d){return d.kind;}):Object.keys(DOC_KINDS));
  Array.prototype.forEach.call(rows,function(slot,i){
    var f=files[i]; if(!f)return;
    var g=guessKind(f.name);
    if(kinds.indexOf(g)<0)g=kinds[0];
    slot.innerHTML='<select data-file="'+esc(f.name)+'" aria-label="'+esc(t("What this document is"))+'">'+
      kinds.map(function(k){
        return '<option value="'+k+'"'+(k===g?' selected':'')+'>'+esc(t(DOC_KINDS[k]||k))+'</option>'; }).join("")+'</select>';
  });
  var old=$("co-evidence-kinds"); if(old)old.innerHTML="";
}
(function(){
  var dom=$("co-domicile"), role=$("co-role"), ev=$("co-evidence"), lic=$("co-country");
  // A company is nearly always licensed where it is domiciled, and the two
  // fields did not move together: choosing Türkiye left "licensed in" on
  // whatever it started at, which is the one field the register check is
  // made against. It follows the domicile until the person moves it
  // themselves, and then it is theirs and stays where they put it.
  var licenceChosen=false;
  if(lic)lic.addEventListener("change",function(){ licenceChosen=true; });
  if(dom)dom.addEventListener("change",function(){
    var tr=$("co-tr"); if(tr)tr.hidden=dom.value!=="TR";
    if(lic&&!licenceChosen&&dom.value)lic.value=dom.value;
    renderAskedDocuments();
  });
  if(role)role.addEventListener("change",renderAskedDocuments);
  if(ev)ev.addEventListener("change",renderEvidenceKinds);
  if(dom)LANG_LISTENERS.push(function(){ if(CO_DOCS.list.length)renderAskedDocuments(); });
})();
function submitCarrier(){
  var out=$("co-result"), button=$("co-submit");
  function fail(text){
    out.hidden=false; out.className="verdict no";
    out.innerHTML='<p>'+text+'</p>';
    button.disabled=false; button.textContent=t("Register");
  }

  var perils=pressedValues("#co-perils .opt","peril");
  var settlement=pressedValues("#co-settlement .opt","asset");
  var name=$("co-name").value.trim();
  if(!name)return fail(esc(t("A company has a name.")));
  if(!perils.length)return fail(esc(t("Choose at least one peril you will write.")));
  var role=$("co-role").value;
  if(role==="carrier"&&!settlement.length)
    return fail(esc(t("Choose what that licence permits you to settle in.")));
  if(role==="carrier"&&!$("co-authority").value.trim())
    return fail(esc(t("A carrier names the authority that supervises it.")));
  if(role==="carrier"&&!$("co-reference").value.trim())
    return fail(esc(t("A carrier gives its licence number, as the regulator records it.")));

  var lei=$("co-lei").value.trim().toUpperCase();
  if(lei&&!/^[A-Z0-9]{18}[0-9]{2}$/.test(lei))return fail(esc(t("An LEI is 20 characters: 18 letters or digits and 2 check digits.")));
  var files=Array.prototype.slice.call(($("co-evidence").files)||[]);
  if(files.length>4)return fail(esc(t("At most 4 documents.")));
  for(var fi=0;fi<files.length;fi++){
    if(files[fi].size>3000000)return fail(esc(t("Each document is at most 3 MB.")));
    if(["application/pdf","image/png","image/jpeg"].indexOf(files[fi].type)<0)return fail(esc(t("Documents are PDF, PNG or JPEG.")));
  }
  button.disabled=true; button.textContent=t("Registering…");
  var year=Math.floor(Date.now()/1000)+365*24*3600;
  var body={
    name:name, role:role, domicile:$("co-domicile").value,
    lei:lei, domain:$("co-domain").value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/\/.*$/,""),
    perils:perils,
    max_limit:carrierAmount(+$("co-limit").value,25000,5000000),
    max_term_days:400,
    capacity:carrierAmount(+$("co-capacity").value,500000,200000000),
    fronting_fee:(+$("co-fee").value)/200,
    contact:$("co-contact").value.slice(0,100),
    licences:role==="reinsurer"?[]:[{
      country:$("co-country").value,
      authority:$("co-authority").value.slice(0,100),
      reference:$("co-reference").value.slice(0,60),
      perils:perils, reach:$("co-reach").value,
      settlement:settlement, expires_at:year,
    }],
  };

  // The company signs its own registration, so the row has an owner who can
  // come back to it: the company page lists what this address registered.
  function readEvidence(){
    return Promise.all(files.map(function(f){
      return new Promise(function(resolve,reject){
        var r=new FileReader();
        r.onload=function(){ resolve({kind:evidenceKindFor(f),
          filename:f.name.slice(0,120), content_type:f.type, data:String(r.result).split(",")[1]||""}); };
        r.onerror=reject; r.readAsDataURL(f);
      });
    }));
  }
  body.mersis=($("co-mersis")||{}).value||""; body.tax_number=($("co-tax")||{}).value||"";
  var signedBody=(identity.address?Promise.resolve():chooseSignIn("company")).then(function(){
    setRole("company");
    return signIn();
  }).then(readEvidence).then(function(ev){
    body.evidence=ev;
  }).then(function(){
    var terms={name:body.name, role:body.role, domicile:body.domicile};
    return api("/api/auth/challenge",{method:"POST",body:{address:identity.address,purpose:"register",terms:terms}})
      .then(function(challenge){
        return sign(challenge.message).then(function(signature){
          body.address=identity.address; body.nonce=challenge.nonce; body.signature=signature;
          return body;
        });
      });
  });
  signedBody.then(function(body){
    return api("/api/carriers",{method:"POST",timeout:20000,body:body});
  }).then(function(reply){
    renderWho();
    var carrier=reply.carrier;
    out.hidden=false; out.className="verdict ok";
    out.innerHTML='<div class="vrow"><span class="pill">'+esc(t(COMPANY_STATUS[carrier.status]||carrier.status))+'</span>'+
      '<span>'+esc(ts(carrier.name))+'</span></div><p>'+tsHtml(reply.next)+'</p>'+
      '<p class="fine">'+t("Registered as {id}. It appears in the list above straight away, writing nothing, which is what a claim nobody has checked should look like.",
        {id:'<span class="mono">'+esc(carrier.carrier_id)+'</span>'})+'</p>'+
      domainProofHtml(reply.proof_file);
    button.disabled=false; button.textContent=t("Register another");
    api("/api/carriers",{timeout:9000}).then(function(list){
      $("carriers-out").innerHTML=companiesHtml(list);
    });
    // Signed in as a reviewer on this same page: the new registration is
    // waiting on you, so show it rather than a list read before it existed.
    if(OP.token) opLoad();
  },function(error){
    var payload=error&&error.payload;
    if(error&&/closed/.test(String(error.message||""))){ button.disabled=false; button.textContent=t("Register"); return; }
    fail((payload&&typeof payload.detail==="string")?tsHtml(payload.detail)
      :esc(t("The protocol did not accept that registration.")));
  });
}


/* ---------------- reviewing registrations ----------------
   The one step in this protocol a person performs, given a screen.

   It used to be a curl command, which meant the operator token was pasted into
   a terminal every time somebody registered, and the decision left no trace of
   who took it or what they checked. Here the token is presented once and
   exchanged for a session that expires, the licence numbers are put in front of
   the reviewer next to the regulator that would hold them, and activating is
   gated on the reviewer saying they checked. What they say is kept with the
   company, permanently.

   Nothing in this panel is a privilege the page grants. Without the token the
   API answers 401, and on a deployment with no token set at all it answers 404
   and this screen says so. */

/* OP is declared with the identity, above: the header reads it on load. */

function opStore(value){
  try { value ? sessionStorage.setItem("clause.op", value)
              : sessionStorage.removeItem("clause.op"); } catch(e){}
}
function opRestore(){
  try { return sessionStorage.getItem("clause.op"); } catch(e){ return null; }
}
function opStamp(seconds){
  if(!seconds) return "";
  return new Date(seconds*1000).toISOString().slice(0,16).replace("T"," ")+" UTC";
}

function bindOperator(){
  if(!OP.bound){
    OP.bound = true;
    $("op-signin").addEventListener("submit", function(e){ e.preventDefault(); opSignIn(); });
  }
  var kept = OP.token || opRestore();
  if(kept){ OP.token = kept; opLoad(); }
}

function opSignIn(){
  var out=$("op-result"), button=$("op-go"), field=$("op-token");
  var token=field.value.trim(), reviewer=$("op-name").value.trim();
  function fail(text){
    out.hidden=false; out.className="verdict no"; out.innerHTML='<p>'+esc(text)+'</p>';
    button.disabled=false; button.textContent=t("Sign in");
  }
  if(!token) return fail(t("The operator token is what this screen is behind."));

  button.disabled=true; button.textContent=t("Signing in…");
  api("/api/operator/session",{
    method:"POST", timeout:12000, body:{reviewer:reviewer},
    headers:{"x-operator-token":token},
  }).then(function(reply){
    /* Out of the page before anything else happens to it. */
    field.value=""; 
    OP.token=reply.token; OP.reviewer=reply.reviewer; OP.expires=reply.expires_at;
    opStore(reply.token);
    out.hidden=true; button.disabled=false; button.textContent=t("Sign in");
    opLoad();
  },function(error){
    var status=error&&error.status;
    if(status===404) return fail(t("This deployment has no operator token set, so "+
      "there is nothing to sign in to. Set CLAUSE_OPERATOR_TOKEN on the server "+
      "and restart it."));
    if(status===401) return fail(t("That token is not the operator token."));
    if(status===429) return fail(t("Too many attempts. Wait fifteen minutes."));
    fail(t("The protocol did not answer."));
  });
}

function opSignOut(){
  var token=OP.token;
  OP.token=null; OP.reviewer=""; OP.expires=0; opStore(null);
  $("op-work").hidden=true; $("op-work").innerHTML="";
  $("op-signin").hidden=false;
  if(token) api("/api/operator/session",{method:"DELETE",token:token,timeout:8000})
    .then(function(){},function(){});
}

function opLoad(){
  var work=$("op-work");
  work.hidden=false;
  work.innerHTML='<div class="panel" style="padding:22px">'+esc(t("Reading the registry…"))+'</div>';
  Promise.all([
    api("/api/operator/carriers",{token:OP.token,timeout:12000}),
    api("/api/operator/overview",{token:OP.token,timeout:12000}).catch(function(){ return null; }),
    api("/api/operator/payouts",{token:OP.token,timeout:12000}).catch(function(){ return null; }),
    api("/api/operator/partners",{token:OP.token,timeout:12000}).catch(function(){ return null; }),
    api("/api/review/applications",{token:OP.token,timeout:12000}).catch(function(){ return null; }),
    api("/api/operator/funding",{token:OP.token,timeout:12000}).catch(function(){ return null; }),
    api("/api/operator/statements"+(OP.month?"?month="+encodeURIComponent(OP.month):""),{token:OP.token,timeout:20000}).catch(function(){ return null; }),
  ]).then(function(both){
    var payload=both[0]; OP.overview=both[1]; OP.payouts=both[2]; OP.partners=both[3]; OP.apps=both[4]; OP.funding=both[5]; OP.platform=both[6];
    OP.reviewer=payload.reviewer||OP.reviewer;
    $("op-signin").hidden=true;
    ensureReadingKey("/api/operator/reading-key",{token:OP.token});
    work.innerHTML=opHtml(payload);
    opBindCards();
    bindVetting(work,{token:OP.token},opLoad);
    opBindTabs();
    opBindMoney();
    opBindPlatform();
    var opDesk=$("op-desk"); if(opDesk)bindDesk(opDesk,"operator","/api/operator/policies",{token:OP.token},true);
    bindReview($("op-work"),{token:OP.token},opLoad);
  },function(error){
    if(error&&error.status===401){
      OP.token=null; opStore(null); renderWho();
      work.hidden=true; work.innerHTML="";
      $("op-signin").hidden=false;
      var out=$("op-result");
      out.hidden=false; out.className="verdict";
      out.innerHTML='<p>'+esc(t("That session ended. Signing in again takes the token once more."))+'</p>';
      return;
    }
    work.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("The protocol did not answer."))+'</p></div>';
  });
}

function opHtml(payload){
  var companies=payload.companies||[];
  var pending=companies.filter(function(c){ return c.status==="pending"; });
  var rest=companies.filter(function(c){ return c.status!=="pending"; });

  var out='<div class="op-bar"><span class="who">'+esc(payload.reviewer)+'</span>'+
    '<span class="fine">'+esc(OP.expires?t("session until {time}",{time:opStamp(OP.expires)}):t("signed in"))+
    '</span><span class="sp"></span>'+
    '<button class="btn btn-ghost btn-sm" type="button" id="op-refresh">'+esc(t("Refresh"))+'</button>'+
    '<button class="btn btn-line btn-sm" type="button" id="op-out">'+esc(t("Sign out"))+'</button></div>';

  var ov=OP.overview;
  if(ov){
    var tt=ov.totals;
    out+='<div class="stats">'+
      statHtml(f0.format(tt.buyers),t("buyers"))+
      statHtml(f0.format(tt.policies),t("policies, {n} open",{n:f0.format(tt.open)}))+
      statHtml(money(tt.premiums),t("premiums, USDC"))+
      statHtml(money(tt.paid_out),t("paid out, USDC"))+
      statHtml(f0.format(tt.companies),t("companies, {n} pending",{n:f0.format(tt.pending)}))+
      '</div>';
  }
  var waiting=OP.apps?OP.apps.waiting:0;
  if(!OP.tab&&waiting)OP.tab="apps";
  var tab=OP.tab||"companies";
  if(waiting&&tab!=="apps")out+='<div class="verdict" style="margin-bottom:14px"><p>'+
    esc(t("{n} applications are waiting for a decision.",{n:waiting}))+' <a href="#/admin" data-goto-tab="apps">'+esc(t("Review them"))+'</a></p></div>';
  out+='<div class="tabs" role="tablist">'+
    '<button role="tab" data-tab="companies" aria-selected="'+(tab==="companies")+'">'+esc(t("Companies"))+'</button>'+
    '<button role="tab" data-tab="buyers" aria-selected="'+(tab==="buyers")+'">'+esc(t("Buyers and policies"))+'</button>'+
    (OP.apps?'<button role="tab" data-tab="apps" aria-selected="'+(tab==="apps")+'">'+esc(t("Applications ({n})",{n:OP.apps.waiting}))+'</button>':'')+
    (OP.payouts?'<button role="tab" data-tab="payouts" aria-selected="'+(tab==="payouts")+'">'+esc(t("Payouts to banks ({n})",{n:OP.payouts.open.length}))+'</button>':'')+
    (OP.partners?'<button role="tab" data-tab="partners" aria-selected="'+(tab==="partners")+'">'+esc(t("Partners"))+'</button>':'')+
    (OP.funding?'<button role="tab" data-tab="funding" aria-selected="'+(tab==="funding")+'">'+esc(t("Money in ({n})",{n:OP.funding.waiting.length}))+'</button>':'')+
    (OP.platform?'<button role="tab" data-tab="platform" aria-selected="'+(tab==="platform")+'">'+esc(t("Platform and statements"))+'</button>':'')+
    '</div>';
  if(tab==="platform"&&OP.platform) return out+opPlatformHtml(OP.platform);
  if(tab==="buyers") return out+'<div id="op-desk"><p class="fine">'+esc(t("Reading the book…"))+'</p></div>';
  if(tab==="payouts"&&OP.payouts) return out+opPayoutsHtml(OP.payouts);
  if(tab==="apps"&&OP.apps) return out+'<div class="verdict" style="margin-bottom:16px"><p>'+
    esc(t("Each application waits for the issuing company's checks. On a demonstration the stand in companies have nobody of their own, so you decide for them here: confirm each check you did, then approve, or reject with a reason the applicant will read."))+
    '</p></div>'+reviewHtml(OP.apps.applications||[]);
  if(tab==="partners"&&OP.partners) return out+opPartnersHtml(OP.partners);
  if(tab==="funding"&&OP.funding) return out+opFundingHtml(OP.funding);

  out+='<div class="verdict" style="margin-bottom:18px"><p>'+tsHtml(payload.instruction)+'</p></div>';
  var att=(ov&&ov.attention)||[];
  if(att.length){
    out+='<div class="verdict no" style="margin-bottom:18px"><p><b>'+esc(t("Due again ({n})",{n:att.length}))+'</b></p><ul style="margin:6px 0 0 18px;display:grid;gap:4px">'+att.map(function(a){
      var bits=[];
      if(a.review_overdue)bits.push(t("checks overdue since {time}",{time:opStamp(a.review_due_at)}));
      else if(a.review_due_soon)bits.push(t("checks due {time}",{time:opStamp(a.review_due_at)}));
      if(a.licences_expiring.length)bits.push(t("licence expiring: {refs}",{refs:a.licences_expiring.join(", ")}));
      if(a.licences_lapsed.length)bits.push(t("licence lapsed: {refs}",{refs:a.licences_lapsed.join(", ")}));
      return '<li>'+esc(ts(a.name))+' · '+esc(bits.join(" · "))+'</li>'; }).join("")+'</ul></div>';
  }

  out+='<h2 style="font-size:17px;margin:0 0 12px">'+esc(t("Waiting on you ({n})",{n:pending.length}))+'</h2>';
  out+= pending.length ? pending.map(opCard).join("")
      : '<div class="panel" style="padding:20px"><p>'+esc(t("Nothing pending. Every registration here has been decided."))+'</p></div>';

  var stand=rest.filter(function(c){ return c.specimen&&c.carrier_id==="specimen-"+String(c.domicile||"").toLowerCase(); });
  var folded=specimenList(stand);
  if(folded) rest=rest.filter(function(c){ return stand.indexOf(c)<0; });
  if(rest.length||folded){
    out+='<h2 style="font-size:17px;margin:32px 0 12px">'+esc(t("Already decided ({n})",{n:rest.length+stand.length}))+'</h2>'+
      rest.map(opCard).join("")+(folded||"");
  }
  return out;
}

/* ---------------- the desk: a book, worked ----------------
   Search, filters, the ones ending soon, exposure by province, a file. One
   renderer for a company's own paper and for the operator's whole book. */
var DESKS={};
var DESK_STATUS=[["",N("every status")],["open",N("open")],["paid",N("paid")],["lapsed",N("ended, no trigger")],["expired",N("expired, refunded")],["cancelled",N("cancelled")]];
var DESK_SORT=[["bought_at",N("newest first")],["ends_at",N("ending soonest")],["limit",N("largest cover")],["premium",N("largest premium")],["policy_id",N("policy number")]];
function deskTable(rows,admin){
  if(!rows||!rows.length) return '<div class="panel" style="padding:20px"><p>'+esc(t("Nothing matches."))+'</p></div>';
  var head='<tr><th>'+esc(t("Policy"))+'</th><th>'+esc(t("Cover"))+'</th><th>'+esc(t("Province"))+'</th><th>'+esc(t("Buyer"))+'</th>'+
    (admin?'<th>'+esc(t("Issued by"))+'</th>':'')+
    '<th class="num">'+esc(t("Limit"))+'</th><th class="num">'+esc(t("Premium"))+'</th><th>'+esc(t("Status"))+'</th><th>'+esc(t("Ends"))+'</th></tr>';
  var body=rows.map(function(p){
    var ends=p.days_left===null||p.days_left===undefined?esc(opStamp(p.ends_at)):
      (p.renewal_due?'<b>':'')+esc(t("in {n} days",{n:Math.max(0,Math.round(p.days_left))}))+(p.renewal_due?'</b> <span class="pill">'+esc(t("renewal"))+'</span>':'');
    return '<tr><td class="mono"><a href="#/proof/'+encodeURIComponent(p.policy_id)+'">'+esc(p.policy_id)+'</a></td>'+
      '<td><b>'+esc(perilWords([p.peril]))+'</b><br><span class="fine">'+esc(ts(p.subject))+(p.address?'<br>'+esc(p.address):'')+'</span></td>'+
      '<td>'+esc(p.province||"—")+'</td><td class="mono">'+esc(p.holder)+'</td>'+
      (admin?'<td>'+esc(p.carrier?ts(p.carrier):t("the pool alone"))+'</td>':'')+
      '<td class="num">'+money(p.limit)+'</td><td class="num">'+money(p.premium)+'</td>'+
      '<td>'+esc(t(POLICY_STATUS[p.status]||p.status))+(p.payout?' · '+money(p.payout):'')+'</td>'+
      '<td>'+ends+'</td></tr>';
  }).join("");
  return '<div class="tbl-wrap"><table class="tbl"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>';
}
function deskHtml(id,r,st,admin){
  var sm=r.summary||{};
  var sel=function(name,opts,value){ return '<select class="dlg-input" style="max-width:220px" data-desk-'+name+'="'+esc(id)+'">'+opts.map(function(o){
    return '<option value="'+esc(o[0])+'"'+(o[0]===value?' selected':'')+'>'+esc(t(o[1]))+'</option>'; }).join("")+'</select>'; };
  var provs=[["",N("every province")]].concat((r.provinces||[]).map(function(p){return [p,p];}));
  var out='<div class="stats">'+
    statHtml(f0.format(sm.open||0),t("open policies"))+
    statHtml(money(sm.in_force||0),t("in force, USDC"))+
    statHtml(f0.format(sm.renewals_due||0),t("ending within 30 days"))+
    statHtml(money(sm.renewals_in_force||0),t("of cover to renew, USDC"))+
    statHtml(f0.format(sm.provinces||0),t("provinces"))+'</div>';
  out+='<div class="vrow" style="gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0">'+
    '<input class="dlg-input" style="max-width:280px" placeholder="'+esc(t("Find: policy number, street, place, buyer"))+'" value="'+esc(st.q||"")+'" data-desk-q="'+esc(id)+'">'+
    sel("status",DESK_STATUS,st.status||"")+sel("province",provs,st.province||"")+sel("sort",DESK_SORT,st.sort||"bought_at")+
    '<label class="fine" style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-desk-due="'+esc(id)+'"'+(st.due?' checked':'')+'> '+esc(t("ending within 30 days"))+'</label>'+
    '<button class="btn btn-line btn-sm" type="button" style="flex:0 0 auto" data-desk-csv="'+esc(id)+'">'+esc(t("Download CSV"))+'</button></div>';
  var by=r.by_province||[];
  if(by.length&&!st.q&&!st.status&&!st.province&&!st.due){
    out+='<h2 style="font-size:16px;margin:16px 0 10px">'+esc(t("Open cover by province"))+'</h2><div class="tbl-wrap"><table class="tbl" style="min-width:0"><thead><tr><th>'+esc(t("Province"))+'</th><th class="num">'+esc(t("Policies"))+'</th><th class="num">'+esc(t("In force"))+'</th><th class="num">'+esc(t("Premiums"))+'</th><th>'+esc(t("Perils"))+'</th></tr></thead><tbody>'+
      by.map(function(g){ return '<tr><td><a href="#" data-desk-pick="'+esc(id)+'" data-province="'+esc(g.province)+'">'+esc(g.province||t("not placed"))+'</a></td><td class="num">'+f0.format(g.policies)+'</td><td class="num">'+money(g.in_force)+'</td><td class="num">'+money(g.premiums)+'</td><td class="fine">'+esc(Object.keys(g.perils).map(function(k){return perilWords([k])+" "+g.perils[k];}).join(", "))+'</td></tr>'; }).join("")+
      '</tbody></table></div>';
  }
  out+='<h3 style="font-size:16px;margin:16px 0 10px">'+esc(t("{n} policies",{n:f0.format(r.total||0)}))+(r.total>(r.limit||100)?' <span class="fine">'+esc(t("showing the first {n}",{n:r.limit||100}))+'</span>':'')+'</h3>'+deskTable(r.policies,admin);
  return out;
}
function bindDesk(holder,id,base,auth,admin){
  var st=DESKS[id]||(DESKS[id]={q:"",status:"",province:"",sort:"bought_at",due:false});
  function query(csv){
    var qs=[];
    if(st.q)qs.push("q="+encodeURIComponent(st.q)); if(st.status)qs.push("status="+encodeURIComponent(st.status));
    if(st.province)qs.push("province="+encodeURIComponent(st.province)); if(st.sort)qs.push("sort="+encodeURIComponent(st.sort));
    if(st.due)qs.push("due_within=30"); if(csv)qs.push("format=csv");
    return base+(base.indexOf("?")>=0?"&":"?")+qs.join("&");
  }
  function load(){
    var o={timeout:30000}; for(var k in auth)o[k]=auth[k];
    api(query(false),o).then(function(r){
      holder.innerHTML=deskHtml(id,r,st,admin);
      var q=holder.querySelector("[data-desk-q]"), timer=null;
      q.addEventListener("input",function(){ clearTimeout(timer); timer=setTimeout(function(){ st.q=q.value.trim(); load(); },350); });
      ["status","province","sort"].forEach(function(name){
        var el=holder.querySelector("[data-desk-"+name+"]"); el.addEventListener("change",function(){ st[name]=el.value; load(); });
      });
      var due=holder.querySelector("[data-desk-due]"); due.addEventListener("change",function(){ st.due=due.checked; load(); });
      Array.prototype.forEach.call(holder.querySelectorAll("[data-desk-pick]"),function(a){
        a.addEventListener("click",function(e){ e.preventDefault(); st.province=a.dataset.province; load(); });
      });
      var dl=holder.querySelector("[data-desk-csv]"); dl.addEventListener("click",function(){
        dl.disabled=true; downloadCsv(query(true),auth,id+"-policies.csv").then(function(){ dl.disabled=false; },function(e){ dl.disabled=false; dl.textContent=refusalText(e); });
      });
      var focus=holder.querySelector("[data-desk-q]"); if(st.q&&focus){ focus.focus(); focus.setSelectionRange(focus.value.length,focus.value.length); }
    },function(e){ holder.innerHTML='<p class="fine">'+esc(refusalText(e))+'</p>'; });
  }
  load();
}

/* A download that needs the session: fetched with it, then handed to the
   browser as a file, since a plain link cannot carry a bearer token. */
function downloadCsv(path, opts, filename){
  var o={raw:true,timeout:30000}; for(var k in opts)o[k]=opts[k];
  return api(path,o).then(function(blob){
    var url=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=url; a.download=filename; document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(url); a.remove(); },1000);
  });
}
function monthLabel(m){
  var p=String(m||"").split("-"); if(p.length<2)return m||"";
  return new Date(Date.UTC(+p[0],+p[1]-1,1)).toLocaleDateString(LOCALES[LANG]||"en-US",{year:"numeric",month:"long",timeZone:"UTC"});
}
/* One company's month, as a statement: the totals, then the lines. */
var FEE_KINDS={fronting_fee:N("fronting fee received"),fronting_fee_returned:N("fronting fee returned"),platform_fee:N("platform fee"),platform_fee_returned:N("platform fee returned")};
function statementHtml(st, months, chosen, who){
  var sel=months.length?'<select class="dlg-input" style="max-width:220px" data-statement-month="'+esc(who)+'">'+months.map(function(m){
    return '<option value="'+esc(m)+'"'+(m===chosen?' selected':'')+'>'+esc(monthLabel(m))+'</option>'; }).join("")+'</select>':'';
  var rows=[[t("Policies written"),f0.format(st.policies)],[t("Premiums written"),money(st.premiums_written)+" USDC"],
    [t("Fronting fees received"),money(st.fronting_fees)+" USDC"],[t("Fronting fees returned"),money(st.fronting_fees_returned)+" USDC"],
    [t("Platform fee, deducted"),money(st.platform_fees)+" USDC"],[t("Platform fee, returned"),money(st.platform_fees_returned)+" USDC"],
    [t("Net to the company"),money(st.net_to_company)+" USDC"]];
  return '<div class="vrow" style="gap:10px;align-items:center;flex-wrap:wrap">'+sel+
    '<button class="btn btn-line btn-sm" type="button" style="flex:0 0 auto" data-statement-csv="'+esc(who)+'">'+esc(t("Download CSV"))+'</button></div>'+
    '<div class="tbl-wrap" style="margin-top:10px"><table class="tbl" style="min-width:0"><tbody>'+rows.map(function(r){
      return '<tr><td>'+esc(r[0])+'</td><td class="num"><b>'+esc(r[1])+'</b></td></tr>'; }).join("")+'</tbody></table></div>'+
    (st.lines&&st.lines.length?'<div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>'+esc(t("When"))+'</th><th>'+esc(t("Policy"))+'</th><th>'+esc(t("Entry"))+'</th><th class="num">'+esc(t("Premium"))+'</th><th class="num">'+esc(t("Amount"))+'</th></tr></thead><tbody>'+
      st.lines.map(function(l){ return '<tr><td class="fine">'+esc(opStamp(l.at))+'</td><td class="mono">'+esc(l.policy_id)+'</td><td>'+esc(t(FEE_KINDS[l.kind]||l.kind))+'</td><td class="num">'+esc(money(l.premium))+'</td><td class="num">'+esc((l.kind.indexOf("returned")>=0?"−":"")+money(l.amount))+'</td></tr>'; }).join("")+
      '</tbody></table></div>':'<p class="fine">'+esc(t("No entries this month."))+'</p>');
}
/* What the platform earned, and every company's statement for the month. */
function opPlatformHtml(p){
  var pf=p.platform||{}, months=p.months||[], month=p.month;
  var out='<div class="stats">'+
    statHtml(pct(pf.rate||0.01,0),t("of each premium, from the company's fee"))+
    statHtml(money(pf.platform_fees||0),t("platform fees taken, USDC"))+
    statHtml(money(pf.platform_fees_returned||0),t("returned with refunds, USDC"))+
    statHtml(money(pf.net||0),t("net, USDC"))+
    statHtml(money(pf.balance||0),t("platform account balance, USDC"))+'</div>';
  out+='<div class="verdict" style="margin-bottom:16px"><p>'+esc(t("The platform is paid by the companies that write here, out of their fronting fee, the moment the fee is paid; buyers pay the pool's price and nothing on top for the platform. A fee that goes back to a buyer takes the platform's share back with it. Each company sees the same statement on its own page."))+'</p></div>';
  var by=pf.by_month||{};
  out+='<h3 style="font-size:16px;margin:0 0 10px">'+esc(t("By month"))+'</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>'+esc(t("Month"))+'</th><th class="num">'+esc(t("Policies"))+'</th><th class="num">'+esc(t("Premiums"))+'</th><th class="num">'+esc(t("Platform fees"))+'</th><th class="num">'+esc(t("Returned"))+'</th></tr></thead><tbody>'+
    Object.keys(by).map(function(m){ var r=by[m]; return '<tr><td>'+esc(monthLabel(m))+'</td><td class="num">'+f0.format(r.policies)+'</td><td class="num">'+money(r.premiums)+'</td><td class="num">'+money(r.platform_fees)+'</td><td class="num">'+money(r.platform_fees_returned)+'</td></tr>'; }).join("")+
    '</tbody></table></div>';
  out+='<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Statements for {month}",{month:monthLabel(month)}))+'</h3>'+
    '<div class="vrow" style="gap:10px;align-items:center;flex-wrap:wrap">'+
    (months.length?'<select class="dlg-input" style="max-width:220px" id="op-month">'+months.map(function(m){ return '<option value="'+esc(m)+'"'+(m===month?' selected':'')+'>'+esc(monthLabel(m))+'</option>'; }).join("")+'</select>':'')+
    '<button class="btn btn-line btn-sm" type="button" style="flex:0 0 auto" data-op-csv="">'+esc(t("Download CSV, all companies"))+'</button></div>';
  var sts=p.statements||[];
  out+=sts.length?'<div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>'+esc(t("Company"))+'</th><th class="num">'+esc(t("Policies"))+'</th><th class="num">'+esc(t("Premiums"))+'</th><th class="num">'+esc(t("Fronting fees"))+'</th><th class="num">'+esc(t("Platform fee"))+'</th><th class="num">'+esc(t("Net to the company"))+'</th><th></th></tr></thead><tbody>'+
    sts.map(function(st){ return '<tr><td>'+esc(ts(st.carrier))+'</td><td class="num">'+f0.format(st.policies)+'</td><td class="num">'+money(st.premiums_written)+'</td><td class="num">'+money(st.fronting_fees-st.fronting_fees_returned)+'</td><td class="num">'+money(st.platform_fees-st.platform_fees_returned)+'</td><td class="num"><b>'+money(st.net_to_company)+'</b></td><td><button class="btn btn-ghost btn-sm" type="button" data-op-csv="'+esc(st.carrier_id)+'">CSV</button></td></tr>'; }).join("")+
    '</tbody></table></div>':'<p class="fine">'+esc(t("No entries this month."))+'</p>';
  return out;
}
function opBindPlatform(){
  var sel=$("op-month"); if(sel)sel.addEventListener("change",function(){ OP.month=sel.value; opLoad(); });
  Array.prototype.forEach.call(document.querySelectorAll("#op-work [data-op-csv]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true; var id=b.dataset.opCsv, month=(OP.platform||{}).month||"";
      downloadCsv("/api/operator/statements?format=csv&month="+encodeURIComponent(month)+(id?"&carrier_id="+encodeURIComponent(id):""),{token:OP.token},(id||"all")+"-"+month+".csv")
        .then(function(){ b.disabled=false; },function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
}
function statHtml(value,label){ return '<div class="stat"><b>'+esc(value)+'</b><span>'+esc(label)+'</span></div>'; }
function opBindTabs(){
  Array.prototype.forEach.call(document.querySelectorAll('#op-work .tabs button'),function(b){
    b.addEventListener("click",function(){ OP.tab=b.dataset.tab; opLoad(); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('#op-work [data-goto-tab]'),function(a){
    a.addEventListener("click",function(e){ e.preventDefault(); OP.tab=a.dataset.gotoTab; opLoad(); });
  });
}
/* One table for the admin's view of every buyer and a company's view of its
   own paper. Buyers are shortened addresses: nobody here needs more. */
function policiesTable(rows,admin){
  if(!rows||!rows.length) return '<div class="panel" style="padding:20px"><p>'+esc(t("No policies yet."))+'</p></div>';
  var head='<tr><th>'+esc(t("Policy"))+'</th><th>'+esc(t("Cover"))+'</th><th>'+esc(t("Buyer"))+'</th>'+
    (admin?'<th>'+esc(t("Issued by"))+'</th>':'')+
    '<th class="num">'+esc(t("Limit"))+'</th><th class="num">'+esc(t("Premium"))+'</th><th>'+esc(t("Status"))+'</th><th>'+esc(t("Bought"))+'</th></tr>';
  var body=rows.map(function(p){
    return '<tr><td class="mono"><a href="#/proof/'+encodeURIComponent(p.policy_id)+'">'+esc(p.policy_id)+'</a></td>'+
      '<td><b>'+esc(perilWords([p.peril]))+'</b><br><span class="fine">'+esc(ts(p.subject))+'</span></td><td class="mono">'+esc(p.holder)+'</td>'+
      (admin?'<td>'+esc(p.carrier?ts(p.carrier):t("the pool alone"))+'</td>':'')+
      '<td class="num">'+money(p.limit)+'</td><td class="num">'+money(p.premium)+'</td>'+
      '<td>'+esc(t(POLICY_STATUS[p.status]||p.status))+(p.payout?' · '+money(p.payout):'')+'</td>'+
      '<td>'+esc(opStamp(p.bought_at))+'</td></tr>';
  }).join("");
  return '<div class="tbl-wrap"><table class="tbl"><thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>';
}

/* ---------------- a company's own page ---------------- */
function renderCompany(){
  var box=$("company-out");
  if(!link.checked){ whenLinked().then(renderCompany); return; }
  if(!link.live){ box.innerHTML=minePanel(t("Not connected"),t("The protocol did not answer."),""); return; }
  if(!identity.token){
    box.innerHTML=minePanel(t("Sign in as your company"),
      t("Sign in with the account you registered the company from. Its review status and the cover written on its paper are here."),
      '<button class="btn btn-primary" type="button" id="company-go">'+esc(t("Sign in"))+'</button> '+
      '<a class="btn btn-line" href="#/insurers">'+esc(t("Register a company"))+'</a>');
    $("company-go").addEventListener("click",function(){
      setRole("company");
      (identity.address?signIn():chooseSignIn("company")).then(function(){ renderWho(); renderCompany(); },function(){});
    });
    return;
  }
  box.innerHTML='<div class="panel" style="padding:22px">'+esc(t("Reading the registry…"))+'</div>';
  api("/api/company",{token:identity.token,timeout:12000}).then(function(reply){
    var list=reply.companies||[];
    var demo=reply.demo&&reply.demo.on?specimenDesksHtml(reply.demo.specimens||[]):"";
    if(!list.length){
      box.innerHTML=minePanel(t("No company registered from this account"),
        t("Register your company with this same sign in, and it will appear here, pending review."),
        '<a class="btn btn-primary" href="#/insurers">'+esc(t("Register a company"))+'</a>')+demo;
      bindSpecimenDesks(box);
      return;
    }
    box.innerHTML=list.map(companyHtml).join("")+'<h3 style="font-size:17px;margin:30px 0 12px">'+
      esc(t("Applications for your paper"))+'</h3><div id="company-apps"></div>'+demo;
    bindStatements(box,{token:identity.token});
    bindCompanyComplaints(box,{token:identity.token});
    bindBordereaux(box,{token:identity.token});
    bindVetting(box,{token:identity.token},renderCompany);
    bindMoreDocs(box,{token:identity.token},renderCompany);
    Array.prototype.forEach.call(box.querySelectorAll("[data-desk-for]"),function(h){
      bindDesk(h,h.dataset.deskFor,"/api/company/policies?carrier_id="+encodeURIComponent(h.dataset.deskFor),{token:identity.token},false);
    });
    bindSpecimenDesks(box);
    ensureReadingKey("/api/auth/reading-key",{token:identity.token});
    bindVerification(box,{token:identity.token},renderCompany);
    api("/api/review/applications",{token:identity.token}).then(function(r){
      var holder=$("company-apps"); if(!holder)return;
      var rows=r.applications||[];
      holder.innerHTML=rows.length?reviewHtml(rows):'<p class="fine">'+esc(t("Nothing is waiting for you."))+'</p>';
      bindReview(holder,{token:identity.token},renderCompany);
    },function(){});
  },function(error){
    if(error&&error.status===401){ setSession(null); renderCompany(); return; }
    box.innerHTML=minePanel(t("Could not read it"),t("The protocol did not answer."),"");
  });
}
var DESK_COUNTRY="";
/* The one line the company publishes on its own domain to prove the
   registration is its own. */
function domainProofHtml(proof){
  if(!proof||!proof.url||!proof.content)return "";
  return '<div class="verdict" style="margin-top:12px"><p><b>'+esc(t("Prove the domain is yours."))+'</b> '+
    esc(t("Publish this one line, exactly, at the address below. The protocol fetches it and marks the domain confirmed; the reviewer sees that whoever registered can publish under your name."))+'</p>'+
    '<p class="mono" style="font-size:13px;word-break:break-all">'+esc(proof.url)+'</p>'+
    '<p class="mono" style="font-size:13px;word-break:break-all;background:var(--paper-2,#f4f2ee);padding:8px 10px;border-radius:8px">'+esc(proof.content)+'</p>'+
    '<p class="fine">'+esc(t("Then press \"Run the automatic checks again\" on your company page. Your LEI is looked up at GLEIF without you doing anything."))+'</p></div>';
}
function specimenDesksHtml(rows){
  if(!rows.length)return "";
  var countries={}; rows.forEach(function(r){ r.countries.forEach(function(c){ countries[c]=1; }); });
  var codes=Object.keys(countries).sort(function(a,b){ return regionName(a).localeCompare(regionName(b)); });
  var shown=rows.filter(function(r){ return r.mine||r.waiting||(DESK_COUNTRY&&r.countries.indexOf(DESK_COUNTRY)>=0); });
  function row(r){
    var act=r.mine?'<button class="btn btn-line btn-sm" type="button" data-desk="'+esc(r.carrier_id)+'" data-release="1">'+esc(t("Leave this desk"))+'</button>'
      :'<button class="btn btn-primary btn-sm" type="button" data-desk="'+esc(r.carrier_id)+'">'+esc(t("Take this desk"))+'</button>';
    return '<tr><td><b>'+esc(t(r.name))+'</b><br><span class="fine">'+esc(r.countries.map(regionName).join(", "))+'</span></td>'+
      '<td class="num">'+(r.waiting?esc(t("{n} waiting",{n:r.waiting})):(r.mine?esc(t("your desk")):''))+'</td><td class="num">'+act+'</td></tr>';
  }
  return '<div class="panel" style="padding:22px;margin-top:26px" id="specimen-desks">'+
    '<h3 style="font-size:17px;margin:0 0 6px">'+esc(t("Demonstration: sit at a stand in company's desk"))+'</h3>'+
    '<p class="fine" style="margin:0 0 14px">'+esc(t("The stand in companies are not real, so nobody sits behind them. Take one's desk and the applications placed with it appear above, for you to check and approve as its underwriter would. Choose the company shown as the issuer on the application."))+'</p>'+
    '<div class="tform" style="margin-bottom:12px"><label><span>'+esc(t("Show the companies in"))+'</span><select id="desk-country"><option value="">'+esc(t("only those with applications waiting"))+'</option>'+
      codes.map(function(c){ return '<option value="'+esc(c)+'"'+(c===DESK_COUNTRY?' selected':'')+'>'+esc(regionName(c))+'</option>'; }).join("")+'</select></label></div>'+
    (shown.length?'<div class="tbl-wrap"><table class="tbl" style="min-width:0"><tbody>'+shown.map(row).join("")+'</tbody></table></div>'
      :'<p class="fine">'+esc(t("No stand in company has an application waiting. Pick a country to see its companies."))+'</p>')+
    '<p class="fine" id="desk-out" style="margin:10px 0 0"></p></div>';
}
function bindSpecimenDesks(root){
  var sel=$("desk-country");
  if(sel)sel.addEventListener("change",function(){ DESK_COUNTRY=sel.value; renderCompany(); });
  Array.prototype.forEach.call(root.querySelectorAll("[data-desk]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true;
      api("/api/company/specimen",{method:"POST",token:identity.token,timeout:15000,
        body:{carrier_id:b.dataset.desk,release:!!b.dataset.release}}).then(function(){ renderCompany(); },
        function(e){ b.disabled=false; var o=$("desk-out"); if(o)o.textContent=refusalText(e); });
    });
  });
}
function companyHtml(c){
  var b=c.book||{}, reinsurer=c.role==="reinsurer";
  var status='<span class="pill">'+esc(t(COMPANY_STATUS[c.status]||c.status))+'</span>';
  var next=c.status==="pending"
    ? '<div class="verdict" style="margin:14px 0"><p>'+esc(t("Waiting for review. Nothing can be written on your paper until a person has checked your licence against the regulator's register."))+'</p></div>'
    : c.status==="active" ? '' : '<div class="verdict no" style="margin:14px 0"><p>'+esc(t("Not writing. Cover on your paper stops until this is resolved."))+'</p></div>';
  var countries=Object.keys(b.by_country||{});
  var byCountry=countries.length?'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("In force by country"))+'</h3>'+
    '<div class="tbl-wrap"><table class="tbl" style="min-width:0"><tbody>'+countries.map(function(k){
      var r=b.by_country[k];
      return '<tr><td>'+esc(k==="?"?t("not recorded"):regionName(k))+'</td><td class="num">'+f0.format(r.policies)+'</td><td class="num">'+money(r.in_force)+' USDC</td></tr>';
    }).join("")+'</tbody></table></div>':'';
  var checklist=c.specimen?'':'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("What the operator checks before you may write"))+'</h3>'+
    '<div data-vetting="'+esc(c.carrier_id)+'" data-pending="0"><p class="fine">'+esc(t("Reading the checklist…"))+'</p></div>'+
    '<div class="field" style="margin-top:12px"><label class="label" for="more-docs-'+esc(c.carrier_id)+'">'+esc(t("Add documents the checklist asks for"))+'</label>'+
    '<input id="more-docs-'+esc(c.carrier_id)+'" type="file" accept="application/pdf,image/png,image/jpeg" multiple data-more-docs="'+esc(c.carrier_id)+'">'+
    '<div data-more-kinds="'+esc(c.carrier_id)+'" style="display:grid;gap:6px;margin-top:8px"></div>'+
    '<button class="btn btn-line btn-sm" type="button" style="margin-top:8px" data-more-send="'+esc(c.carrier_id)+'" disabled>'+esc(t("Send the documents"))+'</button> <span class="fine" data-more-out="'+esc(c.carrier_id)+'"></span></div>';
  var verification=c.specimen?'':'<div style="margin-top:18px">'+checklist+verificationHtml(c,{token:identity.token},false)+
    (c.status==="pending"&&c.domain&&!((c.verification||{}).domain||{}).ok?domainProofHtml({url:"https://"+c.domain+"/.well-known/clause-insurer.txt",content:"clause-insurer="+(c.address||identity.address||"")}):'')+'</div>';
  var reviews=(c.reviews||[]).map(function(r){
    return '<li>'+esc(opStamp(r.at))+' · '+esc(t(r.action==="activated"?"approved":"suspended"))+
      (r.note?' · '+esc(r.note):'')+'</li>';
  }).join("");
  return '<div class="panel" style="padding:22px;margin-bottom:18px">'+
    '<div class="vrow" style="gap:10px;align-items:center">'+status+'<h2 style="font-size:21px">'+esc(ts(c.name))+'</h2>'+
      '<span class="fine">'+esc(t(reinsurer?"Reinsurer":"Insurer"))+' · '+esc(regionName(c.domicile))+'</span></div>'+
    next+
    '<div class="stats">'+
      statHtml(f0.format(b.open||0),t(reinsurer?"policies in the book you back":"open policies on your paper"))+
      statHtml(money(b.in_force||0),t("in force, USDC"))+
      statHtml(money(b.premiums||0),t("premiums, USDC"))+
      (reinsurer?'':statHtml(money(b.fees||0),t("your fronting fees, USDC")))+
      (reinsurer?'':statHtml(money(b.platform_fees||0),t("platform fee, {rate} of premium, USDC",{rate:pct(b.platform_rate||0.01,0)})))+
      statHtml(money(b.paid_out||0),t("paid out, USDC"))+
    '</div>'+byCountry+
    (reinsurer?'':'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Monthly statement"))+'</h3>'+
      '<p class="fine">'+esc(t("Every fee movement on your paper, month by month: the fees buyers paid you, what came back to them, and the platform's {rate} of premium taken out of your fee. The buyer's price is the pool's price; the platform is paid by you, never by them.",{rate:pct(b.platform_rate||0.01,0)}))+'</p>'+
      '<div data-statement-for="'+esc(c.carrier_id)+'"><p class="fine">'+esc(t("Reading the statement…"))+'</p></div>')+
    (reinsurer?'':'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Bordereaux"))+'</h3>'+
      '<p class="fine">'+esc(t("What your desk and your reinsurer expect, month by month: the risk bordereau (every policy bound, with its dates, limit, premium and the shares taken from your fee), the claims bordereau (every payout and every premium returned), and the reconciliation against the fee ledger, which says whether they agree and by how much they do not."))+'</p>'+
      '<div data-bordereaux-for="'+esc(c.carrier_id)+'"><p class="fine">'+esc(t("Reading the bordereaux…"))+'</p></div>')+
    (reinsurer?'':'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Complaints"))+'</h3>'+
      '<p class="fine">'+esc(t("Raised on your policies, with your time to answer counted from the day they were raised. Answer on the thread; your first message stops the clock. Close one when it is settled."))+'</p>'+
      '<div data-complaints-for="'+esc(c.carrier_id)+'"><p class="fine">'+esc(t("Reading the complaints…"))+'</p></div>')+
    '<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Your book"))+'</h3>'+
    (reinsurer?policiesTable(b.recent,false):'<div data-desk-for="'+esc(c.carrier_id)+'"><p class="fine">'+esc(t("Reading the book…"))+'</p></div>')+
    (reviews?'<h3 style="font-size:16px;margin:22px 0 10px">'+esc(t("Review record"))+'</h3><ul class="fine" style="display:grid;gap:4px;padding-left:18px">'+reviews+'</ul>':'')+
    verification+
  '</div>';
}

/* What anchors a registration: the LEI record, the proof file on the
   company's domain, the documents it uploaded, and the register a person
   has to read. Shown to the reviewer and to the company itself. */
var CHECK_WORDS={lei:N("LEI record"),domain:N("Control of the domain"),licence:N("Licence at the regulator's register"),evidence:N("Documents uploaded")};
var EVIDENCE_WORDS={licence_certificate:N("licence certificate"),register_extract:N("register extract"),authorisation_letter:N("letter of authorisation"),other:N("document")};
function verificationHtml(c, auth, forReviewer){
  var v=c.verification||{}, id=esc(c.carrier_id);
  function line(ok, given, text, label){
    var cls=ok?"ok":(given===false||label?"":"no");
    return '<div class="vrule"><span class="pill '+cls+'">'+esc(label||(ok?t("confirmed"):given===false?t("not given"):t("not confirmed")))+'</span><span>'+text+'</span></div>';
  }
  var out='<div class="verify">'+
    '<div class="label" style="margin-bottom:8px">'+esc(t("What anchors this registration"))+'</div>';
  if(!c.verification){
    out+='<p class="fine">'+esc(t("The automatic checks have not run yet; they run within seconds of registering."))+'</p>';
  }else{
    var L=v.lei||{}, D=v.domain||{};
    out+=line(L.ok,L.given,'<span class="t">'+esc(t("LEI"))+(L.lei?' <span class="mono">'+esc(L.lei)+'</span>':'')+'</span><span class="s">'+esc(ts(L.summary||""))+'</span>');
    out+=line(D.ok,D.given,'<span class="t">'+esc(t("Company domain"))+(D.domain?' <span class="mono">'+esc(D.domain)+'</span>':'')+'</span><span class="s">'+esc(ts(D.summary||""))+'</span>');
  }
  var ev=c.evidence||[];
  out+=line(null,ev.length?null:false,'<span class="t">'+esc(t("Documents"))+'</span><span class="s">'+
    (ev.length?ev.map(function(e){
      return '<a href="#" data-evidence="'+id+'" data-n="'+e.n+'">'+esc(t(EVIDENCE_WORDS[e.kind]||e.kind))+(e.filename?' · '+esc(e.filename):'')+'</a>'+
        ' <span class="mono" style="font-size:11px">sha256 '+esc(e.sha256.slice(0,12))+'…</span>';
    }).join("<br>")+'<br>'+esc(t("A document shows what the company claims, not that it is true: a PDF can be edited, a register cannot.")):esc(t("none uploaded")))+'</span>',ev.length?t("for review"):"");
  var regs=(v.registers||[]);
  out+='<div class="vrule"><span class="pill">'+esc(t("a person"))+'</span><span><span class="t">'+esc(t("The licence, at the regulator's own register"))+'</span><span class="s">'+
    (regs.length?regs.map(function(r){ return '<a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.name)+'</a>'; }).join("<br>"):esc(t("links appear once the checks have run")))+
    '<br>'+esc(t("No supervisor offers a free API for this; the number is checked by reading the register, and the record below says who read it."))+'</span></span></div>';
  out+='<div class="op-acts" style="margin-top:8px"><button class="btn btn-ghost btn-sm" type="button" data-reverify="'+id+'">'+esc(t("Run the automatic checks again"))+'</button>'+
    (v.checked_at?'<span class="fine">'+esc(t("last run {time}",{time:opStamp(v.checked_at)}))+'</span>':'')+'</div>';
  if(forReviewer&&c.status==="pending"){
    out+='<div class="checks" data-cochecks="'+id+'">'+["lei","domain","licence","evidence"].map(function(k){
      return '<label><input type="checkbox" value="'+k+'"> '+esc(t("Confirmed: {what}",{what:t(CHECK_WORDS[k])}))+'</label>';
    }).join("")+'</div>';
  }
  return out+'</div>';
}
function bindVerification(root, auth, reload){
  Array.prototype.forEach.call(root.querySelectorAll("[data-evidence]"),function(a){
    a.addEventListener("click",function(e){
      e.preventDefault();
      var opts={raw:true,timeout:30000}; for(var k in auth)opts[k]=auth[k];
      api("/api/carriers/"+encodeURIComponent(a.dataset.evidence)+"/evidence/"+a.dataset.n,opts).then(function(blob){
        var url=URL.createObjectURL(blob); window.open(url,"_blank"); setTimeout(function(){URL.revokeObjectURL(url);},60000);
      },function(){ a.textContent=t("could not open it"); });
    });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-reverify]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true; b.textContent=t("Checking…");
      var opts={method:"POST",timeout:30000}; for(var k in auth)opts[k]=auth[k];
      api("/api/carriers/"+encodeURIComponent(b.dataset.reverify)+"/verify",opts).then(reload,function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
}
/* The operator's checklist for one company: what to confirm, where to
   look, the documents that bear on it, and the record of who confirmed
   what. The same list, read only, on the company's own page. */
var VET_STATE={};
function vettingHtml(v,id,canEdit){
  var items=v.items||[];
  var head='<div class="label" style="margin-bottom:8px">'+esc(t("Before this company may write: {done} of {n} confirmed",{done:v.done,n:items.length}))+
    (v.missing&&v.missing.length?' · <span class="fine">'+esc(t("{n} required still open",{n:v.missing.length}))+'</span>':' · <span class="pill ok">'+esc(t("complete"))+'</span>')+'</div>';
  return head+items.map(function(it){
    var st=it.state||{}, auto=it.auto;
    var pill=it.done?'<span class="pill ok">'+esc(t("confirmed"))+'</span>'
      :st.ok===false?'<span class="pill no">'+esc(t("failed"))+'</span>'
      :(st.ok===null&&st.by)?'<span class="pill">'+esc(t("set aside"))+'</span>'
      :'<span class="pill">'+esc(it.required?t("required"):t("recommended"))+'</span>';
    var where=(it.where||[]).map(function(l){ return '<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(ts(l.name))+'</a>'; }).join(" · ");
    var docs=(it.documents||[]).map(function(d){ return '<a href="#" data-evidence="'+esc(id)+'" data-n="'+d.n+'">'+esc(t(DOC_KINDS[d.kind]||d.kind))+(d.filename?' · '+esc(d.filename):'')+'</a>'; }).join(" · ");
    var record=st.by?'<div class="fine">'+esc(st.ok===false?t("{who} found it failed, {when}",{who:st.by,when:opStamp(st.at)}):st.ok===null?t("{who} set it aside, {when}",{who:st.by,when:opStamp(st.at)}):t("{who} confirmed it, {when}",{who:st.by,when:opStamp(st.at)}))+
      (st.source?' · '+esc(st.source):'')+(st.note?' · '+esc(st.note):'')+'</div>':'';
    var autoLine=auto?'<div class="fine">'+esc(auto.ok?t("automatic check passed"):auto.ok===false?t("automatic check did not pass"):t("automatic check pending"))+(auto.summary?': '+esc(ts(auto.summary)):'')+'</div>':'';
    var form=canEdit?'<div class="tform" style="margin-top:6px"><input class="dlg-input" style="min-width:200px;flex:1" maxlength="300" placeholder="'+esc(t("where you looked (a link or a register)"))+'" data-vet-source="'+esc(it.key)+'">'+
      '<input class="dlg-input" style="min-width:200px;flex:1" maxlength="400" placeholder="'+esc(t("what you saw"))+'" data-vet-note="'+esc(it.key)+'">'+
      '<button class="btn btn-primary btn-sm" type="button" data-vet="'+esc(it.key)+'" data-ok="1">'+esc(t("Confirmed"))+'</button>'+
      '<button class="btn btn-line btn-sm" type="button" data-vet="'+esc(it.key)+'" data-ok="0">'+esc(t("Failed"))+'</button>'+
      (it.required?'':'<button class="btn btn-ghost btn-sm" type="button" data-vet="'+esc(it.key)+'" data-ok="">'+esc(t("Set aside"))+'</button>')+'</div>':'';
    return '<div class="vrule" style="align-items:flex-start"><span class="pill-col">'+pill+'</span><span style="flex:1"><span class="t">'+esc(ts(it.title))+'</span>'+
      '<span class="s">'+esc(ts(it.what))+(it.branches&&it.branches.length?'<br><b>'+esc(it.branches.join("; "))+'</b>':'')+'</span>'+
      (where?'<div class="fine">'+esc(t("Where:"))+' '+where+'</div>':'')+
      (docs?'<div class="fine">'+esc(t("Documents:"))+' '+docs+'</div>':(it.evidence&&it.evidence.length&&canEdit?'<div class="fine">'+esc(t("No document for this yet; the company can add one from its page."))+'</div>':''))+
      autoLine+record+form+'</span></div>';
  }).join("");
}
function bindMoreDocs(root,auth,reload){
  Array.prototype.forEach.call(root.querySelectorAll("[data-more-docs]"),function(input){
    var id=input.dataset.moreDocs, kinds=root.querySelector('[data-more-kinds="'+id+'"]'), send=root.querySelector('[data-more-send="'+id+'"]'), out=root.querySelector('[data-more-out="'+id+'"]');
    input.addEventListener("change",function(){
      var files=Array.prototype.slice.call(input.files||[]);
      kinds.innerHTML=files.map(function(f){ var g=guessKind(f.name);
        return '<label class="fine" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><span style="min-width:180px">'+esc(f.name)+'</span><select class="dlg-input" style="max-width:280px" data-file="'+esc(f.name)+'">'+
          Object.keys(DOC_KINDS).map(function(k){ return '<option value="'+k+'"'+(k===g?' selected':'')+'>'+esc(t(DOC_KINDS[k]))+'</option>'; }).join("")+'</select></label>'; }).join("");
      send.disabled=!files.length;
    });
    send.addEventListener("click",function(){
      var files=Array.prototype.slice.call(input.files||[]); if(!files.length)return;
      if(files.length>4){ out.textContent=t("At most 4 documents."); return; }
      for(var i=0;i<files.length;i++){ if(files[i].size>3000000){ out.textContent=t("Each document is at most 3 MB."); return; } }
      send.disabled=true; out.textContent=t("Sending…");
      Promise.all(files.map(function(f){ return new Promise(function(resolve,reject){ var r=new FileReader();
        r.onload=function(){ var sel=kinds.querySelector('select[data-file="'+CSS.escape(f.name)+'"]');
          resolve({kind:sel?sel.value:guessKind(f.name),filename:f.name.slice(0,120),content_type:f.type,data:String(r.result).split(",")[1]||""}); };
        r.onerror=reject; r.readAsDataURL(f); }); })).then(function(ev){
        var o={method:"POST",timeout:40000,body:{evidence:ev}}; for(var k in auth)o[k]=auth[k];
        return api("/api/company/"+encodeURIComponent(id)+"/evidence",o);
      }).then(function(){ out.textContent=t("Sent."); reload(); },function(e){ send.disabled=false; out.textContent=refusalText(e); });
    });
  });
}
function bindVetting(root,auth,reload){
  Array.prototype.forEach.call(root.querySelectorAll("[data-vetting]"),function(holder){
    var id=holder.dataset.vetting, canEdit=!!auth.token&&auth.token===OP.token;
    function paint(v){
      VET_STATE[id]=v;
      holder.innerHTML=vettingHtml(v,id,canEdit);
      var act=root.querySelector('[data-act="activate"][data-id="'+id+'"]'); if(act&&holder.dataset.pending==="1")act.disabled=!v.can_activate;
      bindVerification(holder,auth,reload);
      Array.prototype.forEach.call(holder.querySelectorAll("[data-vet]"),function(b){
        b.addEventListener("click",function(){
          var key=b.dataset.vet, ok=b.dataset.ok===""?null:b.dataset.ok==="1";
          var src=(holder.querySelector('[data-vet-source="'+key+'"]')||{}).value||"", note=(holder.querySelector('[data-vet-note="'+key+'"]')||{}).value||"";
          if(ok!==null&&!src.trim()){ b.textContent=t("Say where you looked"); return; }
          b.disabled=true;
          var o={method:"POST",timeout:15000,body:{key:key,ok:ok,source:src,note:note}}; for(var k in auth)o[k]=auth[k];
          api("/api/carriers/"+encodeURIComponent(id)+"/vetting",o).then(paint,function(e){ b.disabled=false; b.textContent=refusalText(e); });
        });
      });
    }
    var o={timeout:15000}; for(var k in auth)o[k]=auth[k];
    api("/api/carriers/"+encodeURIComponent(id)+"/vetting",o).then(paint,function(e){ holder.innerHTML='<p class="fine">'+esc(refusalText(e))+'</p>'; });
  });
}
function opCard(c){
  var pending=c.status==="pending", active=c.status==="active";
  var licences=(c.licences||[]).map(function(l){
    return '<div class="vrule"><span class="mark">'+esc(l.country)+'</span>'+
      '<span><span class="t">'+esc(ts(l.authority))+'</span>'+
      '<span class="s">'+t("Reference {ref}",{ref:'<b>'+esc(ts(l.reference))+'</b>'})+' · '+esc(perilWords(l.perils))+
      ' · '+esc(t(REACH_WORDS[l.reach]||l.reach))+' · '+esc(t("settles {assets}",{assets:listText(l.settlement.map(localValue))}))+
      '<br>'+esc(t("Expires {time}",{time:opStamp(l.expires_at)}))+
      ' · '+esc(l.verified_at?t("checked {time}",{time:opStamp(l.verified_at)}):t("never checked"))+
      '</span></span>'+
      '<span class="pill '+(l.live?(l.expiring_soon?"":"ok"):"no")+'">'+
      esc(l.live?(l.expiring_soon?t("renewing"):t("live")):t("out of force"))+'</span></div>';
  }).join("") || '<div class="vrule"><span class="mark">—</span><span><span class="t">'+
    esc(t("No licence on this record"))+'</span><span class="s">'+
    esc(t("A reinsurer holds none where the buyer is, which is the role working as intended. A carrier with none can write nothing anywhere."))+'</span></span></div>';

  var trail=(c.reviews||[]).map(function(r){
    return esc(opStamp(r.at))+' · '+esc(t(r.action==="activated"?"activated by {name}":"suspended by {name}",{name:r.reviewer}))+
      (r.note?' · '+esc(r.note):'');
  }).join("<br>");

  var id=esc(c.carrier_id);
  return '<div class="co-card">'+
    '<div><div class="co-head"><span class="nm">'+esc(ts(c.name))+'</span>'+
      '<span class="pill '+(active?"ok":pending?"":"no")+'">'+esc(t(COMPANY_STATUS[c.status]||c.status))+'</span>'+
      (c.specimen?'<span class="pill no">'+esc(t("specimen"))+'</span>':'')+
      '<span class="fine">'+esc(t(ROLE_WORDS[c.role]||c.role))+' · '+esc(t("domiciled in {country}",{country:regionName(c.domicile)}))+
      ' · '+esc(t("registered {time}",{time:opStamp(c.registered_at)}))+'</span></div></div>'+
    '<div>'+licences+'</div>'+
    '<div><div class="kvs">'+
      kv(t("Capacity"),money(c.capacity))+
      kv(t("In force"),money(c.in_force))+
      kv(t("Fronting fee"),c.fronting_fee?pct(c.fronting_fee,2):esc(t("none")))+
      kv(t("Contact"),esc(c.contact||t("none given")))+
    '</div></div>'+
    (trail?'<div><div class="op-trail">'+trail+'</div></div>':'')+
    (c.specimen?'':'<div>'+verificationHtml(c,{token:OP.token},true)+'</div>')+
    '<div>'+
      (c.specimen?'':'<div class="vetting" data-vetting="'+id+'" data-pending="'+(pending?"1":"0")+'"><p class="fine">'+esc(t("Reading the checklist…"))+'</p></div>')+
      (c.review_due_at?'<p class="fine">'+esc(t("Checks due again {time}",{time:opStamp(c.review_due_at)}))+'</p>':'')+
      '<div class="op-acts">'+
        '<input class="dlg-input" style="flex:1;min-width:220px" maxlength="400" '+
          'data-note="'+id+'" placeholder="'+esc(pending
            ? t("what you checked, and where")
            : t("why")).replace(/"/g,"&quot;")+'">'+
        (active
          ? '<button class="btn btn-line btn-sm" type="button" data-act="suspend" '+
            'data-id="'+id+'">'+esc(t("Suspend"))+'</button>'
          : '<button class="btn btn-primary btn-sm" type="button" data-act="activate" '+
            'data-id="'+id+'"'+(pending&&!c.specimen?' disabled':'')+'>'+esc(t("Activate"))+'</button>')+
      '</div>'+
      '<div class="verdict" data-out="'+id+'" hidden></div>'+
    '</div></div>';
}


/* ---------------- operator: payouts and partners ---------------- */
function perilLabel(k){ var f=MANDATE_PERILS.filter(function(p){return p[0]===k;})[0]; return f?t(f[1]):k; }
function opPayoutsHtml(p){
  var out='<div class="verdict" style="margin-bottom:16px"><p>'+esc(p.rail==="manual"
    ? t("No payment partner is connected, so each order below is paid by hand: make the transfer from the issuing company's account, then mark it paid with the bank's reference. Marking one failed returns the money to the holder's address.")
    : t("Orders go to the payment partner as they settle; the partner reports back. An order stuck here can still be marked by hand."))+'</p></div>';
  if(!p.open.length) out+='<div class="panel" style="padding:20px"><p>'+esc(t("Nothing waiting."))+'</p></div>';
  p.open.forEach(function(o){
    out+='<div class="panel" style="padding:18px;display:grid;gap:10px;margin-bottom:12px">'+
      '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:baseline"><b class="mono">'+esc(o.order_id)+'</b>'+
      '<span>'+money(o.amount)+' USDC → '+esc(o.currency)+'</span><span class="fine">'+esc(t(ORDER_KIND[o.kind]||o.kind))+' · '+
      (o.kind==="withdrawal"?'<span class="mono">'+esc(short(o.account||""))+'</span>':'<a href="#/proof/'+encodeURIComponent(o.reference)+'">'+esc(o.reference)+'</a>')+' · '+esc(t(PAYOUT_STATUS[o.status]||o.status))+'</span></div>'+
      '<div class="mono" style="font-size:14px;word-break:break-all">'+esc(o.pay_to||"")+'</div>'+
      (o.company?'<p class="fine">'+esc(t("Registered company: {name}",{name:o.company}))+(o.name_check==="match"?' · <span style="color:var(--settled)">'+esc(t("the name on the bank account matches"))+'</span>':o.name_check==="mismatch"?' · <span style="color:var(--crit)">'+esc(t("the name on the bank account does not match the company; check before paying"))+'</span>':'')+'</p>':'')+
      (o.note?'<p class="fine">'+esc(o.note)+'</p>':'')+
      '<div class="tform"><label><span>'+esc(t("Bank reference"))+'</span><input data-ref="'+esc(o.order_id)+'"></label>'+
      '<button class="btn btn-primary btn-sm" type="button" data-pay="'+esc(o.order_id)+'" data-st="paid">'+esc(t("Mark paid"))+'</button>'+
      '<button class="btn btn-line btn-sm" type="button" data-pay="'+esc(o.order_id)+'" data-st="failed">'+esc(t("Mark failed"))+'</button></div></div>';
  });
  if(p.recent.length){
    out+='<h3 style="font-size:16px;margin:24px 0 10px">'+esc(t("Recently decided"))+'</h3><div class="table-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways" data-i18n-aria><table class="ttable"><tbody>'+
      p.recent.map(function(o){ return '<tr><td class="mono">'+esc(o.order_id)+'</td><td class="num">'+money(o.amount)+'</td><td>'+esc(o.currency)+'</td><td>'+
        esc(o.destination)+'</td><td>'+esc(t(PAYOUT_STATUS[o.status]||o.status))+'</td><td class="mono">'+esc(o.rail_reference||"")+'</td></tr>'; }).join("")+
      '</tbody></table></div>';
  }
  return out;
}
function opFundingHtml(f){
  var out='<div class="verdict" style="margin-bottom:16px"><p>'+esc(f.how.methods.length
    ? t("Each line is a transfer someone announced. Check the bank statement or the chain explorer for the reference, enter the amount that actually arrived and confirm; the address is credited then and not before. Nothing seen after thirty days expires by itself.")
    : t("No way of adding balance is configured. Set CLAUSE_FUNDING_IBAN and the account name, or a receiving wallet address, on the server."))+'</p></div>';
  if(!f.waiting.length) out+='<div class="panel" style="padding:20px"><p>'+esc(t("Nothing waiting."))+'</p></div>';
  f.waiting.forEach(function(r){
    out+='<div class="panel" style="padding:18px;display:grid;gap:10px;margin-bottom:12px">'+
      '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:baseline"><b class="mono">'+esc(r.reference)+'</b>'+
      '<span>'+esc(t(FUNDING_NAMES[r.method]||r.method))+' · '+money(r.amount)+' USDC '+esc(t("announced"))+'</span>'+
      '<span class="fine mono">'+esc(t("for"))+' '+esc(r.account)+(r.sender?' · '+esc(t("from"))+' '+esc(r.sender):'')+' · '+esc(opStamp(r.created_at))+'</span></div>'+
      '<div class="tform"><label><span>'+esc(t("Amount received"))+'</span><input data-fund-amt="'+esc(r.request_id)+'" type="number" min="1" step="0.01" value="'+esc(r.amount)+'" style="max-width:150px"></label>'+
      '<label><span>'+esc(t("Bank or transaction reference"))+'</span><input data-fund-note="'+esc(r.request_id)+'" maxlength="200"></label>'+
      '<button class="btn btn-primary btn-sm" type="button" data-fund="'+esc(r.request_id)+'" data-st="received">'+esc(t("Confirm and credit"))+'</button>'+
      '<button class="btn btn-line btn-sm" type="button" data-fund="'+esc(r.request_id)+'" data-st="cancelled">'+esc(t("Nothing arrived"))+'</button></div></div>';
  });
  if(f.recent.length){
    out+='<h3 style="font-size:16px;margin:24px 0 10px">'+esc(t("Recently decided"))+'</h3><div class="table-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways" data-i18n-aria><table class="ttable"><tbody>'+
      f.recent.map(function(r){ return '<tr><td class="mono">'+esc(r.reference)+'</td><td>'+esc(t(FUNDING_NAMES[r.method]||r.method))+'</td><td class="num">'+money(r.received||r.amount)+'</td><td class="mono">'+esc(short(r.account))+'</td><td>'+esc(t(FUNDING_STATUS[r.status]||r.status))+'</td><td>'+esc(r.note||"")+'</td></tr>'; }).join("")+
      '</tbody></table></div>';
  }
  return out;
}
function opPartnersHtml(p){
  var out='<div class="panel" style="padding:18px;display:grid;gap:12px;margin-bottom:18px">'+
    '<h3 style="font-size:16px">'+esc(t("Admit a partner"))+'</h3>'+
    '<p class="fine">'+esc(t("A company that sells this cover inside its own product. It gets an API key, pays premiums from its own address and keeps a commission of up to 20%, never more than the premium's expense load."))+'</p>'+
    '<div class="tform">'+
      '<label><span>'+esc(t("Name"))+'</span><input id="pt-name" style="min-width:240px"></label>'+
      '<label><span>'+esc(t("Commission, %"))+'</span><input id="pt-comm" type="number" min="0" max="20" value="10"></label>'+
      '<label><span>'+esc(t("Countries"))+'</span><input id="pt-countries" value="TR" placeholder="TR, GR"></label>'+
      '<label><span>'+esc(t("Webhook, https"))+'</span><input id="pt-hook" placeholder="https://" style="min-width:240px"></label></div>'+
    '<div class="checks" id="pt-perils">'+MANDATE_PERILS.map(function(x){
      return '<label><input type="checkbox" value="'+x[0]+'"'+(x[0]==="flight_delay"?" checked":"")+'> '+esc(t(x[1]))+'</label>'; }).join("")+'</div>'+
    '<div><button class="btn btn-primary btn-sm" type="button" id="pt-go">'+esc(t("Admit and issue a key"))+'</button></div>'+
    '<div id="pt-key">'+(OP.newKey?keyHtml(OP.newKey):'')+'</div></div>';
  OP.newKey=null;
  if(!p.partners.length) return out+'<div class="panel" style="padding:20px"><p>'+esc(t("No partners yet."))+'</p></div>';
  out+='<div class="table-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways" data-i18n-aria><table class="ttable"><thead><tr><th>'+esc(t("Partner"))+'</th><th>'+esc(t("Covers"))+'</th><th class="num">'+
    esc(t("Sold"))+'</th><th class="num">'+esc(t("Premium"))+'</th><th class="num">'+esc(t("Commission"))+'</th><th class="num">'+esc(t("Balance"))+'</th><th>'+
    esc(t("Status"))+'</th><th></th></tr></thead><tbody>'+
    p.partners.map(function(x){
      return '<tr><td><b>'+esc(x.name)+'</b><br><span class="fine mono">'+esc(x.partner_id)+' · …'+esc(x.key_hint)+'</span></td>'+
        '<td>'+esc(x.perils.map(perilLabel).join(", "))+'<br><span class="fine">'+esc(x.countries.join(", "))+'</span></td>'+
        '<td class="num">'+f0.format(x.sold)+'</td><td class="num">'+money(x.premium_total)+'</td><td class="num">'+money(x.commission_total)+'</td>'+
        '<td class="num">'+money(x.balance)+'</td><td>'+esc(x.status==="active"?t("active"):t("suspended"))+'</td>'+
        '<td><button class="btn btn-ghost btn-sm" type="button" data-pt="'+esc(x.partner_id)+'" data-do="rotate">'+esc(t("New key"))+'</button> '+
        '<button class="btn btn-line btn-sm" type="button" data-pt="'+esc(x.partner_id)+'" data-do="'+(x.status==="active"?"suspend":"activate")+'">'+
        esc(x.status==="active"?t("Suspend"):t("Activate"))+'</button></td></tr>';
    }).join("")+'</tbody></table></div>';
  return out;
}
function showKey(reply){ $("pt-key").innerHTML=keyHtml(reply); }
function keyHtml(reply){
  return '<div class="verdict ok"><p><b>'+esc(t("Shown once. Copy it now and send it to the partner over a safe channel."))+'</b></p>'+
    '<p class="mono" style="word-break:break-all">'+esc(t("API key"))+': '+esc(reply.api_key)+'</p>'+
    (reply.webhook_secret?'<p class="mono" style="word-break:break-all">'+esc(t("Webhook secret"))+': '+esc(reply.webhook_secret)+'</p>':'')+'</div>';
}
function opBindMoney(){
  Array.prototype.forEach.call(document.querySelectorAll("#op-work [data-fund]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.fund, amt=document.querySelector('#op-work [data-fund-amt="'+id+'"]'), note=document.querySelector('#op-work [data-fund-note="'+id+'"]');
      b.disabled=true;
      api("/api/operator/funding/"+encodeURIComponent(id),{method:"POST",token:OP.token,
        body:{status:b.dataset.st,received:amt?Number(amt.value):undefined,note:note?note.value.trim():""}}).then(opLoad,function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll("#op-work [data-pay]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.pay, ref=document.querySelector('#op-work [data-ref="'+id+'"]');
      b.disabled=true;
      api("/api/operator/payouts/"+encodeURIComponent(id),{method:"POST",token:OP.token,
        body:{status:b.dataset.st,reference:ref?ref.value.trim():""}}).then(opLoad,function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
  var go=$("pt-go");
  if(go)go.addEventListener("click",function(){
    var perils=Array.prototype.filter.call($("pt-perils").querySelectorAll("input"),function(i){return i.checked;}).map(function(i){return i.value;});
    go.disabled=true;
    api("/api/operator/partners",{method:"POST",token:OP.token,body:{
      name:$("pt-name").value.trim(), commission:Number($("pt-comm").value)/100, perils:perils,
      countries:$("pt-countries").value.split(/[\s,]+/).filter(Boolean), webhook_url:$("pt-hook").value.trim(),
      // Pretend money for the demonstration; a real deployment ignores it.
      fund:50000}}).then(function(reply){
        OP.newKey=reply; OP.tab="partners"; opLoad();
      },function(e){ go.disabled=false; go.textContent=refusalText(e); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("#op-work [data-pt]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true;
      api("/api/operator/partners/"+encodeURIComponent(b.dataset.pt)+"/"+b.dataset.do,{method:"POST",token:OP.token})
        .then(function(reply){ if(reply.api_key){ showKey(reply); b.disabled=false; } else opLoad(); },
              function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
}

function opBindCards(){
  var refresh=$("op-refresh"), out=$("op-out");
  if(refresh) refresh.addEventListener("click", opLoad);
  if(out) out.addEventListener("click", opSignOut);

  Array.prototype.forEach.call(
    document.querySelectorAll("#op-work [data-confirm]"), function(box){
      box.addEventListener("change", function(){
        var button=document.querySelector(
          '#op-work [data-act="activate"][data-id="'+box.dataset.confirm+'"]');
        if(button) button.disabled = !box.checked;
      });
    });

  Array.prototype.forEach.call(
    document.querySelectorAll("#op-work [data-act]"), function(button){
      button.addEventListener("click", function(){
        opAct(button.dataset.id, button.dataset.act, button);
      });
    });
  bindVerification($("op-work"),{token:OP.token},opLoad);
}

function opAct(id, action, button){
  var note=document.querySelector('#op-work [data-note="'+id+'"]');
  var out=document.querySelector('#op-work [data-out="'+id+'"]');
  button.disabled=true; button.textContent=action==="activate"?t("Activating…"):t("Suspending…");
  var boxes=document.querySelector('#op-work [data-cochecks="'+id+'"]');
  var checked=boxes?Array.prototype.filter.call(boxes.querySelectorAll("input"),function(i){return i.checked;}).map(function(i){return i.value;}):[];
  api("/api/carriers/"+encodeURIComponent(id)+"/"+action,{
    method:"POST", token:OP.token, timeout:12000,
    body:{note:note?note.value.slice(0,400):"",checked:checked},
  }).then(function(reply){
    var carrier=reply.carrier;
    out.hidden=false; out.className="verdict ok";
    out.innerHTML='<p>'+t("{name} is now <b>{status}</b>.",
        {name:esc(ts(carrier.name)),status:esc(t(COMPANY_STATUS[carrier.status]||carrier.status))})+' '+
      esc(carrier.status==="active"
        ? t("Its licences count from this second, and the record says you approved it. A country opens once a reinsurer and a model that can price the risk there are also in place.")
        : t("It stops matching at once. Cover already written is unaffected and will be checked again before it pays."))+'</p>';
    opLoad();
  },function(error){
    var payload=error&&error.payload;
    out.hidden=false; out.className="verdict no";
    out.innerHTML='<p>'+((payload&&typeof payload.detail==="string")?tsHtml(payload.detail):esc(t("The protocol refused that.")))+'</p>';
    button.disabled=false;
    button.textContent=action==="activate"?t("Activate"):t("Suspend");
  });
}


