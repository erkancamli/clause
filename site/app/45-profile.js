/* ---------------- the profile ----------------
   What else this account is known by. A Solana or Ethereum wallet is joined by
   signing a short text with the wallet itself, so the link is proved, not
   stated; a Rialo address is written down until Rialo wallets can sign in a
   browser; an X account comes through Privy, which runs X's own sign in. */
var LINK_KINDS={rialo:N("Rialo wallet"),solana:N("Solana wallet"),evm:N("Ethereum wallet"),x:N("X account")};
function profilePanel(p){
  if(!p)return "";
  var links=(p.links||[]).map(function(l){
    return '<div class="hrow"><span>'+(l.kind==="rialo"?'<i class="rialo-mark" aria-hidden="true"></i>':'')+esc(t(LINK_KINDS[l.kind]||l.kind))+
      (l.verified?' <span class="pill ok">'+esc(t("proved"))+'</span>':' <span class="pill">'+esc(t("as stated"))+'</span>')+'</span>'+
      '<b class="mono" style="word-break:break-all">'+esc(l.kind==="x"?"@"+l.address:l.address)+
      ' <button class="btn btn-ghost btn-sm" type="button" data-unlink="'+esc(l.link_id)+'">'+esc(t("Remove"))+'</button></b></div>';
  }).join("");
  var hasX=(p.links||[]).some(function(l){return l.kind==="x";});
  return '<details class="more" id="profile-box"><summary>'+esc(t("Profile"))+': <b>'+esc(p.via==="privy"?t("signed in with e-mail or a passkey"):t("this device's key"))+
      (p.links&&p.links.length?' · '+esc(t("{n} linked",{n:p.links.length})):'')+'</b></summary><div class="inner">'+
    '<div class="holding"><div class="hrow"><span>'+esc(t("Address"))+'</span><b class="mono" style="word-break:break-all">'+esc(p.address)+'</b></div>'+links+'</div>'+
    '<div class="label" style="margin:14px 0 6px">'+esc(t("Link a wallet"))+'</div>'+
    '<p class="fine">'+esc(t("A Solana or Ethereum wallet signs a short text to prove it is yours; nothing moves and nothing is spent. A deposit from a linked wallet is credited without a reference, and a payout to it needs no second look. A Rialo address is written down as you give it."))+'</p>'+
    '<div class="seg" id="link-kind" role="radiogroup">'+["solana","evm","rialo"].map(function(k,i){
      return '<button type="button" role="radio" data-k="'+k+'" aria-checked="'+(i===0)+'">'+(k==="rialo"?'<i class="rialo-mark" aria-hidden="true"></i>':'')+esc(t(LINK_KINDS[k]))+'</button>';}).join("")+'</div>'+
    '<div class="tform" style="margin-top:10px"><label><span>'+esc(t("Wallet address"))+'</span><input id="link-addr" autocomplete="off" spellcheck="false" style="min-width:330px"></label>'+
      '<button class="btn btn-line btn-sm" type="button" id="link-connect">'+esc(t("Connect wallet"))+'</button>'+
      '<button class="btn btn-primary btn-sm" type="button" id="link-go">'+esc(t("Sign and link"))+'</button></div>'+
    '<p class="fine" id="link-hint"></p>'+
    (p.x_enabled&&p.via==="privy"?'<div class="label" style="margin:14px 0 6px">'+esc(t("X account"))+'</div>'+
      '<p class="fine">'+esc(t("X's own sign in runs inside the sign in window; only your handle is kept here, shown on your company's page if you have one."))+'</p>'+
      '<div><button class="btn btn-line btn-sm" type="button" id="link-x">'+esc(hasX?t("Link a different X account"):t("Link my X account"))+'</button></div>':'')+
    '<p class="fine" id="link-msg" role="status"></p></div></details>';
}
function walletSign(kind,address,message){
  if(kind==="evm"){
    if(!window.ethereum)return Promise.reject(new Error(t("No Ethereum wallet found in this browser.")));
    var hex="0x"+Array.prototype.map.call(new TextEncoder().encode(message),function(b){return ("0"+b.toString(16)).slice(-2);}).join("");
    return window.ethereum.request({method:"personal_sign",params:[hex,address]});
  }
  var sol=window.solana||(window.phantom&&window.phantom.solana);
  if(!sol||!sol.signMessage)return Promise.reject(new Error(t("No Solana wallet found in this browser.")));
  return sol.signMessage(new TextEncoder().encode(message),"utf8").then(function(r){
    var sig=r&&r.signature?r.signature:r; var bytes=sig instanceof Uint8Array?sig:new Uint8Array(sig);
    var bin=""; for(var i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]); return btoa(bin);
  });
}
function refreshProfile(){
  /* The profile page is drawn by renderProfile; the account box is redrawn
     open, so the link just made is in view instead of behind a summary. */
  var open=!!($("profile-box")&&$("profile-box").open);
  var drawn=renderProfile();
  if(open&&drawn&&drawn.then)drawn.then(function(){ var b=$("profile-box"); if(b)b.open=true; });
}
function bindProfilePanel(p){
  if(!p||!$("link-kind"))return;
  var kind="solana";
  function show(){
    Array.prototype.forEach.call($("link-kind").querySelectorAll("button"),function(b){ b.setAttribute("aria-checked",String(b.dataset.k===kind)); });
    var c=CHAIN_WALLETS[kind]||{};
    $("link-hint").textContent=t(c.hint||""); $("link-addr").placeholder=c.ph?t(c.ph):"";
    $("link-connect").hidden=!c.connect;
  }
  Array.prototype.forEach.call($("link-kind").querySelectorAll("button"),function(b){ b.addEventListener("click",function(){ kind=b.dataset.k; show(); }); });
  show();
  $("link-connect").addEventListener("click",function(){
    connectChainWallet(kind).then(function(a){ $("link-addr").value=a; $("link-msg").textContent=""; },
      function(e){ $("link-msg").textContent=e&&e.message?e.message:t("The wallet did not connect."); });
  });
  $("link-go").addEventListener("click",function(){
    var address=$("link-addr").value.trim(), go=$("link-go");
    if(!address){ $("link-msg").textContent=t("Give the wallet address."); return; }
    go.disabled=true; $("link-msg").textContent=t("Signing…");
    var proof=kind==="rialo"?Promise.resolve({}):api("/api/profile/links/start",{method:"POST",token:identity.token,body:{kind:kind,address:address}})
      .then(function(start){ $("link-msg").textContent=t("Confirm in your wallet…");
        return walletSign(kind,address,start.message).then(function(sig){ return {wallet_nonce:start.nonce,wallet_signature:sig}; }); });
    proof.then(function(extra){
      $("link-msg").textContent=t("Signing…");
      return signedCall("link-wallet",{kind:kind,address:address},"/api/profile/links",function(){
        var body={account:identity.address,kind:kind,address:address}; for(var k in extra)body[k]=extra[k]; return body; });
    }).then(function(){ refreshProfile(); },function(e){ go.disabled=false; $("link-msg").textContent=e&&e.payload?refusalText(e):(e&&e.message?e.message:t("The wallet did not sign.")); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-unlink]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true;
      api("/api/profile/links/"+encodeURIComponent(b.dataset.unlink)+"/remove",{method:"POST",token:identity.token})
        .then(function(){ refreshProfile(); },function(e){ b.disabled=false; $("link-msg").textContent=refusalText(e); });
    });
  });
  var x=$("link-x");
  if(x)x.addEventListener("click",function(){
    x.disabled=true; $("link-msg").textContent=t("Opening X's sign in…");
    loadPrivy().then(function(){ return window.ClausePrivy.linkX(); }).then(function(idToken){
      if(!idToken)throw new Error(t("Privy gave no identity token; turn identity tokens on in the Privy dashboard."));
      return api("/api/profile/x",{method:"POST",token:identity.token,body:{identity_token:idToken}});
    }).then(function(){ refreshProfile(); },function(e){ x.disabled=false; $("link-msg").textContent=e&&e.payload?refusalText(e):(e&&e.message?e.message:t("X could not be linked.")); });
  });
}
/* ---------------- the profile page: my things ---------------- */
var ASSET_KINDS={home:N("My home"),vehicle:N("My car"),field:N("My harvest")};
var ASSETS={list:[],at:0};
function loadAssets(force){
  if(!identity.token)return Promise.resolve([]);
  if(!force&&ASSETS.list.length&&Date.now()-ASSETS.at<60000)return Promise.resolve(ASSETS.list);
  return api("/api/assets",{token:identity.token}).then(function(r){ ASSETS.list=r.assets||[]; ASSETS.at=Date.now(); return ASSETS.list; },function(){ return ASSETS.list; });
}
function assetSummary(a){
  var z=a.size||{};
  if(a.kind==="home")return t("{building}, {area} m², built {built}",{building:t(BUILDING_WORDS[z.building]||z.building),area:f0.format(z.area_m2),built:z.built});
  if(a.kind==="vehicle")return [z.make,z.model,z.plate].filter(Boolean).join(" ")+(z.model_year?" · "+t("{year} model",{year:z.model_year}):"");
  return t("{area} ha of {crop}",{area:f1.format(z.area_ha),crop:t(CROP_WORDS[z.crop]||z.crop)});
}
function assetCardHtml(a){
  var addr=a.address?[a.address.street,a.address.number,a.address.flat,a.address.postcode,a.address.city].filter(Boolean).join(" "):"";
  return '<div class="policy-card"><div class="bar"><span class="label">'+esc(t(ASSET_KINDS[a.kind]||a.kind))+'</span><span class="right label mono">'+esc(a.asset_id)+'</span></div>'+
    '<div class="body"><div class="kvs">'+kv(t("Name"),esc(a.label))+kv(t("What it is"),esc(assetSummary(a)))+
    (a.place?kv(t("Where"),esc(a.place)):"")+(addr?kv(t("Address"),esc(addr)):"")+'</div>'+
    '<div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn btn-primary btn-sm" href="#/cover" data-asset-cover="'+esc(a.asset_id)+'">'+esc(t("Get cover for it"))+'</a>'+
    '<button class="btn btn-line btn-sm" type="button" data-asset-edit="'+esc(a.asset_id)+'">'+esc(t("Edit"))+'</button>'+
    '<button class="btn btn-ghost btn-sm" type="button" data-asset-remove="'+esc(a.asset_id)+'">'+esc(t("Remove"))+'</button></div></div></div>';
}
function assetFormHtml(a){
  a=a||{kind:"home",size:{},address:{}};
  var z=a.size||{}, ad=a.address||{};
  return '<div class="panel" style="padding:20px;display:grid;gap:12px" id="asset-form">'+
    '<div class="seg" id="asset-kind" role="radiogroup">'+["home","vehicle","field"].map(function(k){
      return '<button type="button" role="radio" data-k="'+k+'" aria-checked="'+(a.kind===k)+'">'+esc(t(ASSET_KINDS[k]))+'</button>';}).join("")+'</div>'+
    '<div class="sizegrid"><div class="field"><label class="label" for="as-label">'+esc(t("A name you will recognise"))+'</label><input id="as-label" class="dlg-input" maxlength="60" value="'+esc(a.label||"")+'" placeholder="'+esc(t("the flat in Kadıköy, the white Corolla"))+'"></div>'+
      '<div class="field" data-for-kind="home"><label class="label" for="as-building">'+esc(t("What kind of building"))+'</label><select id="as-building">'+Object.keys(BUILDING_WORDS).map(function(k){ return '<option value="'+k+'"'+(k===z.building?' selected':'')+'>'+esc(t(BUILDING_WORDS[k]))+'</option>'; }).join("")+'</select></div>'+
      '<div class="field" data-for-kind="home"><label class="label" for="as-area">'+esc(t("Floor area, m²"))+'</label><input id="as-area" class="dlg-input" inputmode="decimal" value="'+esc(z.area_m2||"")+'"></div>'+
      '<div class="field" data-for-kind="home"><label class="label" for="as-built">'+esc(t("Year built"))+'</label><input id="as-built" class="dlg-input" inputmode="numeric" maxlength="4" value="'+esc(z.built||"")+'"></div>'+
      '<div class="field" data-for-kind="vehicle"><label class="label" for="as-year">'+esc(t("Model year"))+'</label><input id="as-year" class="dlg-input" inputmode="numeric" maxlength="4" value="'+esc(z.model_year||"")+'"></div>'+
      '<div class="field" data-for-kind="vehicle"><label class="label" for="as-make">'+esc(t("Make and model"))+'</label><input id="as-make" class="dlg-input" maxlength="40" value="'+esc([z.make,z.model].filter(Boolean).join(" "))+'"></div>'+
      '<div class="field" data-for-kind="vehicle"><label class="label" for="as-plate">'+esc(t("Plate"))+'</label><input id="as-plate" class="dlg-input" maxlength="16" value="'+esc(z.plate||"")+'"></div>'+
      '<div class="field" data-for-kind="field"><label class="label" for="as-crop">'+esc(t("What grows there"))+'</label><select id="as-crop">'+Object.keys(CROP_WORDS).map(function(k){ return '<option value="'+k+'"'+(k===z.crop?' selected':'')+'>'+esc(t(CROP_WORDS[k]))+'</option>'; }).join("")+'</select></div>'+
      '<div class="field" data-for-kind="field"><label class="label" for="as-ha">'+esc(t("Area, hectares"))+'</label><input id="as-ha" class="dlg-input" inputmode="decimal" value="'+esc(z.area_ha||"")+'"></div></div>'+
    '<div class="field"><label class="label" for="as-place">'+esc(t("Where it is"))+'</label><input id="as-place" class="dlg-input" maxlength="120" value="'+esc(a.place||"")+'" placeholder="'+esc(t("district or city; pick from the list"))+'" autocomplete="off"><div id="as-place-opts" class="results"></div>'+
      '<p class="fine" id="as-place-note">'+esc(a.latitude?t("Pinned at {lat}, {lon}",{lat:Number(a.latitude).toFixed(4),lon:Number(a.longitude).toFixed(4)}):t("Not pinned yet: choose a place from the list so the risk can be priced."))+'</p></div>'+
    '<div data-for-kind="home vehicle"><div class="label" style="margin:4px 0 8px" id="as-addr-title">'+esc(t("The address"))+'</div><div class="sizegrid addr">'+
      ["street","number","flat","postcode","city"].map(function(k){ var names={street:t("Street"),number:t("Building no"),flat:t("Flat"),postcode:t("Postcode"),city:t("City")};
        return '<div class="field"><label class="label" for="as-addr-'+k+'">'+esc(names[k])+'</label><input id="as-addr-'+k+'" class="dlg-input" maxlength="80" value="'+esc(ad[k]||"")+'"></div>'; }).join("")+'</div>'+
      '<p class="fine">'+esc(t("Kept for you alone and shown to the insurer only when you apply for cover on it."))+'</p></div>'+
    '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button class="btn btn-primary btn-sm" type="button" id="as-save">'+esc(a.asset_id?t("Save changes"):t("Save"))+'</button>'+
      (a.asset_id?'<button class="btn btn-ghost btn-sm" type="button" id="as-cancel">'+esc(t("Cancel"))+'</button>':'')+'<span class="fine" id="as-msg" role="status"></span></div></div>';
}
function bindAssetForm(a,done){
  a=a||{}; var kind=a.kind||"home"; var pin={latitude:a.latitude,longitude:a.longitude,country:a.country||"",place:a.place||""};
  function show(){
    Array.prototype.forEach.call($("asset-kind").querySelectorAll("button"),function(b){ b.setAttribute("aria-checked",String(b.dataset.k===kind)); });
    Array.prototype.forEach.call($("asset-form").querySelectorAll("[data-for-kind]"),function(el){ el.hidden=el.dataset.forKind.split(" ").indexOf(kind)<0; });
    $("as-addr-title").textContent=kind==="vehicle"?t("Where the car is kept"):t("The address of the home");
  }
  Array.prototype.forEach.call($("asset-kind").querySelectorAll("button"),function(b){ b.addEventListener("click",function(){ kind=b.dataset.k; show(); }); });
  show();
  var timer=null;
  $("as-place").addEventListener("input",function(e){
    var q=e.target.value.trim(); pin.latitude=null; pin.longitude=null;
    clearTimeout(timer); if(q.length<3){ $("as-place-opts").innerHTML=""; return; }
    timer=setTimeout(function(){
      var local=searchPlaces(q).slice(0,4).map(function(p){ return Object.assign({country:"TR"},p); });
      api("/api/geocode?q="+encodeURIComponent(q.slice(0,120))+"&lang="+LANG,{timeout:9000}).then(function(r){ return local.concat(r.places||[]); },function(){ return local; }).then(function(hits){
        $("as-place-opts").innerHTML=hits.slice(0,7).map(function(h){
          return '<button class="opt" type="button" data-lat="'+h.latitude+'" data-lon="'+h.longitude+'" data-name="'+esc(h.name)+'" data-country="'+esc(h.country||"")+'"><span class="lead">'+esc((h.country||"TR"))+'</span><span><span class="t">'+esc(h.name)+'</span><span class="s">'+esc(h.region||"")+'</span></span></button>';
        }).join("");
        Array.prototype.forEach.call($("as-place-opts").querySelectorAll(".opt"),function(b){
          b.addEventListener("click",function(){
            pin={latitude:Number(b.dataset.lat),longitude:Number(b.dataset.lon),country:b.dataset.country,place:b.dataset.name};
            $("as-place").value=pin.place; $("as-place-opts").innerHTML="";
            $("as-place-note").textContent=t("Pinned at {lat}, {lon}",{lat:pin.latitude.toFixed(4),lon:pin.longitude.toFixed(4)});
            if(!$("as-addr-city").value){ var parts=pin.place.split(", "); $("as-addr-city").value=parts[parts.length-1]||""; }
          });
        });
      });
    },400);
  });
  var cancel=$("as-cancel"); if(cancel)cancel.addEventListener("click",function(){ done(false); });
  $("as-save").addEventListener("click",function(){
    var body={asset_id:a.asset_id||undefined,kind:kind,label:$("as-label").value.trim(),place:pin.place||$("as-place").value.trim(),country:pin.country||"",
      latitude:pin.latitude,longitude:pin.longitude};
    if(kind==="home")body.size={building:$("as-building").value,area_m2:Number($("as-area").value),built:Number($("as-built").value)};
    else if(kind==="vehicle"){ var mm=$("as-make").value.trim().split(/\s+/); body.size={model_year:Number($("as-year").value),make:mm[0]||"",model:mm.slice(1).join(" "),plate:$("as-plate").value.trim()}; }
    else body.size={crop:$("as-crop").value,area_ha:Number($("as-ha").value)};
    if(kind!=="field"){ body.address={}; ["street","number","flat","postcode","city"].forEach(function(k){ body.address[k]=$("as-addr-"+k).value.trim(); }); }
    if(kind!=="field"&&pin.latitude==null){ $("as-msg").textContent=t("Choose the place from the list, so it can be pinned."); return; }
    $("as-save").disabled=true; $("as-msg").textContent=t("Saving…");
    api("/api/assets",{method:"POST",token:identity.token,body:body}).then(function(r){ ASSETS.list=r.assets||[]; ASSETS.at=Date.now(); done(true); },
      function(e){ $("as-save").disabled=false; $("as-msg").textContent=refusalText(e); });
  });
}
function renderProfile(){
  var box=$("profile-out");
  if(!link.checked){ whenLinked().then(renderProfile); return; }
  if(!link.live){ box.innerHTML=minePanel(t("Not connected"),t("This page cannot reach the protocol, so there is nothing to show."),""); return; }
  if(!identity.token){
    box.innerHTML=minePanel(t("Sign in to see it"),t("Your profile is held by your address, and only you can open it."),
      '<button class="btn btn-primary" type="button" id="profile-go">'+esc(t("Sign in"))+'</button>');
    $("profile-go").addEventListener("click",function(){
      var go=identity.address?signIn():chooseSignIn("sign-in");
      go.then(function(){ renderWho(); renderProfile(); },function(){});
    });
    return;
  }
  box.innerHTML='<div class="panel" style="padding:24px">'+skeleton(3)+'</div>';
  return Promise.all([api("/api/profile",{token:identity.token}).catch(function(){return null;}), loadAssets(true)]).then(function(all){
    var profile=all[0], list=all[1]||[];
    var html='<h2 style="font-size:18px;margin-bottom:10px">'+esc(t("My things"))+'</h2>'+
      (list.length?'<div style="display:grid;gap:12px" id="asset-list">'+list.map(assetCardHtml).join("")+'</div>':'<p class="fine">'+esc(t("Nothing written down yet. Add a home, a car or a field and the next purchase starts filled in."))+'</p>')+
      '<div id="asset-new" style="margin-top:14px"><button class="btn btn-line btn-sm" type="button" id="asset-add">'+esc(t("Add a home, a car or a field"))+'</button></div>'+
      '<h2 style="font-size:18px;margin:26px 0 10px">'+esc(t("Account"))+'</h2><div class="mine-extras">'+profilePanel(profile)+'</div>';
    box.innerHTML=html;
    bindProfilePanel(profile);
    $("asset-add").addEventListener("click",function(){
      $("asset-new").innerHTML=assetFormHtml(null); bindAssetForm(null,function(){ renderProfile(); });
    });
    Array.prototype.forEach.call(box.querySelectorAll("[data-asset-edit]"),function(b){
      b.addEventListener("click",function(){
        var a=list.filter(function(x){return x.asset_id===b.dataset.assetEdit;})[0]; if(!a)return;
        var card=b.closest(".policy-card"); card.outerHTML=assetFormHtml(a); bindAssetForm(a,function(){ renderProfile(); });
      });
    });
    Array.prototype.forEach.call(box.querySelectorAll("[data-asset-remove]"),function(b){
      b.addEventListener("click",function(){
        if(!confirm(t("Remove this entry? Cover already bought on it is not affected.")))return;
        b.disabled=true;
        api("/api/assets/"+encodeURIComponent(b.dataset.assetRemove)+"/remove",{method:"POST",token:identity.token}).then(function(){ renderProfile(); },function(e){ b.disabled=false; alert(refusalText(e)); });
      });
    });
    Array.prototype.forEach.call(box.querySelectorAll("[data-asset-cover]"),function(a){
      a.addEventListener("click",function(){
        var item=list.filter(function(x){return x.asset_id===a.dataset.assetCover;})[0];
        if(item)setTimeout(function(){ useAsset(item); },50);
      });
    });
  });
}
/* Fill the purchase flow from one of my things. */
function useAsset(a){
  // A home has two covers; the one already chosen wins, earthquake otherwise.
  var key=a.kind==="home"?(flow.peril==="storm"&&flow.chosen?"storm":"quake"):a.kind==="vehicle"?"car":"drought";
  if(flow.peril!==key||!flow.chosen)choosePeril(key);
  flow.asset=a.asset_id;
  if(a.latitude!=null&&a.longitude!=null)setPoint(a.latitude,a.longitude,a.place||"",a.country||null);
  flow.interest.what=a.label; flow.interest.inside=true; flow.interest.touched=false;
  if(a.country)flow.interest.country=a.country;
  if(a.address)flow.interest.address=Object.assign({},a.address);
  var z=a.size||{};
  if(a.kind==="home")flow.size={peril:flow.peril,kind:"home",building:z.building||"flat",area:String(z.area_m2||""),built:String(z.built||""),valid:false};
  if(a.kind==="field")flow.size={peril:"drought",kind:"field",crop:z.crop||"wheat",area:String(z.area_ha||""),unit:"hectare",valid:false};
  if(a.kind==="vehicle")flow.interest.modelYear=z.model_year||null;
  goStep(Math.max(flow.step, 2));
}
function assetChipsHtml(){
  var kind=(flow.peril==="quake"||flow.peril==="storm")?"home":flow.peril==="car"?"vehicle":flow.peril==="drought"?"field":null;
  if(!kind||!identity.token)return "";
  var mine=ASSETS.list.filter(function(a){return a.kind===kind;});
  if(!mine.length)return "";
  return '<div class="label" style="margin:0 0 6px">'+esc(t("From my profile"))+'</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'+mine.map(function(a){
    return '<button class="btn btn-line btn-sm" type="button" data-use-asset="'+esc(a.asset_id)+'" aria-pressed="'+(flow.asset===a.asset_id)+'">'+esc(a.label)+' <span class="fine">'+esc(assetSummary(a))+'</span></button>';
  }).join("")+'</div>';
}
function renderAssetChips(){
  var slot=$("asset-chips"); if(!slot)return;
  slot.innerHTML=assetChipsHtml();
  Array.prototype.forEach.call(slot.querySelectorAll("[data-use-asset]"),function(b){
    b.addEventListener("click",function(){ var a=ASSETS.list.filter(function(x){return x.asset_id===b.dataset.useAsset;})[0]; if(a)useAsset(a); });
  });
}
/* ---------------- adding balance ----------------
   The mirror of payouts: a bank transfer to the operator's account, or USDC
   sent from a wallet the person holds elsewhere. Announced here with an
   amount; the reply gives where to send it and the reference to write on it;
   the operator confirms what arrived and only then is the address credited. */
var FUNDING_NAMES={bank:N("Bank transfer"),rialo:N("From a Rialo wallet"),solana:N("From a Solana wallet"),evm:N("From an Ethereum wallet")};
var FUNDING_STATUS={waiting:N("waiting for the transfer to arrive"),received:N("received and credited"),cancelled:N("cancelled"),expired:N("expired, nothing arrived in 30 days")};
function fundingPanel(f){
  if(!f||!f.how||!f.how.methods.length)return "";
  var how=f.how, waiting=(f.requests||[]).filter(function(r){return r.status==="waiting";});
  var rows=(f.requests||[]).map(function(r){
    return '<tr><td class="mono">'+esc(r.reference)+'</td><td>'+esc(t(FUNDING_NAMES[r.method]||r.method))+'</td><td class="num">'+money(r.amount)+'</td>'+
      '<td>'+esc(t(FUNDING_STATUS[r.status]||r.status))+(r.status==="received"?' · '+money(r.received)+' USDC':'')+(r.note?' · '+esc(r.note):'')+'</td>'+
      '<td>'+(r.status==="waiting"?'<button class="btn btn-ghost btn-sm" type="button" data-fund-cancel="'+esc(r.request_id)+'">'+esc(t("Cancel"))+'</button>':'')+'</td></tr>';
  }).join("");
  var nets=how.networks||{};
  var netline=Object.keys(nets).length
    ? '<p class="fine"><b>'+esc(t("Wallet transfers are watched on {chains}.",
        {chains:listText(Object.keys(nets).map(function(k){return nets[k];}))}))+'</b></p>' : "";
  var testline=how.testnet
    ? '<div class="verdict" style="margin:8px 0"><p><b>'+esc(t("This is a test network."))+'</b> '+
      esc(t("Send test USDC only. Anything of value sent here is lost, and the balance it credits is not money either."))+'</p></div>' : "";
  return '<details class="more" id="funding-box"'+(waiting.length?' open':'')+'><summary>'+esc(t("Add balance"))+': <b>'+
      esc(waiting.length?t("{n} transfer waiting",{n:waiting.length}):t("bank transfer or a wallet"))+'</b></summary><div class="inner">'+
    testline+netline+
    '<p class="fine">'+esc(t("Balance here is USDC. Announce what you will send and how; you get the account or address to send it to and a reference to write on the transfer. When it arrives, the operator confirms it and your balance is credited. A bank transfer usually takes a working day."))+
      ((how.watched&&(how.watched.solana||how.watched.evm))?' '+esc(t("Deposits from a Solana or Ethereum wallet are seen on chain and credited within a minute of arriving; write the reference in the memo, or give the sending wallet below.")):'')+'</p>'+
    '<div class="seg" id="fund-method" role="radiogroup">'+how.methods.map(function(m,i){
      return '<button type="button" role="radio" data-m="'+m+'" aria-checked="'+(i===0)+'">'+(m==="rialo"?'<i class="rialo-mark" aria-hidden="true"></i>':'')+esc(t(FUNDING_NAMES[m]||m))+'</button>';
    }).join("")+'</div>'+
    '<div class="tform" style="margin-top:10px"><label><span>'+esc(t("Amount, USDC"))+'</span><input id="fund-amount" type="number" min="'+how.min_amount+'" max="'+how.max_amount+'" step="1" value="1000" style="max-width:160px"></label>'+
      '<label id="fund-sender-wrap" hidden><span>'+esc(t("Sending wallet"))+'</span><input id="fund-sender" spellcheck="false" style="min-width:330px"></label>'+
      '<button class="btn btn-primary btn-sm" type="button" id="fund-go">'+esc(t("Get the details"))+'</button></div>'+
    '<div id="fund-out"></div>'+
    (rows?'<div class="table-scroll" tabindex="0" role="region" aria-label="'+esc(t("Table, scrolls sideways"))+'" style="margin-top:12px"><table class="ttable"><thead><tr><th>'+esc(t("Reference"))+'</th><th>'+esc(t("How"))+'</th><th class="num">'+esc(t("Announced"))+'</th><th>'+esc(t("Status"))+'</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>':'')+
    '<p class="fine" id="fund-msg" role="status"></p></div></details>';
}
function fundingDetailsHtml(req,how){
  var lines;
  if(req.method==="bank"){
    var b=how.bank||{};
    lines=[[t("To"),b.account_name],[t("Bank"),b.bank],["IBAN",b.iban.replace(/(.{4})/g,"$1 ").trim()],[t("Amount"),money(req.amount)+" USDC "+t("(or its value in the account's currency)")],[t("Reference, written on the transfer"),req.reference]];
  }else{
    lines=[[t("Network"),(how.networks||{})[req.method]||""],[t("Send USDC to"),how[req.method]],
           [t("Amount"),money(req.amount)+" USDC"],[t("Memo or reference"),req.reference]];
  }
  var chain=(how.networks||{})[req.method]||"";
  var warn=req.method==="bank"?"":
    '<p style="margin-top:8px"><b>'+esc(t("Send it on {chain} and nowhere else.",{chain:chain}))+'</b> '+
    esc(t("The same address exists on other chains, and a transfer sent on one of those cannot be recovered."))+'</p>'+
    (how.testnet?'<p style="margin-top:8px"><b>'+esc(t("This is a test network."))+'</b> '+
      esc(t("Send test USDC only. Anything of value sent here is lost, and the balance it credits is not money either."))+'</p>':'');
  return '<div class="verdict '+(how.testnet&&req.method!=="bank"?"":"ok")+'" style="margin-top:10px"><p><b>'+esc(t("Send it exactly like this."))+'</b> '+esc(t("The reference is how the transfer is matched to your address; without it the money waits."))+'</p>'+warn+
    '<div class="holding" style="margin-top:8px">'+lines.filter(function(l){return l[1];}).map(function(l){
      return '<div class="hrow"><span>'+esc(l[0])+'</span><b class="mono" style="word-break:break-all">'+esc(l[1])+'</b></div>'; }).join("")+'</div></div>';
}
function bindFundingPanel(f){
  if(!f||!$("fund-method"))return;
  var how=f.how, method=how.methods[0];
  function show(){
    Array.prototype.forEach.call($("fund-method").querySelectorAll("button"),function(b){ b.setAttribute("aria-checked",String(b.dataset.m===method)); });
    $("fund-sender-wrap").hidden=method==="bank";
    $("fund-sender").placeholder=method==="evm"?"0x…":"base58";
  }
  Array.prototype.forEach.call($("fund-method").querySelectorAll("button"),function(b){
    b.addEventListener("click",function(){ method=b.dataset.m; show(); });
  });
  show();
  $("fund-go").addEventListener("click",function(){
    var go=$("fund-go"); go.disabled=true; $("fund-msg").textContent="";
    api("/api/funding",{method:"POST",token:identity.token,body:{method:method,amount:Number($("fund-amount").value),sender:$("fund-sender").value.trim()||undefined}})
      .then(function(r){ $("fund-out").innerHTML=fundingDetailsHtml(r.request,r.how); go.disabled=false; },
            function(e){ go.disabled=false; $("fund-msg").textContent=refusalText(e); });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-fund-cancel]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true;
      api("/api/funding/"+encodeURIComponent(b.dataset.fundCancel)+"/cancel",{method:"POST",token:identity.token})
        .then(function(){ renderMineExtras(); },function(e){ b.disabled=false; $("fund-msg").textContent=refusalText(e); });
    });
  });
}
function payoutPanel(p){
  if(!p)return "";
  var pref=p.preference||{method:"wallet"};
  var where=pref.method==="wallet"?t("To my address"):t(PAYOUT_NAMES[pref.method])+": "+pref.destination;
  var providers=p.mobile_providers||{};
  var orders=(p.orders||[]).map(function(o){
    return '<tr><td class="mono">'+esc(o.order_id)+'</td><td>'+esc(t(ORDER_KIND[o.kind]||o.kind))+'</td><td class="num">'+money(o.amount)+'</td>'+
      '<td>'+esc(o.currency)+'</td><td>'+esc(o.destination)+'</td><td>'+esc(t(PAYOUT_STATUS[o.status]||o.status))+
      (o.rail_reference?' · <span class="mono">'+esc(o.rail_reference)+'</span>':'')+'</td></tr>';
  }).join("");
  var canOut=pref.method&&pref.method!=="wallet";
  var cashout='<div class="holding" style="margin-top:14px"><div class="label" style="margin-bottom:6px">'+esc(t("Withdraw balance"))+'</div>'+
    (canOut?'<p class="fine">'+esc(t("Send part of your balance to the destination above: capital you took back from the pool, its returns, or a payout that landed here. It leaves your address now and is sent by hand for the moment; a transfer that fails comes back."))+'</p>'+
      '<div class="tform"><label><span>'+esc(t("Amount, USDC"))+'</span><input id="cash-amount" type="number" min="'+(p.min_cashout||10)+'" step="1" style="max-width:160px"></label>'+
      '<button class="btn btn-line btn-sm" type="button" id="cash-go">'+esc(t("Sign and withdraw"))+'</button></div>'
     :'<p class="fine">'+esc(t("To take balance out, first choose a bank account, a mobile wallet or a wallet on another chain above and save it."))+'</p>')+'</div>';
  return '<details class="more" id="payout-box"><summary>'+esc(t("Where payouts go"))+': <b>'+esc(where)+'</b></summary><div class="inner">'+
    '<div class="seg" id="pay-method" role="radiogroup">'+["wallet","bank","mobile_money","rialo","solana","evm"].map(function(m){
      return '<button type="button" role="radio" data-m="'+m+'" aria-checked="'+(pref.method===m)+'">'+(m==="rialo"?'<i class="rialo-mark" aria-hidden="true"></i>':'')+esc(t(PAYOUT_NAMES[m]))+'</button>';
    }).join("")+'</div>'+
    '<div class="tform" id="pay-bank" hidden>'+
      '<label><span>'+esc(t("IBAN"))+'</span><input id="pay-iban" autocomplete="off" spellcheck="false" placeholder="TR00 0000 0000 0000 0000 0000 00" style="min-width:290px"></label>'+
      '<label><span>'+esc(t("Name on the account"))+'</span><input id="pay-name" autocomplete="name"></label>'+
      '<p class="fine">'+esc(t("A bank transfer cannot be made without the name on the account. It is used for the transfer and for nothing else."))+' '+
      esc(t("Switching to another method erases the IBAN and name saved here. Transfers already sent keep their own record."))+'</p></div>'+
    '<div class="tform" id="pay-mobile" hidden>'+
      '<label><span>'+esc(t("Provider"))+'</span><select id="pay-provider">'+Object.keys(providers).map(function(k){
        return '<option value="'+esc(k)+'">'+esc(providers[k].name)+'</option>';}).join("")+'</select></label>'+
      '<label><span>'+esc(t("Country"))+'</span><select id="pay-country"></select></label>'+
      '<label><span>'+esc(t("Phone, with country code"))+'</span><input id="pay-phone" inputmode="tel" placeholder="+254712345678"></label></div>'+
    '<div id="pay-chain" hidden><div class="tform">'+
      '<label><span>'+esc(t("Wallet address"))+'</span><input id="pay-chain-addr" autocomplete="off" spellcheck="false" style="min-width:330px" value="'+esc(pref.rialo_address||"")+'"></label>'+
      '<button class="btn btn-line btn-sm" type="button" id="pay-connect" hidden>'+esc(t("Connect wallet"))+'</button></div>'+
      '<p class="fine" id="pay-chain-hint"></p></div>'+
    '<div><button class="btn btn-primary btn-sm" type="button" id="pay-save">'+esc(t("Sign and save"))+'</button></div>'+
    '<p class="fine">'+esc(p.rail==="manual"
      ? t("Payouts to a bank, a mobile wallet or a wallet on another chain are made by the issuing company or a licensed payment partner, in their currency, and each one is checked and sent by hand for now. Your details are kept only to make the payment and are shown back to you masked.")
      : t("Payouts to a bank or a mobile wallet are sent to a licensed payment partner as soon as they settle, in its currency. Your details are kept only to make the payment and are shown back to you masked."))+'</p>'+
    cashout+
    (orders?'<div class="table-scroll" tabindex="0" role="region" aria-label="'+esc(t("Table, scrolls sideways"))+'" style="margin-top:12px"><table class="ttable"><thead><tr><th>'+esc(t("Order"))+'</th><th>'+esc(t("Kind"))+'</th><th class="num">'+esc(t("Amount"))+'</th><th>'+
      esc(t("Currency"))+'</th><th>'+esc(t("To"))+'</th><th>'+esc(t("Status"))+'</th></tr></thead><tbody>'+orders+'</tbody></table></div>':'')+
    '<p class="fine" id="pay-msg" role="status"></p></div></details>';
}
var PAYOUT_STATUS={queued:N("waiting to be sent"),sent:N("sent"),paid:N("paid"),failed:N("failed, returned to your address")};
var ORDER_KIND={payout:N("payout"),refund:N("refund"),withdrawal:N("withdrawal")};
function bindPayoutPanel(p){
  if(!p||!$("pay-method"))return;
  var method=(p.preference||{}).method||"wallet";
  var providers=p.mobile_providers||{};
  function show(){
    Array.prototype.forEach.call($("pay-method").querySelectorAll("button"),function(b){ b.setAttribute("aria-checked",String(b.dataset.m===method)); });
    $("pay-bank").hidden=method!=="bank"; $("pay-mobile").hidden=method!=="mobile_money";
    var chain=CHAIN_WALLETS[method];
    $("pay-chain").hidden=!chain;
    if(chain){
      $("pay-chain-hint").textContent=t(chain.hint); $("pay-chain-addr").placeholder=t(chain.ph);
      $("pay-connect").hidden=!chain.connect;
    }
  }
  $("pay-connect").addEventListener("click",function(){
    var c=CHAIN_WALLETS[method]; if(!c||!c.connect)return;
    connectChainWallet(c.connect).then(function(a){ $("pay-chain-addr").value=a; $("pay-msg").textContent=""; },
      function(e){ $("pay-msg").textContent=e&&e.message?e.message:t("The wallet did not connect."); });
  });
  function countries(){
    var prov=providers[$("pay-provider").value]||{countries:[]};
    $("pay-country").innerHTML=prov.countries.map(function(c){return '<option value="'+c+'">'+esc(countryName(c))+'</option>';}).join("");
  }
  Array.prototype.forEach.call($("pay-method").querySelectorAll("button"),function(b){
    b.addEventListener("click",function(){ method=b.dataset.m; show(); });
  });
  $("pay-provider").addEventListener("change",countries);
  countries(); show();
  var cash=$("cash-go");
  if(cash)cash.addEventListener("click",function(){
    var amount=Number($("cash-amount").value);
    if(!(amount>0)){ $("pay-msg").textContent=t("Enter an amount."); return; }
    if(!confirm(t("Withdraw {amount} USDC to {where}? It leaves your address now.",{amount:money(amount),where:(p.preference||{}).destination||""})))return;
    cash.disabled=true; $("pay-msg").textContent=t("Signing…");
    signedCall("cashout",{amount:amount},"/api/payouts/cashout",function(){ return {account:identity.address,amount:amount}; })
      .then(function(){ renderMineExtras(); renderWho(); },function(e){ cash.disabled=false; $("pay-msg").textContent=refusalText(e); });
  });
  $("pay-save").addEventListener("click",function(){
    var terms={method:method};
    if(method==="bank"){ terms.iban=$("pay-iban").value.replace(/\s+/g,"").toUpperCase(); terms.holder_name=$("pay-name").value.trim(); }
    if(method==="mobile_money"){ terms.provider=$("pay-provider").value; terms.country=$("pay-country").value; terms.phone=$("pay-phone").value.replace(/[\s()-]/g,""); }
    if(CHAIN_WALLETS[method]){ terms.rialo_address=$("pay-chain-addr").value.trim(); }
    var go=$("pay-save"); go.disabled=true; $("pay-msg").textContent=t("Signing…");
    signedCall("payout",terms,"/api/payouts/preference",function(){
      var body={account:identity.address}; for(var k in terms)body[k]=terms[k]; return body;
    }).then(function(){ renderMineExtras(); },function(e){ go.disabled=false; $("pay-msg").textContent=refusalText(e); });
  });
}
var MANDATE_PERILS=[["flight_delay",N("Flight delay")],["earthquake",N("Earthquake")],["drought",N("Drought")],["vehicle_flood",N("Vehicle flood")],["storm",N("Storm")]];
function mandatePanel(m){
  if(!m)return "";
  var inner;
  var mand=m.mandate;
  if(!m.rider_can_buy){
    inner='<p class="fine">'+esc(t("On this deployment Rider cannot buy: no purchase Latch is configured. It prices and prepares, and you sign."))+'</p>';
  }else if(mand){
    var here=!!mandateToken();
    inner='<div class="holding">'+
      '<div class="hrow"><span>'+esc(t("Most per policy"))+'</span><b>'+money(mand.max_premium_per_policy)+'</b></div>'+
      '<div class="hrow"><span>'+esc(t("Spent of the total"))+'</span><b>'+money(mand.spent)+' / '+money(mand.max_premium_total)+'</b></div>'+
      '<div class="hrow"><span>'+esc(t("Largest cover"))+'</span><b>'+f0.format(mand.max_limit_per_policy)+'</b></div>'+
      '<div class="hrow"><span>'+esc(t("Covers"))+'</span><b>'+esc(mand.perils.map(function(k){
         var f=MANDATE_PERILS.filter(function(p){return p[0]===k;})[0]; return f?t(f[1]):k;}).join(", "))+'</b></div>'+
      '<div class="hrow"><span>'+esc(t("Until"))+'</span><b>'+esc(new Date(mand.expires_at*1000).toLocaleDateString(LANG))+'</b></div></div>'+
      (here?'':'<p class="fine">'+esc(t("This permission was given on another device. Rider on this device cannot use it; give it again here to replace it."))+'</p>')+
      '<div><button class="btn btn-line btn-sm" type="button" id="mand-revoke">'+esc(t("Withdraw the permission"))+'</button></div>';
  }else{
    inner='<p>'+esc(t("Let Rider buy cover for you when you ask it to, inside limits you sign here. It cannot go past them, whatever it is told, and anything it buys can be cancelled for a full refund for {hours} hours.",{hours:m.cooling_off_hours}))+'</p>'+
      '<div class="tform">'+
      '<label><span>'+esc(t("Most per policy"))+'</span><input id="mand-per" type="number" min="1" value="100"></label>'+
      '<label><span>'+esc(t("Total"))+'</span><input id="mand-total" type="number" min="1" value="300"></label>'+
      '<label><span>'+esc(t("Largest cover"))+'</span><input id="mand-limit" type="number" min="100" max="10000" value="2000"></label>'+
      '<label><span>'+esc(t("Days"))+'</span><input id="mand-days" type="number" min="1" max="90" value="30"></label></div>'+
      '<div class="checks" id="mand-perils">'+MANDATE_PERILS.map(function(p){
        return '<label><input type="checkbox" value="'+p[0]+'"'+(p[0]==="flight_delay"?" checked":"")+'> '+esc(t(p[1]))+'</label>';
      }).join("")+'</div>'+
      '<div><button class="btn btn-primary btn-sm" type="button" id="mand-go">'+esc(t("Sign the permission"))+'</button></div>';
  }
  return '<details class="more" id="mandate-box"><summary>'+esc(t("Rider's permission to buy"))+': <b>'+
    esc(mand?t("given"):t("not given"))+'</b></summary><div class="inner">'+inner+
    '<p class="fine" id="mand-msg" role="status"></p></div></details>';
}
function bindMandatePanel(m){
  if(!m)return;
  var revoke=$("mand-revoke");
  if(revoke)revoke.addEventListener("click",function(){
    revoke.disabled=true;
    signedCall("mandate",{revoke:true},"/api/mandate/revoke",function(){return {account:identity.address};})
      .then(function(){ keepMandate(null); renderMineExtras(); },function(e){ revoke.disabled=false; $("mand-msg").textContent=refusalText(e); });
  });
  var go=$("mand-go");
  if(!go)return;
  go.addEventListener("click",function(){
    var perils=Array.prototype.filter.call($("mand-perils").querySelectorAll("input"),function(i){return i.checked;})
      .map(function(i){return i.value;}).sort();
    var terms={max_premium_per_policy:Number($("mand-per").value), max_premium_total:Number($("mand-total").value),
      max_limit_per_policy:Number($("mand-limit").value), perils:perils.join(","), days:Number($("mand-days").value)};
    go.disabled=true; $("mand-msg").textContent=t("Signing…");
    var screening=flow.statements&&flow.statements.sanctions_clear
      ? Promise.resolve(flow.statements.sanctions_clear)
      : api("/api/eligibility/demo",{method:"POST",body:{address:identity.address,purpose:"sanctions_clear"}})
          .then(function(r){ flow.statements.sanctions_clear=r.attestation; return r.attestation; });
    screening.then(function(att){
      return signedCall("mandate",terms,"/api/mandate",function(){
        var body={account:identity.address,country:(flow.interest&&flow.interest.country)||"TR",attestations:[att]};
        for(var k in terms)body[k]=terms[k]; return body;
      });
    }).then(function(reply){ keepMandate(reply.token); renderMineExtras(); },
      function(e){ go.disabled=false; $("mand-msg").textContent=refusalText(e); });
  });
}


