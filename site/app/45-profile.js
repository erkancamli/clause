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



/* ---------------- adding balance ----------------
   The mirror of payouts: a bank transfer to the operator's account, or USDC
   sent from a wallet the person holds elsewhere. Announced here with an
   amount; the reply gives where to send it and the reference to write on it;
   the operator confirms what arrived and only then is the address credited. */














