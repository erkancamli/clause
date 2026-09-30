/* ---- what the chain this protocol runs on has published -----------------
   Read by the protocol, not by the browser: one fetch every few hours from
   one server is a polite use of somebody else's front page; a fetch per
   visitor is not. The list is theirs, so the titles are theirs too and are
   not translated -- a title is a name.

   Three states, and the third is the one that matters: the source answered,
   the source has not answered yet, and the source stopped answering after it
   had. The last shows what it last said and says how old that is, rather
   than showing nothing as though Rialo had published nothing. */
var RIALO_READ=false;
function renderRialo(){
  var box=$("rialo-out"), said=$("rialo-said");
  if(!box)return;
  if(RIALO_READ)return;
  RIALO_READ=true;
  said.textContent=t("Reading the sources…");
  api("/api/live/rialo",{timeout:12000}).then(function(reply){
    var rows=(reply&&reply.items)||[];
    if(!rows.length){
      said.textContent=t("Rialo's front page could not be read just now.");
      box.innerHTML="";
      RIALO_READ=false;
      return;
    }
    // agoText already says "ago" in the reader's language, so neither of
    // these sentences says it a second time.
    said.textContent=reply.stale
      ? t("Last read {ago}, and the page has not answered since.",{ago:agoText(reply.age_seconds)})
      : t("Read from rialo.io, {ago}.",{ago:agoText(reply.age_seconds)});
    box.innerHTML='<div class="pubs">'+rows.map(function(row){
      return '<a class="pub" href="'+esc(row.url)+'" target="_blank" rel="noopener noreferrer">'+
        '<span class="no">'+esc(row.number||"·")+'</span>'+
        '<span class="nm">'+esc(row.title)+'</span>'+
        (row.when?'<span class="wn">'+esc(row.when)+'</span>':"")+
        (row.summary?'<span class="sm">'+esc(row.summary)+'</span>':"")+
        '</a>';
    }).join("")+'</div>';
  },function(){
    said.textContent=t("Rialo's front page could not be read just now.");
    RIALO_READ=false;
  });
}

/* ---- the papers that show the thing is yours ---------------------------
   These are asked for after the purchase, not during it. The insurer decides
   afterwards in any case, and nothing about the price depends on them, so
   putting a file picker in front of somebody who is still choosing cover
   only delays the cover. They can be sent from the screen that follows the
   purchase, or from My cover at any time while the application is open. */
var DOC_TYPES=["application/pdf","image/png","image/jpeg"];
function badDocuments(files){
  if(files.length>4)return t("At most 4 documents.");
  for(var i=0;i<files.length;i++){
    if(files[i].size>4000000)return t("Each document is at most 4 MB.");
    if(DOC_TYPES.indexOf(files[i].type)<0)return t("Documents are PDF, PNG or JPEG.");
  }
  return null;
}
function docPickerHtml(id,label){
  return '<div class="field" style="margin-top:10px"><label class="label" for="'+esc(id)+'">'+esc(label)+'</label>'+
    '<input id="'+esc(id)+'" type="file" accept="application/pdf,image/png,image/jpeg" multiple>'+
    '<p class="fine" id="'+esc(id)+'-msg" role="status"></p></div>';
}
function bindDocPicker(id,app,done){
  var input=$(id), out=$(id+"-msg");
  if(!input||input.dataset.bound)return;
  input.dataset.bound="1";
  input.addEventListener("change",function(){
    var files=Array.prototype.slice.call(input.files||[]), bad=badDocuments(files);
    if(bad){ input.value=""; out.textContent=bad; return; }
    if(!files.length){ out.textContent=""; return; }
    input.disabled=true;
    sealAndSend(files,app,out).then(function(sent){
      input.value=""; input.disabled=false;
      if(sent&&done)done();
    },function(){ input.disabled=false; });
  });
}
function sealAndSend(files,a,out){
  out.textContent=t("Sealing…");
  return api("/api/applications/recipient?carrier_id="+encodeURIComponent(a.carrier_id||"")).then(function(who){
    if(!who.reading_key){
      out.textContent=t("Not sent: {company} has no reading key yet, so nothing can be sealed to it. It will ask for its documents another way.",{company:ts(who.name||"")});
      return false;
    }
    return Promise.all(files.map(function(f){ return sealFile(f,who.reading_key,a.app_id); })).then(function(sealed){
      out.textContent=t("Sending…");
      return api("/api/applications/"+encodeURIComponent(a.app_id)+"/documents",{method:"POST",timeout:60000,token:identity.token,body:{documents:sealed}});
    }).then(function(reply){
      out.textContent=t("{n} sent, sealed to {company}. Only that company's browser can open them; you will see on My cover when it does.",
        {n:reply.documents.length,company:ts(who.name||"")});
      return true;
    });
  }).catch(function(e){ out.textContent=refusalText(e); return false; });
}
function showApplied(reply){
  var a=reply.application;
  LAST_DONE=function(){ showApplied(reply); };
  goStep(DONE_STEP, true);
  $("done-title").removeAttribute("data-i18n"); $("done-state").removeAttribute("data-i18n");
  $("done-title").textContent=t("Your application is with the insurer.");
  $("done-state").textContent=t("Waiting for the insurer's checks");
  $("done-id").textContent=a.app_id;
  $("done-copy").textContent=t("Nothing is written yet and your premium is held, not taken. The company that would issue this policy does its checks and approves or rejects it; approved, the policy is written at the price you agreed and armed on chain; rejected, or not decided within three days, all of the premium comes back.");
  $("done-kvs").innerHTML=
    kv(t("Cover"),f0.format(a.limit)+' USDC')+
    kv(a.plan?t("First payment, held"):t("Premium held"),money(a.first_payment||a.total||a.premium))+
    (a.plan?kv(t("Then"),esc(t("{n} more payments of {amount}",{n:a.plan.count-1,amount:money(a.plan.amount)}))):"")+
    kv(t("Issued by"),esc(ts((chosenOffer()||{}).name||"")))+
    kv(t("The insurer checks"),esc(a.checks.map(function(c){return t(CHECK_NAMES[c]||c);}).join(", ")))+
    kv(t("Decision due by"),esc(new Date(a.decide_by*1000).toLocaleString(LOCALES[LANG]||"en-US")))+
    kv(t("Held by"),esc(short(identity.address)),"mono")+
    ((a.documents||[]).length?'<div class="kv"><div class="k">'+esc(t("Documents"))+'</div><div class="v">'+
      esc((a.documents||[]).map(function(d){return d.filename;}).join(", "))+'</div></div>':'');
  // The one thing still to do, offered where the buyer is rather than made a
  // condition of getting here.
  var ask=$("done-docs-ask");
  if(ask){
    ask.innerHTML=(a.checks||[]).indexOf("ownership")>=0
      ? '<p class="fine">'+esc(t("The company will want to see the paper that shows it is yours. Send it now, or later from My cover; it does not have to be today."))+'</p>'+
        docPickerHtml("done-docs-pick",t("Title deed, lease or vehicle registration"))
      : "";
    bindDocPicker("done-docs-pick",a,null);
  }
  $("done-pred").innerHTML="";
  $("done-links").innerHTML=
    '<a class="btn btn-line" href="#/mine">'+esc(t("See it on My cover"))+'</a>'+
    '<a class="btn btn-ghost" href="'+esc(API+"/api/applications/"+encodeURIComponent(a.app_id)+"/contract")+'" target="_blank" rel="noopener" id="contract-dl">'+esc(t("Download the contract"))+'</a>'+
    (!flow.asset&&flow.peril!=="flight"?'<button class="btn btn-ghost" type="button" id="save-asset">'+esc(flow.peril==="car"?t("Save this car to my profile"):flow.peril==="drought"?t("Save this field to my profile"):t("Save this home to my profile"))+'</button>':'')+
    '<button class="btn btn-ghost" type="button" id="again">'+esc(t("Cover something else"))+'</button>';
  bindAgain();
  var saveAsset=$("save-asset");
  if(saveAsset)saveAsset.addEventListener("click",function(){
    saveAsset.disabled=true;
    var at=coordinates(), z=sizePayload()||{};
    var body={kind:flow.peril==="car"?"vehicle":flow.peril==="drought"?"field":"home",label:flow.interest.what||a.what||"",
      place:flow.place||"",country:flow.placeCountry||flow.interest.country||"",latitude:at?at.latitude:null,longitude:at?at.longitude:null,
      size:flow.peril==="car"?{model_year:flow.interest.modelYear}:flow.peril==="drought"?{crop:z.crop,area_ha:z.area_ha}:{building:z.building,area_m2:z.area_m2,built:z.built},
      address:flow.interest.address||undefined};
    api("/api/assets",{method:"POST",token:identity.token,body:body}).then(function(r){ ASSETS.list=r.assets||[]; ASSETS.at=Date.now(); flow.asset=r.asset.asset_id;
      saveAsset.textContent=t("Saved to my profile"); },function(e){ saveAsset.disabled=false; saveAsset.textContent=refusalText(e); });
  });
  // The contract needs the session; fetched and offered as a file rather than a bare link.
  $("contract-dl").addEventListener("click",function(e){
    e.preventDefault();
    fetch(API+"/api/applications/"+encodeURIComponent(a.app_id)+"/contract",{headers:{authorization:"Bearer "+identity.token}}).then(function(r){
      if(!r.ok)throw new Error("refused"); return r.text();
    }).then(function(text){
      var blob=new Blob([text],{type:"text/plain"}), url=URL.createObjectURL(blob), link=document.createElement("a");
      link.href=url; link.download=a.app_id+"-contract.txt"; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(function(){URL.revokeObjectURL(url);},60000);
    }).catch(function(){ $("contract-dl").textContent=t("Could not fetch the contract; open My cover and try again."); });
  });
}
/* Where this cover can be reached from, said on the one screen that can say it.

   The key is made on this device and never leaves it, which is the whole
   reason nothing here asks for a name or an email. It also means a phone lost
   with nothing linked to it takes the cover with it: the payout is credited to
   the address that key derives (pool.py, PAYOUT to policy.holder), and nobody
   else can sign for it. A linked Ethereum wallet does not change that — it
   only decides where the token is minted.

   The site has always said the first half of this plainly and has never said
   the second. The last screen of a purchase is where it belongs, because a
   product that collects no email has no second chance to reach anybody, and
   because linking is free and takes one press.

   Linking gives the protocol no name and no email either: Privy checks who
   somebody is, the protocol stores only which address they act as, and each
   later device is then allowed to sign for that same address. */
function reachHtml(){
  if(identity.via==="privy")
    return '<p class="fine">'+esc(t("This cover follows your account, so another device can reach it."))+'</p>';
  return '<p class="fine" id="done-reach-said">'+
    esc(t("This cover lives on this device. The key that reaches it was made here and "+
          "never leaves, so a device lost with nothing linked to it takes the cover "+
          "and the payout with it."))+'</p><div id="done-reach-do"></div>';
}
function bindReach(){
  var slot=$("done-reach-do"); if(!slot)return;
  privyConfig().then(function(config){
    if(!config||!config.enabled)return;
    slot.innerHTML='<button class="btn btn-line btn-sm" type="button" id="done-link">'+
      esc(t("Link an account so another device can reach it"))+'</button>';
    $("done-link").addEventListener("click",function(){
      var button=$("done-link"); button.disabled=true;
      privySignIn().then(function(){ renderWho(); $("done-reach").innerHTML=reachHtml(); },
                         function(){ button.disabled=false; });
    });
  },function(){});
}
function showDone(reply){
  var policy=reply.policy;
  LAST_DONE=function(){ showDone(reply); };
  goStep(DONE_STEP, true);
  $("done-title").removeAttribute("data-i18n"); $("done-state").removeAttribute("data-i18n");
  $("done-title").textContent=t("You are covered. There is nothing else to do.");
  $("done-state").textContent=t("Armed on chain");
  $("done-id").textContent=policy.policy_id;
  $("done-copy").textContent=
    t("The subscription is registered on chain against your address. If the reading "+
    "crosses your trigger, the payout runs in the block that carries it. You will "+
    "not be asked to sign again, and there is no claim to file.");
  $("done-kvs").innerHTML=
    kv(t("Cover"),f0.format(policy.limit)+' USDC')+
    kv(t("You paid"),money(policy.premium))+
    kv(t("Payout currency"),esc(cashName(riskCountry(), (reply.compliance||{}).settlement)))+
    kv(t("Runs for"),esc(t("{days} days",{days:f0.format(policy.term_days)})))+
    kv(t("Measured by"),esc(sourceName()))+
    kv(t("Subscription"),esc(reply.account||"—"),"mono")+
    kv(t("Held by"),esc(short(policy.holder||identity.address)),"mono")+
    ((reply.compliance&&reply.compliance.carrier&&reply.compliance.carrier.specimen)
      ? kv(t("Is this real cover"),esc(t("No. The issuer is a stand in and holds no licence."))) : '');
  $("done-pred").innerHTML=predicateHtml();
  $("done-reach").innerHTML=reachHtml(); bindReach();
  $("done-links").innerHTML=
    '<a class="btn btn-line" href="#/proof/'+encodeURIComponent(policy.policy_id)+'">'+esc(t("See its record on chain"))+'</a>'+
    '<a class="btn btn-line" href="#/mine">'+esc(t("What you hold"))+'</a>'+
    '<button class="btn btn-ghost" type="button" id="again">'+esc(t("Cover something else"))+'</button>';
  bindAgain();
}

/* When the protocol cannot be reached the page still walks the flow, because
   the flow is worth seeing. It says plainly that nothing was bought. */
function demoDone(){
  var q=quote();
  var id="CLS-"+Math.random().toString(16).slice(2,8).toUpperCase();
  goStep(DONE_STEP, true);
  $("done-id").textContent=id;
  $("done-copy").textContent=
    t("Nothing was bought. The protocol is not reachable from this page right now, "+
    "so this is the shape of what would have happened, priced by the same model "+
    "the protocol runs.");
  $("done-kvs").innerHTML=
    kv(t("Cover"),f0.format(flow.limit)+' USDC')+
    kv(t("Premium"),money(q.premium)+' USDC')+
    kv(t("Runs for"),esc(t("{days} days",{days:PERILS[flow.peril].term})))+
    kv(t("Measured by"),esc(sourceName()));
  $("done-pred").innerHTML=predicateHtml();
  $("done-links").innerHTML=
    '<a class="btn btn-line" href="#/pool">'+esc(t("See what happens when an event hits"))+'</a>'+
    '<button class="btn btn-ghost" type="button" id="again">'+esc(t("Cover something else"))+'</button>';
  bindAgain();
}

/* One labelled figure. The label is escaped here; the value arrives as HTML. */
function kv(label,valueHtml,cls){
  return '<div class="kv"><div class="k">'+esc(label)+'</div><div class="v'+(cls?" "+cls:"")+'">'+
    valueHtml+'</div></div>';
}

function bindAgain(){
  var button=$("again");
  if(button)button.addEventListener("click",function(){
    resetFlow(); renderStep();
  });
}


/* ---------------- what you hold ----------------
   The same two questions a live chain answers with get_subscription and
   get_triggered_transactions, asked of your address and nobody else's. */

var MINE_SIGNIN=null;

function minePanel(title,body,action){
  return '<div class="panel" style="padding:26px;display:grid;gap:14px;max-width:560px">'+
    '<h2 style="font-size:19px">'+esc(title)+'</h2>'+
    '<p style="font-size:14.5px;color:var(--ink-2)">'+esc(body)+'</p>'+
    (action||"")+'</div>';
}

var POLICY_STATUS={active:N("active"),paid:N("paid"),expired:N("expired"),
  lapsed:N("lapsed"),cancelled:N("cancelled")};

function renderMine(){
  var box=$("mine-out");
  if(MINE_SIGNIN===null)MINE_SIGNIN=box.innerHTML;
  if(!link.checked){ whenLinked().then(renderMine); return; }

  if(!link.live){
    box.innerHTML=minePanel(t("Not connected"),
      t("This page cannot reach the protocol, so there is nothing real to show you. "+
      "It will not invent a portfolio to fill the space."),"");
    return;
  }
  if(!identity.token){
    box.innerHTML=MINE_SIGNIN;
    translateStatic(box);
    $("mine-go").addEventListener("click",function(){
      // Someone new chooses how to sign in; someone this browser already
      // knows is signed back in the way they chose before.
      if(!identity.address){
        chooseSignIn("sign-in").then(renderMine,function(){});
        return;
      }
      $("mine-go").disabled=true; $("mine-go").textContent=t("Signing in…");
      signIn().then(function(){ renderWho(); renderMine(); },function(){
        // A button that redraws, not a link to the page already open: a link
        // to the current address changes nothing, which is how "Try again"
        // came to do nothing at all.
        box.innerHTML=minePanel(t("That did not work"),
          t("The protocol did not accept the signature. Nothing changed."),"")+
          '<p style="margin-top:12px"><button class="btn btn-line" type="button" id="mine-retry">'+esc(t("Try again"))+'</button></p>';
        var retry=$("mine-retry");
        if(retry)retry.addEventListener("click",function(){ renderMine(); });
      });
    });
    if(identity.address){
      $("mine-go").textContent=t("Continue as {address}",{address:short(identity.address)});
    }
    var forget=$("mine-forget");
    if(forget&&identity.address){
      forget.hidden=false;
      forget.addEventListener("click",function(){forgetDevice().then(renderMine);});
    }
    return;
  }

  box.innerHTML='<div class="panel" style="padding:24px">'+esc(t("Reading the chain…"))+'</div>';
  api("/api/portfolio",{token:identity.token}).then(function(reply){
    box.innerHTML=mineHtml(reply);
    bindTokens(box);
    bindCancels(box); bindContractCopies(box); bindComplaints(box);
    Array.prototype.forEach.call(document.querySelectorAll("[data-renew]"),function(b){
      b.addEventListener("click",function(){
        var p=(reply.policies||[]).filter(function(x){return x.policy_id===b.dataset.renew;})[0];
        if(p)renewFrom(p);
      });
    });
    var faucetGo=$("faucet-go");
    if(faucetGo)faucetGo.addEventListener("click",function(){
      faucetGo.disabled=true; faucetGo.textContent=t("Adding…");
      api("/api/wallet/faucet",{method:"POST",token:identity.token}).then(function(){ renderMine(); },
        function(e){ faucetGo.textContent=refusalText(e); });
    });
    renderMineExtras(reply.policies||[]);
    renderMineApplications();
    renderNfts(reply.policies||[]);
    var signout=$("mine-signout");
    if(signout)signout.addEventListener("click",function(){ signOut(); renderMine(); });
    var forget=$("mine-forget2");
    if(forget)forget.addEventListener("click",function(){
      forgetDevice().then(function(){location.hash="#/mine";renderMine();});
    });
  },function(error){
    if(error&&error.status===401){setSession(null);renderMine();return;}
    box.innerHTML=minePanel(t("Could not read it"),
      t("The protocol did not answer. Nothing is shown rather than something guessed."),"");
  });
}

function mineHtml(reply){
  var view=reply.portfolio||{},policies=reply.policies||[],settlements=reply.settlements||[];
  var out='<div class="holding">'+
    '<div class="hrow"><span>'+esc(t("Address"))+'</span><b class="mono">'+esc(view.short||short(identity.address))+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Balance"))+'</span><b>'+money(view.balance||0)+' USDC'+
      (reply.faucet&&reply.faucet.on?' <button class="btn btn-line btn-sm" type="button" id="faucet-go" style="margin-left:10px">'+
        esc(t("Add {amount} demo USDC",{amount:f0.format(reply.faucet.amount)}))+'</button>':'')+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Cover in force"))+'</span><b>'+money(view.cover_in_force||0)+' USDC</b></div>'+
    '<div class="hrow"><span>'+esc(t("Armed"))+'</span><b>'+f0.format(view.policies_open||0)+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Settled"))+'</span><b>'+f0.format(view.policies_settled||0)+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Profile"))+'</span><b><a class="btn btn-line btn-sm" href="#/profile">'+esc(t("My things, wallets, X"))+'</a></b></div>'+
    '</div><div id="mine-due"></div><div id="mine-papers"></div><div id="mine-nfts"></div><div id="mine-apps"></div><div id="mine-extras" class="mine-extras"></div>';

  if(!policies.length){
    out+='<div style="margin-top:22px">'+minePanel(t("Nothing here yet"),
      t("This address holds no cover. Anything you buy will appear here the block it "+
      "is registered."),'<a class="btn btn-primary" href="#/cover">'+esc(t("Get cover"))+'</a>')+'</div>';
    return out;
  }

  out+='<div style="margin-top:26px;display:grid;gap:14px">';
  policies.forEach(function(policy){
    var settled=settlements.filter(function(item){return item.policy_id===policy.policy_id;});
    var paid=settled.reduce(function(total,item){return total+(item.amount||0);},0);
    out+='<div class="policy-card">'+
      '<div class="bar"><span class="lamp'+(policy.status==="active"?"":" off")+'"></span>'+
      '<span class="label">'+esc(t(POLICY_STATUS[policy.status]||policy.status))+'</span>'+
      '<span class="right label mono">'+esc(policy.policy_id)+'</span></div>'+
      '<div class="body"><div class="kvs">'+
        kv(ts(policy.peril_name),esc(policy.subject_text))+
        kv(t("Cover"),f0.format(policy.limit)+' USDC')+
        kv(t("Premium paid"),money(policy.premium))+
        kv(paid?t("Paid out"):t("Runs for"),
          paid?money(paid)+" USDC":esc(t("{days} days",{days:f0.format(policy.term_days)})))+
        /* Cover starts after the peril's waiting period, so the day it starts
           and the day it was bought are different days, and which one a
           policy is in decides whether an event today pays. It is shown
           until it has passed and then there is nothing to say. */
        (policy.status==="active"&&policy.starts_at&&policy.starts_at>Date.now()/1000
          ?kv(t("Starts on"),esc(new Date(policy.starts_at*1000).toLocaleDateString(LANG))):"")+
        (policy.status==="active"&&policy.ends_at?kv(t("Ends on"),esc(new Date(policy.ends_at*1000).toLocaleDateString(LANG))):"")+
      '</div>'+
      (policy.status==="active"&&policy.ends_at&&policy.ends_at-Date.now()/1000<30*86400?'<div class="verdict" style="margin:0 0 12px"><p>'+
        esc(t("This cover ends in {days} days. Renew it and the new term runs from the day the insurer approves it, at today's price.",{days:Math.max(0,Math.ceil((policy.ends_at-Date.now()/1000)/86400))}))+
        ' <button class="btn btn-primary btn-sm" type="button" data-renew="'+esc(policy.policy_id)+'">'+esc(t("Renew"))+'</button></p></div>':'')+
      /* The case the page used to pass over in silence. A policy that ran its
         term and ended says "lapsed" and nothing else, which does not tell
         somebody the thing they need to know: that they have no cover now. */
      (policy.status==="lapsed"&&policy.ends_at&&Date.now()/1000-policy.ends_at<30*86400?'<div class="verdict" style="margin:0 0 12px"><p>'+
        esc(t("This cover ended {days} days ago and you have had none since. Buying it again starts a new term from the day the insurer approves it, at today's price; the days in between were not covered and cannot be.",{days:Math.max(1,Math.floor((Date.now()/1000-policy.ends_at)/86400))}))+
        ' <button class="btn btn-line btn-sm" type="button" data-renew="'+esc(policy.policy_id)+'">'+esc(t("Buy it again"))+'</button></p></div>':'')+
      (policy.settlement_note?'<p style="font-size:13.5px;color:var(--ink-2)">'+
        tsHtml(policy.settlement_note)+'</p>':'')+
      ((policy.metadata||{}).reinstated?'<p class="fine">'+esc(t("Put back in force on {date}: an earlier build had closed it by the demonstration's clock while its term was still running.",{date:new Date(policy.metadata.reinstated.at*1000).toLocaleDateString(LANG)}))+'</p>':'')+
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">'+
        '<a class="btn btn-line btn-sm" href="#/proof/'+encodeURIComponent(policy.policy_id)+
        '">'+esc(t("Why"))+'</a>'+
        ((policy.metadata||{}).token?'<button class="btn btn-ghost btn-sm" type="button" data-token="'+esc(policy.policy_id)+'">'+
          esc(t("Policy token"))+'</button><span class="fine">'+esc(t("Non-transferable, held by your address"))+'</span>':'')+
        cancelHtml(policy)+autoRenewHtml(policy)+
      '</div>'+
      '<div data-complaint-for="'+esc(policy.policy_id)+'"></div>'+
      '</div></div>';
  });
  out+='</div><div style="margin-top:20px;display:flex;gap:8px;flex-wrap:wrap">'+
       '<button class="btn btn-line btn-sm" type="button" id="mine-signout">'+esc(t("Sign out"))+'</button>'+
       '<button class="btn btn-ghost btn-sm" type="button" '+
       'id="mine-forget2">'+esc(t("Forget this device"))+'</button></div>';
  return out;
}


