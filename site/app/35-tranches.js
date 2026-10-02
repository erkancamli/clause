/* ================= the pool's tranches ================= */
var TRANCHE_NAME={senior:N("Senior"),mezzanine:N("Mezzanine"),first_loss:N("First loss")};
function signedCall(purpose, terms, path, extra){
  var ready=identity.token?Promise.resolve():chooseSignIn("sign-in");
  return ready.then(function(){
    return api("/api/auth/challenge",{method:"POST",body:{address:identity.address,purpose:purpose,terms:terms}});
  }).then(function(challenge){
    return sign(challenge.message).then(function(signature){
      // Built after signing in, so it can name the address signed in as.
      var fields=typeof extra==="function"?extra():(extra||{});
      var body={}; var k;
      for(k in fields)body[k]=fields[k];
      body.nonce=challenge.nonce; body.signature=signature;
      // A purchase prices, writes the contract and is on disk before it is
      // answered; on a busy protocol that is longer than a read. Ninety
      // seconds before the page gives up, and it says so meanwhile.
      return api(path,{method:"POST",body:body,timeout:90000});
    });
  });
}
/* A body the protocol could not read comes back as a list of fields; said
   as "field: what is wrong", so the fault can be named rather than guessed. */
function malformedText(d){
  return d.map(function(e){ return (Array.isArray(e.loc)?e.loc.filter(function(x){return x!=="body";}).join("."):"")+": "+String(e.msg||""); }).join("; ");
}
function refusalText(error, fallback){
  var d=error&&error.payload&&error.payload.detail;
  if(d&&d.reasons)return d.reasons.map(ts).join(" ");
  if(typeof d==="string")return ts(d);
  if(Array.isArray(d)&&d.length)return t("The protocol could not read what the page sent:")+" "+malformedText(d);
  if(error&&!error.payload)return t("The protocol could not be reached, or answered with an error the page could not read. Nothing was charged.");
  return t(fallback||"The protocol refused that.");
}
function renderTranches(){
  if(!link.live){ $("tranche-sec").hidden=true; return; }
  $("tranche-sec").hidden=false;
  /* With the session, because "Your capital" below is found by matching the
     reader's own address in the provider list, and the protocol now gives
     that address on their row only. Without it every row comes back with a
     null account and the page would say they hold nothing. */
  Promise.all([api("/api/pool/risk",{timeout:20000}),
               api("/api/pool",{token:identity.token})]).then(function(both){
    var risk=both[0], pool=both[1], rows=risk.tranches||[];
    // A protocol from before tranches has none to show.
    if(!rows.length){ $("tranche-sec").hidden=true; return; }
    var total=rows.reduce(function(a,r){return a+r.balance;},0)||1;
    $("r-capital").textContent=f0.format(pool.balance);
    // Drawn bottom up, the order a loss eats them.
    $("tstack").innerHTML=rows.slice().reverse().map(function(r){
      return '<span class="t-'+esc(r.name)+'" style="width:'+(100*r.balance/total).toFixed(2)+'%"></span>';
    }).join("");
    $("tbody").innerHTML=rows.map(function(r){
      var ret=r.expected_return===null?"–":f1.format(r.expected_return*100)+"%";
      return '<tr><td><span class="tdot t-'+esc(r.name)+'"></span>'+esc(t(TRANCHE_NAME[r.name]||r.name))+'</td>'+
        '<td class="num">'+f0.format(r.balance)+'</td>'+
        '<td class="num">'+f0.format(r.attaches_at)+' → '+f0.format(r.exhausted_at)+'</td>'+
        '<td class="num">'+f1.format(r.probability_of_loss*100)+'%</td>'+
        '<td class="num">'+f0.format(r.expected_loss)+'</td>'+
        '<td class="num">×'+f1.format(r.yield_weight)+'</td>'+
        '<td class="num">'+ret+'</td></tr>';
    }).join("");
    $("tnote").textContent=t("Chances and expected losses come from the same simulated years that price the book, and move with it. Expected return is a year's premium share less the expected loss, over the capital; it is a model's figure, not a promise.");
    var mine=(pool.providers||[]).filter(function(p){return identity.token&&p.account===identity.address&&p.shares>0;});
    $("t-mine").innerHTML=mine.length?('<div class="label" style="margin-bottom:6px">'+esc(t("Your capital"))+'</div>'+
      mine.map(function(p){
        var row=rows.filter(function(r){return r.name===p.tranche;})[0]||{share_price:1};
        return '<div class="tform" style="align-items:center;margin-bottom:6px"><span><span class="tdot t-'+esc(p.tranche)+'"></span>'+
          esc(t(TRANCHE_NAME[p.tranche]||p.tranche))+': '+f0.format(p.shares*row.share_price)+'</span>'+
          '<button class="btn btn-line btn-sm" type="button" data-withdraw="'+esc(p.tranche)+'" data-shares="'+p.shares+'">'+esc(t("Withdraw"))+'</button></div>';
      }).join("")):"";
    Array.prototype.forEach.call($("t-mine").querySelectorAll("[data-withdraw]"),function(b){
      b.addEventListener("click",function(){
        var tranche=b.dataset.withdraw, shares=Number(b.dataset.shares);
        b.disabled=true; $("t-msg").textContent=t("Signing…");
        signedCall("withdraw",{shares:shares,tranche:tranche},"/api/pool/withdraw",
          function(){return {account:identity.address,shares:shares,tranche:tranche};}).then(function(r){
          $("t-msg").textContent=t("{amount} returned to your address.",{amount:f0.format(r.amount)});
          renderTranches(); renderWho();
        },function(e){ b.disabled=false; $("t-msg").textContent=refusalText(e); });
      });
    });
  },function(){
    $("tbody").innerHTML='<tr><td colspan="7" class="fine">'+esc(t("The protocol did not answer."))+'</td></tr>';
  });
}
$("t-go").addEventListener("click",function(){
  var amount=Number($("t-amount").value), tranche=$("t-tranche").value, go=$("t-go");
  if(!(amount>=100)){ $("t-msg").textContent=t("Enter at least 100."); return; }
  go.disabled=true; $("t-msg").textContent=t("Signing…");
  signedCall("deposit",{amount:amount,tranche:tranche},"/api/pool/deposit",
    function(){return {account:identity.address,amount:amount,tranche:tranche};}).then(function(r){
    go.disabled=false;
    $("t-msg").textContent=t("Deposited. You hold {shares} shares of the {tranche} tranche.",
      {shares:f1.format(r.shares),tranche:t(TRANCHE_NAME[tranche])});
    renderTranches();
  },function(e){ go.disabled=false; $("t-msg").textContent=refusalText(e); });
});


