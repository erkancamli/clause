/* ---------------- buying it ----------------
   Three things have to hold, and all three are checked before money moves: the
   buyer proves they hold the key by signing these exact terms, the cover is
   lawful where they are and capped by what they declared, and the pool can
   carry it. The signature covers the terms, so a captured request cannot come
   back as a larger policy. */

var dlg=$("signin");

/* One sign in, asked for wherever something personal happens: buying cover,
   proving residency, opening what you hold. Two doors, both honest about what
   they keep. Resolves once signed in; rejects if the person closes it. */
var CHOOSING=null;
function chooseSignIn(purpose){
  if(identity.address&&identity.token)return Promise.resolve();
  if(CHOOSING)return CHOOSING.promise;
  var pending={};
  pending.promise=new Promise(function(resolve,reject){pending.resolve=resolve;pending.reject=reject;});
  CHOOSING=pending;
  $("bio-text").textContent=purpose==="buy"
    ? t("You will be asked to confirm once, for this policy and no other")
    : t("Nothing is bought by signing in");
  // The header asks who is signing in; a purchase or a registration already
  // knows the answer.
  $("dlg-role").hidden=purpose!=="sign-in";
  $("dlg-operator").hidden=purpose!=="sign-in";
  setRole(purpose==="company"?"company":purpose==="sign-in"?getRole():"person");
  $("dlg-error").hidden=true;
  $("dlg-go").disabled=false; $("dlg-privy").disabled=false;
  privyConfig().then(function(config){ $("dlg-privy").dataset.off=config.enabled?"0":"1"; $("dlg-privy").hidden=!config.enabled||getRole()==="admin"; });
  if(typeof dlg.showModal==="function")dlg.showModal(); else dlg.setAttribute("open","");
  return pending.promise;
}
function finishChoosing(error){
  var pending=CHOOSING; CHOOSING=null;
  if(!pending)return;
  if(error)pending.reject(error); else pending.resolve();
}
function chooseWith(button, work){
  $("dlg-go").disabled=true; $("dlg-privy").disabled=true;
  $("dlg-error").hidden=true;
  work().then(function(){
    dlg.close(); renderWho(); finishChoosing(null);
  },function(error){
    $("dlg-go").disabled=false; $("dlg-privy").disabled=false;
    var closed=error&&/closed|exited|cancel/i.test(String(error.message||error));
    if(closed)return;
    $("dlg-error").hidden=false;
    $("dlg-error").textContent=t("The sign in did not complete. Nothing changed.");
  });
}
$("dlg-go").addEventListener("click",function(){ chooseWith(this, function(){
  // Choosing the device door after a Privy sign in on this browser starts a
  // separate, device only identity; the Privy one is forgotten here.
  var forget=identity.via==="privy"
    ? idbPut(KEYSTORE,{pair:identity.key,address:identity.device}).catch(function(){})
    : Promise.resolve();
  if(identity.via==="privy"){ identity.via=null; identity.address=identity.device; }
  return forget.then(deviceSignIn);
}); });
/* Privy draws its own window. Left under this dialog, which is modal and sits
   in the browser's top layer, that window is drawn but can never be reached:
   the sign in just waits. So this dialog steps aside while Privy asks, and
   comes back if the person closes Privy without finishing. */
var HANDING_OFF=false;
$("dlg-privy").addEventListener("click",function(){
  $("dlg-error").hidden=true;
  HANDING_OFF=true; dlg.close();
  privySignIn().then(function(){
    renderWho(); finishChoosing(null);
  },function(error){
    if(!CHOOSING)return;
    $("dlg-go").disabled=false; $("dlg-privy").disabled=false;
    if(typeof dlg.showModal==="function")dlg.showModal(); else dlg.setAttribute("open","");
    var closed=error&&/closed|exited|cancel/i.test(String(error.message||error));
    if(closed)return;
    $("dlg-error").hidden=false;
    $("dlg-error").textContent=t("The sign in did not complete. Nothing changed.");
  });
});
$("dlg-cancel").addEventListener("click",function(){ dlg.close(); });
$("dlg-op-go").addEventListener("click",function(){
  var token=$("dlg-op-token").value.trim(), name=$("dlg-op-name").value.trim(), go=$("dlg-op-go");
  if(!token){ $("dlg-error").hidden=false; $("dlg-error").textContent=t("The operator token is what this screen is behind."); return; }
  go.disabled=true; $("dlg-error").hidden=true;
  api("/api/operator/session",{method:"POST",timeout:12000,body:{reviewer:name},headers:{"x-operator-token":token}}).then(function(reply){
    $("dlg-op-token").value="";
    OP.token=reply.token; OP.reviewer=reply.reviewer; OP.expires=reply.expires_at; opStore(reply.token);
    setRole("admin"); go.disabled=false; dlg.close(); finishChoosing(null);
    renderWho(); location.hash="#/admin";
  },function(error){
    go.disabled=false; $("dlg-error").hidden=false;
    var st=error&&error.status;
    $("dlg-error").textContent=st===401?t("That token is not the operator token."):st===404
      ?t("This deployment has no operator token set, so there is nothing to sign in to. Set CLAUSE_OPERATOR_TOKEN on the server and restart it.")
      :st===429?t("Too many attempts. Wait fifteen minutes."):t("The protocol did not answer.");
  });
});
var ROLE="person";
function getRole(){ try{ return localStorage.getItem("clause-role")||"person"; }catch(e){ return "person"; } }
function setRole(role){
  ROLE=role;
  try{ localStorage.setItem("clause-role",role); }catch(e){}
  var admin=role==="admin";
  if($("dlg-admin-form")){ $("dlg-admin-form").hidden=!admin; $("dlg-privy").hidden=admin||$("dlg-privy").dataset.off==="1"; $("dlg-go").hidden=admin; $("bio").hidden=admin;
    // Signing in as the operator is a state, not a way back: once chosen, the
    // link that chose it stops being on offer and the two pills carry the
    // way back to being a buyer.
    if($("dlg-operator"))$("dlg-operator").hidden=admin; }
  var line=$("dlg-role-note");
  if(line)line.textContent=admin
    ? t("The operator sees everything: every buyer and their policies, every company, every application, and decides what the stand in companies cannot.")
    : role==="company"
    ? t("A company signs in with the account it registered from. It sees its own page and the insurer side, and does not buy cover.")
    : t("Cover is personal: it is held by your address, and only you can open it. Choose how you sign in.");
  if(document.body.getAttribute("data-role")!=="guest"&&identity.token)
    document.body.setAttribute("data-role", role);
  Array.prototype.forEach.call($("dlg-role").querySelectorAll("button"),function(b){
    b.setAttribute("aria-checked",String(b.dataset.role===role));
  });
}
Array.prototype.forEach.call(
  document.querySelectorAll("#dlg-role button, #dlg-operator"),function(b){
    b.addEventListener("click",function(){ setRole(b.dataset.role); });
  });
function home(){ return getRole()==="company" ? "#/company" : getRole()==="admin" ? "#/admin" : "#/mine"; }
dlg.addEventListener("close",function(){
  if(HANDING_OFF){ HANDING_OFF=false; return; }
  finishChoosing(new Error("closed"));
});

/* Who is signed in, in the header, on every page. */
function renderWho(){
  var button=$("who"), text=$("who-text");
  closeWhoMenu();
  var op=getRole()==="admin"&&(OP.token||opRestore());
  document.body.setAttribute("data-role", op ? "admin" : identity.address&&identity.token ? getRole() : "guest");
  if(op){
    button.classList.add("in"); text.removeAttribute("data-i18n");
    text.textContent=t("Operator"); button.setAttribute("aria-label",t("Signed in as the operator"));
    return;
  }
  if(identity.address&&identity.token){
    button.classList.add("in");
    text.removeAttribute("data-i18n");
    text.textContent=short(identity.address);
    button.setAttribute("aria-label",t("Signed in as {address}. Open my cover",{address:short(identity.address)}));
  }else{
    button.classList.remove("in");
    text.textContent=t("Sign in");
    button.setAttribute("aria-label",t("Sign in"));
  }
}
function closeWhoMenu(){
  var menu=$("who-menu"); if(!menu||menu.hidden)return;
  menu.hidden=true; $("who").setAttribute("aria-expanded","false");
}
function openWhoMenu(){
  var menu=$("who-menu");
  var admin=getRole()==="admin";
  $("who-addr").textContent=admin?t("Operator")+(OP.reviewer?" · "+OP.reviewer:""):(identity.address||"");
  $("who-company").hidden=getRole()!=="company";
  $("who-admin").hidden=!admin; $("who-forget").hidden=admin;
  menu.hidden=false; $("who").setAttribute("aria-expanded","true");
  var first=menu.querySelector("a,button"); if(first)first.focus();
}
document.addEventListener("click",function(e){
  var box=e.target.closest&&e.target.closest(".whobox");
  if(!box)closeWhoMenu();
});
document.addEventListener("keydown",function(e){ if(e.key==="Escape")closeWhoMenu(); });
Array.prototype.forEach.call(document.querySelectorAll("#who-menu a"),function(a){
  a.addEventListener("click",closeWhoMenu);
});
function afterSignOut(){
  var route=currentRoute();
  if(route==="/mine")renderMine();
  else if(route==="/company")renderCompany();
  else if(route==="/admin"&&typeof renderAdmin==="function")renderAdmin();
}
$("who-out").addEventListener("click",function(){ signOut(); afterSignOut(); });
$("who-forget").addEventListener("click",function(){ forgetDevice().then(afterSignOut); });
$("who").addEventListener("click",function(){
  if(getRole()==="admin"&&(OP.token||opRestore())){
    if($("who-menu").hidden)openWhoMenu(); else closeWhoMenu();
    return;
  }
  if(identity.address&&identity.token){
    if($("who-menu").hidden)openWhoMenu(); else closeWhoMenu();
    return;
  }
  chooseSignIn("sign-in").then(function(){
    var target=home(); location.hash=target;
    if(currentRoute()==="/mine")renderMine();
    if(currentRoute()==="/company")renderCompany();
  },function(){});
});

/* ---------------- standing instructions ----------------
   A purchase signed now and made later by the protocol itself: when a policy is
   a day from its end (renew), or from a date or an age (buy). The device signs
   the terms; the protocol keeps them and runs them through the same path a
   purchase by hand takes. */
function showLaterBox(){
  var box=$("later-box"); if(!box)return;
  var ok=link.live&&flow.step===CONFIRM_STEP&&PERIL_KEYS[flow.peril]!=="flight_delay"&&!!flow.quoted;
  box.hidden=!ok; if(!ok)return;
  var q=priced();
  if(!$("later-cap").value)$("later-cap").value=Math.ceil(q.premium*1.2);
  if(!$("later-date").value){ var d=new Date(Date.now()+30*86400000); $("later-date").value=d.toISOString().slice(0,10); }
  var size=sizePayload()||{};
  var born=size.built||size.model_year;
  Array.prototype.forEach.call($("later-when").querySelectorAll("button"),function(b){ b.hidden=b.dataset.w==="age"&&!born; });
}
function instructionTerms(body){
  var terms={kind:body.kind,max_premium:Math.round(body.max_premium*100)/100,days:Number(body.days)};
  if(body.kind==="renew"){ terms.policy_id=body.policy_id; return terms; }
  terms.peril=body.peril; terms.subject=body.subject; terms.limit=Number(body.limit); terms.term_days=Number(body.term_days); terms.when=body.when;
  if(body.when==="age")terms.years=Number(body.years); else terms.at=Number(body.at);
  if(body.carrier_id)terms.carrier_id=body.carrier_id;
  if(body.instalments>1)terms.instalments=Number(body.instalments);
  return terms;
}
function giveInstruction(body){
  var terms=instructionTerms(body);
  return signedCall("instruct",terms,"/api/instructions",function(){
    var out={account:identity.address}; for(var k in body)out[k]=body[k]; return out;
  });
}
(function(){
  var when="date";
  function show(){
    Array.prototype.forEach.call($("later-when").querySelectorAll("button"),function(b){ b.setAttribute("aria-checked",String(b.dataset.w===when)); });
    $("later-date-wrap").hidden=when!=="date"; $("later-age-wrap").hidden=when!=="age";
  }
  Array.prototype.forEach.call($("later-when").querySelectorAll("button"),function(b){ b.addEventListener("click",function(){ when=b.dataset.w; show(); }); });
  $("later-go").addEventListener("click",function(){
    var cap=Number($("later-cap").value), go=$("later-go");
    if(!(cap>0)){ $("later-msg").textContent=t("Set the most it may cost."); return; }
    var body={kind:"buy",peril:PERIL_KEYS[flow.peril],subject:subjectPayload(),limit:flow.limit,term_days:PERILS[flow.peril].term,
      max_premium:cap,days:when==="age"?3650:730,when:when,carrier_id:flow.carrier||undefined,instalments:flow.instalments||1,
      settlement:localRuling().asset,
      interest:{what:flow.interest.what,country:flow.interest.country,inside_trigger_area:true,value_at_risk:flow.interest.value,
                size:sizePayload(),address:flow.interest.address||undefined,professional:false},
      attestations:(flow.need?flow.need.claims:[]).map(function(c){return flow.statements[c];}).filter(Boolean)};
    if(when==="age")body.years=Number($("later-years").value);
    else{ var at=Date.parse($("later-date").value+"T00:00:00Z")/1000; if(!(at>0)){ $("later-msg").textContent=t("Pick a date."); return; } body.at=at; }
    go.disabled=true; $("later-msg").textContent=t("Signing…");
    giveInstruction(body).then(function(r){
      go.disabled=false;
      $("later-msg").textContent=t("Done. The instruction stands: {condition}. It is listed on My cover, where you can cancel it.",{condition:conditionText(r.instruction.condition)});
    },function(e){ go.disabled=false; $("later-msg").textContent=refusalText(e); });
  });
})();
function conditionText(c){
  c=c||{};
  if(c.when==="age")return t(c.what==="home"?"when the home (built {born}) reaches {years} years, from {year}":"when the car ({born} model) reaches {years} years, from {year}",{born:c.born,years:c.years,year:c.year});
  if(c.when==="date")return t("from {date}",{date:new Date(c.at*1000).toLocaleDateString(LANG)});
  return t("keep it in force");
}
var INSTRUCTION_STATUS={live:N("standing"),waiting:N("applied, the insurer is deciding"),done:N("done"),cancelled:N("cancelled"),expired:N("expired")};
var ATTEMPT_OUTCOME={bought:N("bought"),applied:N("applied"),declined:N("refused by the insurer"),waiting:N("not this time"),cancelled:N("cancelled"),expired:N("expired")};
function instructionsPanel(i){
  if(!i||!i.instructions||!i.instructions.length)return "";
  var rows=i.instructions.map(function(x){
    var what=x.kind==="renew"?t("Keep {policy} in force",{policy:x.policy_id}):t("Buy {peril} cover, {condition}",{peril:t((MANDATE_PERILS.filter(function(m){return m[0]===x.peril;})[0]||[x.peril,x.peril])[1]),condition:conditionText(x.condition)});
    var last=x.attempts&&x.attempts.length?x.attempts[x.attempts.length-1]:null;
    return '<tr><td>'+esc(what)+'<br><span class="fine">'+esc(t("up to {cap} per purchase",{cap:money(x.max_premium)}))+(x.bought.length?' · '+esc(t("bought: {list}",{list:x.bought.join(", ")}))+'':'')+'</span></td>'+
      '<td>'+esc(t(INSTRUCTION_STATUS[x.status]||x.status))+(last&&last.note?'<br><span class="fine">'+esc(ts(last.note))+'</span>':'')+
      (x.next_at&&x.status==="live"&&x.next_at>Date.now()/1000?'<br><span class="fine">'+esc(t("next try {date}",{date:new Date(x.next_at*1000).toLocaleDateString(LANG)}))+'</span>':'')+'</td>'+
      '<td>'+((x.status==="live"||x.status==="waiting")?'<button class="btn btn-ghost btn-sm" type="button" data-ins-cancel="'+esc(x.instruction_id)+'">'+esc(t("Cancel"))+'</button>':'')+'</td></tr>';
  }).join("");
  return '<details class="more" id="instructions-box" open><summary>'+esc(t("Standing instructions"))+': <b>'+esc(t("{n} given",{n:i.instructions.length}))+'</b></summary><div class="inner">'+
    '<p class="fine">'+esc(t("Each one is a purchase you signed in advance. The protocol makes it when its moment comes, at the price then, never above the cap; a home or a car is still applied for and the insurer still decides. Every attempt is written here."))+'</p>'+
    '<div class="table-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways" data-i18n-aria><table class="ttable"><thead><tr><th>'+esc(t("Instruction"))+'</th><th>'+esc(t("Status"))+'</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
    '<p class="fine" id="ins-msg" role="status"></p></div></details>';
}
function bindInstructionsPanel(){
  Array.prototype.forEach.call(document.querySelectorAll("[data-ins-cancel]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true;
      api("/api/instructions/"+encodeURIComponent(b.dataset.insCancel)+"/cancel",{method:"POST",token:identity.token})
        .then(function(){ renderMineExtras(); },function(e){ b.disabled=false; $("ins-msg").textContent=refusalText(e); });
    });
  });
}
function autoRenewHtml(policy){
  if(policy.status!=="active"||policy.peril==="flight_delay"||!policy.ends_at)return "";
  return '<span class="renew-slot" data-autorenew-for="'+esc(policy.policy_id)+'" data-premium="'+policy.premium+'"></span>';
}
function bindAutoRenew(root,instructions){
  Array.prototype.forEach.call(root.querySelectorAll("[data-autorenew-for]"),function(slot){
    var id=slot.dataset.autorenewFor, premium=Number(slot.dataset.premium);
    var have=(instructions||[]).filter(function(x){return x.kind==="renew"&&x.policy_id===id&&(x.status==="live"||x.status==="waiting");})[0];
    if(have){ slot.innerHTML='<span class="pill">'+esc(t("Renews itself, up to {cap}",{cap:money(have.max_premium)}))+'</span>'; return; }
    slot.innerHTML='<button class="btn btn-ghost btn-sm" type="button" data-autorenew="'+esc(id)+'">'+esc(t("Renew automatically"))+'</button>';
    slot.querySelector("button").addEventListener("click",function(){
      slot.innerHTML='<span class="tform" style="align-items:center"><label><span>'+esc(t("Most it may cost"))+'</span><input type="number" min="1" step="1" value="'+Math.ceil(premium*1.2)+'" style="max-width:120px" data-cap></label>'+
        '<button class="btn btn-primary btn-sm" type="button" data-go>'+esc(t("Sign the instruction"))+'</button><span class="fine" data-msg>'+esc(t("A day before this cover ends, the same cover is applied for again for another term, at the price then, if it is at or under this cap."))+'</span></span>';
      slot.querySelector("[data-go]").addEventListener("click",function(){
        var go=this, cap=Number(slot.querySelector("[data-cap]").value);
        if(!(cap>0))return;
        go.disabled=true; slot.querySelector("[data-msg]").textContent=t("Signing…");
        giveInstruction({kind:"renew",policy_id:id,max_premium:cap,days:3650}).then(function(){ renderMine(); },
          function(e){ go.disabled=false; slot.querySelector("[data-msg]").textContent=refusalText(e); });
      });
    });
  });
}

function startPurchase(){
  if(flow.busy)return;
  var ruling=localRuling();
  if(!ruling.allowed){renderVerdict();return;}
  if(!link.live){demoDone();return;}
  if(identity.token){completePurchase();return;}
  chooseSignIn("buy").then(completePurchase,function(){});
}

function completePurchase(){
  if(flow.busy)return;
  var ruling=localRuling();
  if(!ruling.allowed){renderVerdict();return;}
  if(!link.live){demoDone();return;}

  // Signed in already, or signing in now. It used to sign in unconditionally,
  // which meant the device door registered, challenged and verified twice for
  // one purchase: three round trips added to the most fragile moment in the
  // flow, on the slow line where they are most likely to be the one that fails.
  setBusy(identity.token?t("Signing the terms…"):t("Signing in…"));
  var terms=null;
  (identity.token?Promise.resolve():signIn()).then(function(){
    setBusy(t("Signing the terms…"));
    terms={peril:PERIL_KEYS[flow.peril], limit:flow.limit,
           term_days:PERILS[flow.peril].term, subject:subjectPayload(),
           country:flow.interest.country, value_at_risk:flow.interest.value,
           size:sizePayload()};
    if(flow.carrier)terms.carrier_id=flow.carrier;
    if(CONTRACT.hash)terms.contract_hash=CONTRACT.hash;
    if(flow.instalments>1)terms.instalments=flow.instalments;
    // The same patience as the application it opens. At the default twelve
    // seconds a slow moment here failed the purchase before it had begun, and
    // an abort carries no reply, so what the buyer read was the banner about
    // not knowing whether they had been charged -- for a request that had not
    // been made yet.
    return api("/api/auth/challenge",{method:"POST",timeout:40000,
      body:{address:identity.address, purpose:"buy", terms:terms}});
  }).then(function(challenge){
    return sign(challenge.message).then(function(signature){
      setBusy(t("Sending the application…"));
      var application={
        peril:terms.peril, subject:terms.subject, limit:terms.limit,
        term_days:terms.term_days, holder:identity.address,
        nonce:challenge.nonce, signature:signature, settlement:ruling.asset,
        // The statements this device is holding. The protocol checks the
        // signatures, learns one bit per claim, and stores none of them.
        attestations:(flow.need?flow.need.claims:[]).map(function(claim){
          return flow.statements[claim];
        }).filter(Boolean),
        // The figure on the screen when the buyer pressed the button. The pool
        // prices again at bind time against a book that has moved since; if it
        // has moved past this, the policy is refused rather than written at a
        // price nobody was shown.
        max_premium:Math.ceil(priced().premium*100)/100,
        // Unless the price is still inside the ten minutes it was promised for,
        // in which case that is the price whatever the book has done.
        quote_id:(flow.quoted&&flow.quoted.lock)?flow.quoted.lock.id:undefined,
        carrier_id:flow.carrier||undefined,
        contract_hash:CONTRACT.hash||undefined,
        instalments:flow.instalments||1,
        interest:{what:flow.interest.what, country:flow.interest.country,
                  inside_trigger_area:true, value_at_risk:flow.interest.value, size:terms.size,
                  address:flow.interest.address||undefined, professional:false},
      };
      // Asked, and asked once more if nothing came back.
      //
      // A POST that failed may have been received and acted on, so sending a
      // different one is how somebody is charged twice -- but this is not a
      // different one. The challenge it is signed over is single use, so the
      // protocol recognises the same purchase arriving again and answers with
      // the application it already wrote, or the refusal it already gave,
      // without writing anything. That is what makes the second ask safe, and
      // it is the difference between a buyer whose line stuttered getting their
      // cover and getting a banner telling them to go and look for it.
      //
      // Only ever twice, and only when the failure carried no answer at all: a
      // refusal is an answer and is shown as one.
      return api("/api/applications",{method:"POST",timeout:40000,body:application})
        .catch(function(error){
          if(!(error&&error.unanswered))throw error;
          setBusy(t("Still sending. Asking again…"));
          return api("/api/applications",{method:"POST",timeout:40000,body:application});
        });
    });
  }).then(function(reply){
    setBusy(null);
    if(reply.session)setSession(reply.session.token);
    if(reply.application) showApplied(reply); else showDone(reply);
  }).catch(function(error){
    setBusy(null);
    showBuyError(error);
  });
}

function showBuyError(error){
  var payload=error&&error.payload,html;
  // The protocol's own sentences, translated where a translation exists and
  // with the English they came from underneath, because a refusal is the
  // protocol's decision and its English is the binding text.
  // Whether we can promise the money did not move. A refusal is the
  // protocol's own decision, taken before anything was taken, so there it can
  // be promised. A request that never came back cannot be: it may have been
  // read, and the policy may exist. Saying "nothing was charged" to somebody
  // who was charged is the one thing this banner must never do.
  var refused=false;
  // Still being decided. The first ask was lost on its way out rather than on
  // its way back, so the protocol is deciding it now: not a refusal, and the
  // one thing this must not say is that nothing was charged.
  if(payload&&payload.detail&&payload.detail.deciding){
    html=esc(t("This purchase is still being decided. Nothing was sent twice. Look at My cover in a moment: if the cover is there it went through, and if it is not, nothing was taken."));
  }
  else if(payload&&payload.detail&&payload.detail.reasons){
    html=payload.detail.reasons.map(tsHtml).join(" "); refused=true;
  }
  else if(payload&&payload.reasons){ html=payload.reasons.map(tsHtml).join(" "); refused=true; }
  else if(payload&&typeof payload.detail==="string")html=tsHtml(payload.detail);
  else if(payload&&Array.isArray(payload.detail)&&payload.detail.length){
    html=esc(t("The protocol could not read what the page sent:")+" "+malformedText(payload.detail)); refused=true;
  }
  // Being replaced is not a refusal. The proxy answers a restart with a 503
  // that carries this word, and without naming it here that reply would have
  // fallen through to "nothing was charged" -- which is the one thing this
  // banner must never say to somebody who was charged, because the request
  // may have been read before the old process went away.
  else if(payload&&payload.error==="restarting")
    html=esc(t("The protocol is being replaced and will answer in a moment. Check My cover before trying again: if the policy is there it was bought, and if it is not, nothing was taken."));
  else if(!payload)html=esc(t("The protocol could not be reached, or answered with something the page could not read. Check My cover before trying again: if the policy is there it was bought, and if it is not, nothing was taken."));
  else html=esc(t("The protocol did not accept this. Nothing was charged."));
  // The technical cause, small and last. It is not for the buyer to
  // understand; it is so that the answer to "it does not work" is one line
  // instead of a week.
  // Always something, because a banner with no reason under it is what a
  // buyer sends a screenshot of, and the screenshot is then all anybody has.
  // Errors raised outside api() carry no kind of their own, so their own name
  // stands in rather than nothing at all.
  var why=(error&&error.kind)||(error&&(error.name||error.message))||"";
  if(why)
    html+='<span class="fine" style="display:block;margin-top:8px;opacity:.8">'+
      esc(t("Reason: {kind}",{kind:String(why).slice(0,120)}))+'</span>';
  var box=$("compliance-box");
  box.hidden=false; box.className="verdict no";
  // Two answers mean "we do not know yet", and both must read that way: being
  // replaced, and being decided. Only a refusal may promise the money stayed.
  var unsure=!!(payload&&(payload.error==="restarting"||(payload.detail&&payload.detail.deciding)));
  box.innerHTML='<div class="vrow"><span class="pill no">'+esc(unsure?t("Not sure"):t("Not written"))+'</span>'+
    '<span>'+esc(t(refused&&!unsure?"nothing was charged":"check My cover"))+'</span></div><p>'+html+'</p>';
  box.scrollIntoView({behavior:"smooth",block:"center"});
}

var LAST_DONE=null;

