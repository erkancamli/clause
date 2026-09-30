
/* ================= what stays when the desks are deferred ================= */
/* A company's desk, an operator's screens and the proof register are 193,502
   bytes of script that a buyer never enters: measured over a whole purchase,
   from the home page to the signing step, a buyer touches 9 per cent of the
   company and operator code, 14 per cent of proof and chain, 5 per cent of the
   profile. They are the three surfaces worth fetching only when somebody opens
   them.

   Sixteen declarations were written inside those three and used outside them,
   which is what stopped them being separable: the cover flow reads the buyer's
   saved things, My cover draws its payout, mandate and funding panels, signing
   out clears the operator's session, and two helpers are simply general. They
   are here now, on the side of the line that is always in the page, and
   nothing about what they do has changed. */
var ASSETS={list:[],at:0};
function loadAssets(force){
  if(!identity.token)return Promise.resolve([]);
  if(!force&&ASSETS.list.length&&Date.now()-ASSETS.at<60000)return Promise.resolve(ASSETS.list);
  return api("/api/assets",{token:identity.token}).then(function(r){ ASSETS.list=r.assets||[]; ASSETS.at=Date.now(); return ASSETS.list; },function(){ return ASSETS.list; });
}
function renderAssetChips(){
  var slot=$("asset-chips"); if(!slot)return;
  slot.innerHTML=assetChipsHtml();
  Array.prototype.forEach.call(slot.querySelectorAll("[data-use-asset]"),function(b){
    b.addEventListener("click",function(){ var a=ASSETS.list.filter(function(x){return x.asset_id===b.dataset.useAsset;})[0]; if(a)useAsset(a); });
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
function downloadCsv(path, opts, filename){
  var o={raw:true,timeout:30000}; for(var k in opts)o[k]=opts[k];
  return api(path,o).then(function(blob){
    var url=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=url; a.download=filename; document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(url); a.remove(); },1000);
  });
}
function opStore(value){
  try { value ? sessionStorage.setItem("clause.op", value)
              : sessionStorage.removeItem("clause.op"); } catch(e){}
}
function opRestore(){
  try { return sessionStorage.getItem("clause.op"); } catch(e){ return null; }
}
function opSignOut(){
  var token=OP.token;
  OP.token=null; OP.reviewer=""; OP.expires=0; opStore(null);
  $("op-work").hidden=true; $("op-work").innerHTML="";
  $("op-signin").hidden=false;
  if(token) api("/api/operator/session",{method:"DELETE",token:token,timeout:8000})
    .then(function(){},function(){});
}
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
function bindTokens(root){
  Array.prototype.forEach.call(root.querySelectorAll("[data-token]"),function(b){
    b.addEventListener("click",function(){ showToken(b.dataset.token); });
  });
}
var FEE_KINDS={fronting_fee:N("fronting fee received"),fronting_fee_returned:N("fronting fee returned"),platform_fee:N("platform fee"),platform_fee_returned:N("platform fee returned")};
var FUNDING_NAMES={bank:N("Bank transfer"),rialo:N("From a Rialo wallet"),solana:N("From a Solana wallet"),evm:N("From an Ethereum wallet")};
var FUNDING_STATUS={waiting:N("waiting for the transfer to arrive"),received:N("received and credited"),cancelled:N("cancelled"),expired:N("expired, nothing arrived in 30 days")};
var ORDER_KIND={payout:N("payout"),refund:N("refund"),withdrawal:N("withdrawal")};
var PAYOUT_STATUS={queued:N("waiting to be sent"),sent:N("sent"),paid:N("paid"),failed:N("failed, returned to your address")};
function assetChipsHtml(){
  var kind=(flow.peril==="quake"||flow.peril==="storm")?"home":flow.peril==="car"?"vehicle":flow.peril==="drought"?"field":null;
  if(!kind||!identity.token)return "";
  var mine=ASSETS.list.filter(function(a){return a.kind===kind;});
  if(!mine.length)return "";
  return '<div class="label" style="margin:0 0 6px">'+esc(t("From my profile"))+'</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'+mine.map(function(a){
    return '<button class="btn btn-line btn-sm" type="button" data-use-asset="'+esc(a.asset_id)+'" aria-pressed="'+(flow.asset===a.asset_id)+'">'+esc(a.label)+' <span class="fine">'+esc(assetSummary(a))+'</span></button>';
  }).join("")+'</div>';
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
function monthLabel(m){
  var p=String(m||"").split("-"); if(p.length<2)return m||"";
  return new Date(Date.UTC(+p[0],+p[1]-1,1)).toLocaleDateString(LOCALES[LANG]||"en-US",{year:"numeric",month:"long",timeZone:"UTC"});
}
function opStamp(seconds){
  if(!seconds) return "";
  return new Date(seconds*1000).toISOString().slice(0,16).replace("T"," ")+" UTC";
}
function showToken(id){
  api("/api/policies/"+encodeURIComponent(id)+"/token",{timeout:9000}).then(function(meta){
    $("token-img").src=meta.image;
    $("token-img").alt=meta.name;
    $("token-meta").textContent=t("Minted in block {n}",{n:f0.format(meta.token.minted_block)})+" · "+meta.token.terms_hash;
    $("token-chain").textContent=""; $("token-claim").innerHTML="";
    api("/api/policies/"+encodeURIComponent(id)+"/anchor",{timeout:9000,token:identity.token||undefined}).then(function(a){
      var last=(a.intents||[]).slice(-1)[0];
      $("token-chain").textContent=last?t("On {chain}: {state}",{chain:(a.chain||{}).name||"",state:t(ANCHOR_KINDS[last.kind]||last.kind)+", "+anchorState(last.status)}):t("Not on a public chain yet.");
      renderTokenClaim(id,a);
    },function(){});
    var d=$("token-dlg");
    if(typeof d.showModal==="function"){ if(!d.open)d.showModal(); } else d.setAttribute("open","");
  },function(){});
}
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
var ANCHOR_KINDS={mint:N("token mint"),burn:N("token burn"),settle:N("settlement record"),root:N("book root")};
function anchorState(st){ return {pending:t("waiting to be sent"),sent:t("sent"),confirmed:t("confirmed"),failed:t("failed")}[st]||st; }
function assetSummary(a){
  var z=a.size||{};
  if(a.kind==="home")return t("{building}, {area} m², built {built}",{building:t(BUILDING_WORDS[z.building]||z.building),area:f0.format(z.area_m2),built:z.built});
  if(a.kind==="vehicle")return [z.make,z.model,z.plate].filter(Boolean).join(" ")+(z.model_year?" · "+t("{year} model",{year:z.model_year}):"");
  return t("{area} ha of {crop}",{area:f1.format(z.area_ha),crop:t(CROP_WORDS[z.crop]||z.crop)});
}
function renderTokenClaim(id,a){
  var box=$("token-claim"); if(!box)return;
  if(!a.wallets||a.mode!=="live"||!a.held)return;   // not the holder, or nothing on the chain yet
  var held=a.held, mine=a.wallets;
  var where=held.custodial?t("Held for you by the protocol's signer."):t("In your wallet {address}.",{address:anchorShort(held.to)});
  var h='<p class="fine">'+esc(where)+'</p>';
  var target=mine.length?mine[0]:null;
  if(target&&(held.to||"").toLowerCase()!==target.toLowerCase()){
    h+='<div><button class="btn btn-ghost btn-sm" type="button" id="token-claim-go">'+esc(t("Mint it to my wallet {address}",{address:anchorShort(target)}))+'</button> <span class="fine" id="token-claim-out"></span></div>';
    if(held.status!=="pending")h+='<p class="fine">'+esc(t("The token cannot be transferred, so this burns the one the signer holds and mints a new one to your wallet, in that order."))+'</p>';
  } else if(!target){
    h+='<p class="fine">'+esc(t("Want it in your own wallet? Link an Ethereum wallet on your profile; the token is then minted to it."))+' <a href="#/profile">'+esc(t("My profile"))+'</a></p>';
  }
  box.innerHTML=h;
  var go=$("token-claim-go");
  if(go)go.addEventListener("click",function(){
    go.disabled=true; $("token-claim-out").textContent="…";
    api("/api/policies/"+encodeURIComponent(id)+"/anchor/claim",{method:"POST",token:identity.token,body:{address:target}}).then(function(r){
      $("token-claim-out").textContent=t("Queued: {n} transaction(s), sent on the next cycle.",{n:(r.queued||[]).length});
    },function(error){
      go.disabled=false;
      $("token-claim-out").textContent=(error&&error.payload&&error.payload.detail)||t("The protocol did not answer.");
    });
  });
}
function anchorShort(h){ return h?h.slice(0,10)+"…"+h.slice(-6):""; }
