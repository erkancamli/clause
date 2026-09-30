/* ================= payouts, Rider's permission, cooling off ================= */
var PAYOUT_NAMES={wallet:N("To my address"),bank:N("To a bank account"),mobile_money:N("To a mobile wallet"),rialo:N("To my Rialo wallet"),solana:N("To a Solana wallet"),evm:N("To an Ethereum wallet")};
var CHAIN_WALLETS={rialo:{hint:N("Your Rialo public key, for example the custodial keypair on playground.rialo.io under Account."),ph:N("Hddr…pCJV (44 characters)"),connect:null},
  solana:{hint:N("USDC on Solana. Connect Phantom or another Solana wallet to fill the address, or paste it."),ph:N("base58, 32 to 44 characters"),connect:"solana"},
  evm:{hint:N("USDC on the chain the operator's rail pays on. Connect MetaMask or another Ethereum wallet to fill the address, or paste it."),ph:"0x…",connect:"evm"}};
function connectChainWallet(kind){
  if(kind==="evm"){
    if(!window.ethereum)return Promise.reject(new Error(t("No Ethereum wallet found in this browser.")));
    return window.ethereum.request({method:"eth_requestAccounts"}).then(function(a){ return a[0]; });
  }
  var sol=window.solana||(window.phantom&&window.phantom.solana);
  if(!sol)return Promise.reject(new Error(t("No Solana wallet found in this browser.")));
  return sol.connect().then(function(r){ return (r&&r.publicKey?r.publicKey:sol.publicKey).toString(); });
}
var MANDATE_KEY="clause-mandate";
function mandateToken(){
  try{ var m=JSON.parse(localStorage.getItem(MANDATE_KEY)||"null");
       return m&&m.address===identity.address?m.token:null; }catch(e){ return null; }
}
function keepMandate(token){
  try{ if(token)localStorage.setItem(MANDATE_KEY,JSON.stringify({address:identity.address,token:token}));
       else localStorage.removeItem(MANDATE_KEY); }catch(e){}
}
/* Every open policy can be asked "can I cancel this, and what comes back?";
   the answer is the protocol's, from the buyer's law and the peril. */
function cancelHtml(policy){
  var m=policy.metadata||{};
  if(policy.status!=="active")return "";
  return (m.bought_by==="rider"?'<span class="pill">'+esc(t("Bought by Rider"))+'</span>':'')+
    '<span class="cancel-slot" data-cancel-for="'+esc(policy.policy_id)+'"></span>'+
    ' <button class="btn btn-ghost btn-sm" type="button" data-contract-copy="'+esc(policy.policy_id)+'">'+esc(t("Your copy of the contract"))+'</button>';
}
/* ---------------- complaints ----------------
   A complaint is a thread on the policy with the company's clock on it. The
   page shows the clock, lets the holder write, and when the clock has run
   out or the answer has come, hands over the file the ombudsman's form asks
   for: the policy, its readings and settlements, the thread, the links. */
/* What went wrong, said the way somebody would say it. These used to be a
   label, a colon and a fragment — "The company: how it dealt with me" is not
   a sentence in English either, which is why every translation of it came out
   broken. A complaint form offers statements, not headings. */
var COMPLAINT_SUBJECTS={settlement:N("It paid nothing, or it paid the wrong amount"),
  payment:N("The payment was decided, but the money has not arrived"),
  cover:N("The cover is not what I was sold"),service:N("How the company treated me"),
  other:N("Something else")};
var COMPLAINT_STATUS={open:N("waiting for the company"),answered:N("answered by the company"),closed:N("closed"),escalated:N("taken to the ombudsman")};
var WHO={holder:N("You"),company:N("The company"),operator:N("The operator")};
function complaintWhen(x){ return new Date(x*1000).toLocaleString(LOCALES[LANG]||"en-US"); }
function complaintThread(c){
  return '<div style="display:grid;gap:6px">'+(c.messages||[]).map(function(m){
    return '<div class="fine"><b>'+esc(t(WHO[m.who]||m.who))+'</b> · '+esc(complaintWhen(m.at))+'<br>'+esc(m.text)+'</div>'; }).join("")+'</div>';
}
function complaintHtml(c){
  var route=c.route||{};
  var clock=c.status==="open"?(c.overdue?t("The company's {days} days to answer have run out.",{days:route.answer_days})
    :t("The company has {n} days left to answer, until {when}.",{n:Math.max(0,Math.ceil(c.days_left)),when:complaintWhen(c.deadline_at)})):"";
  var h='<div class="verdict" style="margin-top:10px"><p><b>'+esc(t("Complaint {id}",{id:c.complaint_id}))+'</b> · '+esc(t(COMPLAINT_SUBJECTS[c.subject]||c.subject))+' · '+esc(t(COMPLAINT_STATUS[c.status]||c.status))+'</p>'+
    (clock?'<p class="fine">'+esc(clock)+'</p>':'')+complaintThread(c);
  if(c.status!=="closed"){
    h+='<div style="margin-top:8px;display:grid;gap:6px"><textarea class="dlg-input" rows="2" data-complaint-text="'+esc(c.complaint_id)+'" placeholder="'+esc(t("Write to the company"))+'"></textarea>'+
      '<div><button class="btn btn-line btn-sm" type="button" data-complaint-send="'+esc(c.complaint_id)+'">'+esc(t("Send"))+'</button> '+
      (c.can_escalate&&c.status!=="escalated"?'<button class="btn btn-primary btn-sm" type="button" data-complaint-escalate="'+esc(c.complaint_id)+'">'+esc(t("Take it to {body}",{body:route.body||""}))+'</button> ':'')+
      '<button class="btn btn-ghost btn-sm" type="button" data-complaint-file="'+esc(c.complaint_id)+'">'+esc(t("Download the file"))+'</button> <span class="fine" data-complaint-out="'+esc(c.complaint_id)+'"></span></div></div>';
  }
  if(c.status==="escalated"||c.can_escalate){
    h+='<p class="fine" style="margin-top:8px">'+esc(ts(route.note||""))+'</p><p class="fine">'+(route.links||[]).map(function(l){
      return '<a href="'+esc(l.url)+'" target="_blank" rel="noreferrer noopener">'+esc(l.name)+'</a>'; }).join(" · ")+'</p>';
  }
  return h+'</div>';
}
function complaintFormHtml(id){
  return '<details class="more" style="margin-top:10px"><summary>'+esc(t("Something wrong? Raise a complaint"))+'</summary><div class="inner" style="display:grid;gap:8px">'+
    '<p class="fine">'+esc(t("It goes to the company that issued the policy, on the record, with its time to answer counted from now. If it does not answer in time, or the answer does not settle it, the ombudsman's file is one click away."))+'</p>'+
    '<select class="dlg-input" data-complaint-subject="'+esc(id)+'">'+Object.keys(COMPLAINT_SUBJECTS).map(function(k){ return '<option value="'+k+'">'+esc(t(COMPLAINT_SUBJECTS[k]))+'</option>'; }).join("")+'</select>'+
    '<textarea class="dlg-input" rows="3" data-complaint-new="'+esc(id)+'" placeholder="'+esc(t("What happened, in your own words"))+'"></textarea>'+
    '<div><button class="btn btn-line btn-sm" type="button" data-complaint-open="'+esc(id)+'">'+esc(t("Send the complaint"))+'</button> <span class="fine" data-complaint-out="new-'+esc(id)+'"></span></div></div></details>';
}
function downloadText(path,filename){
  return fetch(API+path,{headers:{authorization:"Bearer "+identity.token}}).then(function(r){ if(!r.ok)throw new Error("refused"); return r.text(); }).then(function(text){
    var blob=new Blob([text],{type:"text/plain"}), url=URL.createObjectURL(blob), link=document.createElement("a");
    link.href=url; link.download=filename; document.body.appendChild(link); link.click(); link.remove(); setTimeout(function(){URL.revokeObjectURL(url);},60000);
  });
}
function bindComplaints(root){
  var slots=root.querySelectorAll("[data-complaint-for]"); if(!slots.length||!identity.token)return;
  api("/api/complaints",{token:identity.token}).then(function(r){
    var byPolicy={}; (r.complaints||[]).forEach(function(c){ if(!byPolicy[c.policy_id]||c.status!=="closed")byPolicy[c.policy_id]=c; });
    Array.prototype.forEach.call(slots,function(slot){ var id=slot.dataset.complaintFor, c=byPolicy[id]; slot.innerHTML=c?complaintHtml(c):complaintFormHtml(id); });
    bindComplaintActions(root);
  },function(){});
}
function bindComplaintActions(root){
  function out(key,text){ var el=root.querySelector('[data-complaint-out="'+key+'"]'); if(el)el.textContent=text; }
  Array.prototype.forEach.call(root.querySelectorAll("[data-complaint-open]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.complaintOpen, text=root.querySelector('[data-complaint-new="'+id+'"]').value, subject=root.querySelector('[data-complaint-subject="'+id+'"]').value;
      b.disabled=true;
      api("/api/policies/"+encodeURIComponent(id)+"/complaints",{method:"POST",token:identity.token,body:{subject:subject,text:text}}).then(function(){ renderMine(); },function(e){ b.disabled=false; out("new-"+id,refusalText(e)); });
    });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-complaint-send]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.complaintSend, text=root.querySelector('[data-complaint-text="'+id+'"]').value; b.disabled=true;
      api("/api/complaints/"+encodeURIComponent(id)+"/messages",{method:"POST",token:identity.token,body:{text:text}}).then(function(){ renderMine(); },function(e){ b.disabled=false; out(id,refusalText(e)); });
    });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-complaint-escalate]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.complaintEscalate; b.disabled=true;
      api("/api/complaints/"+encodeURIComponent(id)+"/escalate",{method:"POST",token:identity.token,body:{}}).then(function(){
        downloadText("/api/complaints/"+encodeURIComponent(id)+"/package?format=text",id+".txt").then(renderMine,renderMine);
      },function(e){ b.disabled=false; out(id,refusalText(e)); });
    });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-complaint-file]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.complaintFile; b.disabled=true;
      downloadText("/api/complaints/"+encodeURIComponent(id)+"/package?format=text",id+".txt").then(function(){ b.disabled=false; },function(e){ b.disabled=false; out(id,refusalText(e)); });
    });
  });
}
/* The three bordereaux for a month, and the reconciliation in one line. */
function bindBordereaux(root, auth){
  Array.prototype.forEach.call(root.querySelectorAll("[data-bordereaux-for]"),function(holder){
    var id=holder.dataset.bordereauxFor;
    function load(month){
      var o={timeout:20000}; for(var k in auth)o[k]=auth[k];
      api("/api/company/bordereaux?carrier_id="+encodeURIComponent(id)+"&kind=reconciliation"+(month?"&month="+encodeURIComponent(month):""),o).then(function(r){
        var b=r.bordereau, items={}; (b.items||[]).forEach(function(i){ items[i.item]=i.amount; });
        var months=r.months||[]; if(months.indexOf(b.month)<0)months.unshift(b.month);
        holder.innerHTML='<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px">'+
          '<select class="dlg-input" style="width:auto" data-bx-month>'+months.map(function(m){ return '<option value="'+esc(m)+'"'+(m===b.month?' selected':'')+'>'+esc(m)+'</option>'; }).join("")+'</select>'+
          ['risk','claims','reconciliation'].map(function(k){ return '<button class="btn btn-line btn-sm" type="button" data-bx-csv="'+k+'">'+esc(t({risk:"Risk bordereau (CSV)",claims:"Claims bordereau (CSV)",reconciliation:"Reconciliation (CSV)"}[k]))+'</button>'; }).join(" ")+'</div>'+
          '<p class="fine">'+esc(t("{n} policies bound · premiums {premiums} · your fees {fees} · platform {platform} · claims paid {claims} · premiums returned {returned}",
            {n:f0.format(items.policies_bound||0),premiums:money(items.gross_premiums_bound||0),fees:money(items.fronting_fees_on_bound_policies||0),platform:money(items.platform_fees_on_bound_policies||0),claims:money(items.claims_paid||0),returned:money(items.premiums_returned||0)}))+'</p>'+
          '<p class="fine">'+(b.reconciled?esc(t("The ledger and the bound policies agree to the cent.")):esc(t("Ledger and bound policies differ by {diff}: instalment parts paid in other months, or fees returned on policies bound earlier.",{diff:money(items.difference_ledger_less_bound||0)})))+'</p>';
        holder.querySelector("[data-bx-month]").addEventListener("change",function(e){ load(e.target.value); });
        Array.prototype.forEach.call(holder.querySelectorAll("[data-bx-csv]"),function(btn){
          btn.addEventListener("click",function(){
            btn.disabled=true;
            downloadCsv("/api/company/bordereaux?carrier_id="+encodeURIComponent(id)+"&month="+encodeURIComponent(b.month)+"&kind="+btn.dataset.bxCsv+"&format=csv",auth,id+"-"+b.month+"-"+btn.dataset.bxCsv+".csv")
              .then(function(){ btn.disabled=false; },function(e){ btn.disabled=false; btn.textContent=refusalText(e); });
          });
        });
      },function(e){ holder.innerHTML='<p class="fine">'+esc(refusalText(e))+'</p>'; });
    }
    load("");
  });
}
/* The company's side of the same threads: its clock, its answer, its close. */
function bindCompanyComplaints(root, auth){
  Array.prototype.forEach.call(root.querySelectorAll("[data-complaints-for]"),function(holder){
    var id=holder.dataset.complaintsFor;
    function load(){
      var o={timeout:15000}; for(var k in auth)o[k]=auth[k];
      api("/api/company/complaints?carrier_id="+encodeURIComponent(id),o).then(function(r){
        var rows=r.complaints||[], s=r.summary||{};
        if(!rows.length){ holder.innerHTML='<p class="fine">'+esc(t("No complaints."))+'</p>'; return; }
        holder.innerHTML='<p class="fine">'+esc(t("{open} open · {overdue} overdue · {answered} answered · {closed} closed",{open:f0.format(s.open||0),overdue:f0.format(s.overdue||0),answered:f0.format(s.answered||0),closed:f0.format(s.closed||0)}))+'</p>'+
          rows.map(function(c){
            var route=c.route||{};
            return '<div class="policy-card" style="margin-bottom:10px"><div class="bar"><span class="lamp'+(c.status==="open"?"":" off")+'"></span><span class="label">'+esc(t(COMPLAINT_STATUS[c.status]||c.status))+'</span><span class="right label mono">'+esc(c.complaint_id)+' · '+esc(c.policy_id)+'</span></div>'+
              '<div class="body">'+(c.status==="open"?'<p class="fine">'+esc(c.overdue
                ?t("Overdue: the {days} days to answer have passed. Answer now; the holder may already have taken it to {body}.",{days:route.answer_days,body:route.body||""})
                :t("{n} days left to answer, until {when}.",{n:Math.max(0,Math.ceil(c.days_left)),when:complaintWhen(c.deadline_at)}))+'</p>':'')+
              '<p class="fine">'+esc(t(COMPLAINT_SUBJECTS[c.subject]||c.subject))+'</p>'+complaintThread(c)+
              (c.status!=="closed"?'<div style="margin-top:8px;display:grid;gap:6px"><textarea class="dlg-input" rows="2" data-co-complaint-text="'+esc(c.complaint_id)+'" placeholder="'+esc(t("Your answer, on the record"))+'"></textarea><div>'+
                '<button class="btn btn-line btn-sm" type="button" data-co-complaint-send="'+esc(c.complaint_id)+'">'+esc(t("Answer"))+'</button> '+
                '<button class="btn btn-ghost btn-sm" type="button" data-co-complaint-close="'+esc(c.complaint_id)+'">'+esc(t("Close as settled"))+'</button> <span class="fine" data-co-complaint-out="'+esc(c.complaint_id)+'"></span></div></div>':'')+
              '</div></div>'; }).join("");
        bind();
      },function(e){ holder.innerHTML='<p class="fine">'+esc(refusalText(e))+'</p>'; });
    }
    function bind(){
      function out(cid,text){ var el=holder.querySelector('[data-co-complaint-out="'+cid+'"]'); if(el)el.textContent=text; }
      Array.prototype.forEach.call(holder.querySelectorAll("[data-co-complaint-send]"),function(b){
        b.addEventListener("click",function(){
          var cid=b.dataset.coComplaintSend, text=holder.querySelector('[data-co-complaint-text="'+cid+'"]').value; b.disabled=true;
          var o={method:"POST",body:{text:text}}; for(var k in auth)o[k]=auth[k];
          api("/api/complaints/"+encodeURIComponent(cid)+"/messages",o).then(load,function(e){ b.disabled=false; out(cid,refusalText(e)); });
        });
      });
      Array.prototype.forEach.call(holder.querySelectorAll("[data-co-complaint-close]"),function(b){
        b.addEventListener("click",function(){
          var cid=b.dataset.coComplaintClose, text=holder.querySelector('[data-co-complaint-text="'+cid+'"]').value; b.disabled=true;
          var o={method:"POST",body:{resolution:text}}; for(var k in auth)o[k]=auth[k];
          api("/api/complaints/"+encodeURIComponent(cid)+"/close",o).then(load,function(e){ b.disabled=false; out(cid,refusalText(e)); });
        });
      });
    }
    load();
  });
}
/* The contract as a file on the buyer's own device: the durable medium the
   distance selling rules ask for. The protocol notes the day it was taken. */
function bindContractCopies(root){
  Array.prototype.forEach.call(root.querySelectorAll("[data-contract-copy]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.contractCopy; b.disabled=true;
      fetch(API+"/api/policies/"+encodeURIComponent(id)+"/contract?download=1",{headers:{authorization:"Bearer "+identity.token}}).then(function(r){
        if(!r.ok)throw new Error("refused"); return r.text();
      }).then(function(text){
        var blob=new Blob([text],{type:"text/plain"}), url=URL.createObjectURL(blob), link=document.createElement("a");
        link.href=url; link.download=id+"-contract.txt"; document.body.appendChild(link); link.click(); link.remove();
        setTimeout(function(){URL.revokeObjectURL(url);},60000); b.disabled=false;
      }).catch(function(){ b.disabled=false; b.textContent=t("Could not fetch the contract; open My cover and try again."); });
    });
  });
}
var CANCEL_BASIS={mistake:N("Cancel: all of it comes back (bought less than an hour ago)"),
  rider:N("Cancel: all of it comes back (bought by Rider today)"),
  cooling_off:N("Cancel: all of it comes back (cooling off period)"),
  pro_rata:N("Cancel: {refund} comes back (the unexpired part)")};
function bindCancels(root){
  Array.prototype.forEach.call(root.querySelectorAll("[data-cancel-for]"),function(slot){
    var id=slot.dataset.cancelFor;
    api("/api/policies/"+encodeURIComponent(id)+"/cancellation",{token:identity.token}).then(function(c){
      if(!c.allowed){
        slot.innerHTML='<span class="fine">'+esc(t("Cannot be cancelled now: {why}",{why:ts(c.reason)}))+'</span>';
        return;
      }
      var w=c.withdrawal||{}, when=function(x){ return new Date(x*1000).toLocaleString(LOCALES[LANG]||"en-US"); };
      slot.innerHTML='<button class="btn btn-line btn-sm" type="button" data-cancel="'+esc(id)+'">'+
        esc(t(CANCEL_BASIS[c.basis]||"Cancel",{refund:money(c.refund)}))+'</button>'+
        (c.until?'<span class="fine"> '+esc(t("until {time}",{time:when(c.until)}))+'</span>':'')+
        (w.basis==="informed"?'<span class="fine"> · '+esc(t("Your {days} day right to withdraw runs from the day you received the contract; whatever comes back is paid within {refund_days} days, here at once.",{days:w.days,refund_days:w.refund_within_days}))+'</span>':'')+
        (w.basis==="not_informed"?'<span class="fine"> · '+esc(t("You were not given the contract on a durable medium before buying, so you may withdraw for a year. Download your copy below."))+'</span>':'');
      var b=slot.querySelector("[data-cancel]");
      b.addEventListener("click",function(){
        if(!confirm(t("Cancel this policy? {refund} will be returned to your address and the cover ends now.",{refund:money(c.refund)})))return;
        b.disabled=true; b.textContent=t("Signing…");
        signedCall("cancel",{policy_id:id},"/api/policies/"+encodeURIComponent(id)+"/cancel",
          function(){return {account:identity.address};}).then(function(){ renderMine(); },
          function(e){ b.disabled=false; b.textContent=refusalText(e); });
      });
    },function(){});
  });
}
/* ---- what needs attention, at the top of My cover ----------------------
   Telling somebody their own cover is about to end is not a campaign: it is
   about a policy this address already holds, it needs no name and no address
   to send it to, and it is read here because they signed in rather than
   pushed at them anywhere. Two rules keep it that way. It never nags
   somebody whose policy already renews itself, and the one case worth
   saying out loud is the one the page has been silent about: cover that has
   already ended, where the honest sentence is that there is none now. */
var ENDS_SOON_DAYS=30;
var ENDED_RECENTLY_DAYS=30;
function needsAttention(policies,instructions){
  var now=Date.now()/1000, standing={}, ending=[], ended=[];
  (instructions||[]).forEach(function(x){
    if(x.kind==="renew"&&(x.status==="live"||x.status==="waiting"))standing[x.policy_id]=true;
  });
  (policies||[]).forEach(function(p){
    if(!p.ends_at||standing[p.policy_id])return;
    var days=Math.ceil((p.ends_at-now)/86400);
    if(p.status==="active"){ if(days<=ENDS_SOON_DAYS)ending.push({policy:p,days:Math.max(0,days)}); }
    else if(p.status==="lapsed"&&days<0&&-days<=ENDED_RECENTLY_DAYS)ended.push({policy:p,days:-days});
  });
  ending.sort(function(a,b){return a.days-b.days;});
  ended.sort(function(a,b){return a.days-b.days;});
  return {ending:ending,ended:ended};
}
function dueRow(item,gone){
  return '<li class="due-row"><span class="due-what"><b>'+esc(ts(item.policy.peril_name||""))+'</b>'+
    '<span class="fine">'+esc(ts(item.policy.subject_text||""))+'</span></span>'+
    '<span class="due-when">'+esc(gone
      ? t("Ended {days} days ago, and has not been replaced",{days:item.days})
      : (item.days?t("Ends in {days} days",{days:item.days}):t("Ends today")))+'</span>'+
    '<button class="btn '+(gone?"btn-line":"btn-primary")+' btn-sm" type="button" data-due-renew="'+
      esc(item.policy.policy_id)+'">'+esc(gone?t("Buy it again"):t("Renew"))+'</button></li>';
}
function renderDue(policies,instructions){
  var box=$("mine-due"); if(!box)return;
  var due=needsAttention(policies,instructions);
  if(!due.ending.length&&!due.ended.length){ box.innerHTML=""; return; }
  box.innerHTML='<div class="panel due-panel"><h2 class="due-head">'+esc(t("Worth looking at"))+'</h2>'+
    '<ul class="due-list">'+due.ended.map(function(x){return dueRow(x,true);}).join("")+
    due.ending.map(function(x){return dueRow(x,false);}).join("")+'</ul>'+
    (due.ended.length?'<p class="fine">'+esc(t("Buying it again starts a new term from the day the insurer approves it, at today's price. The days in between were not covered and cannot be."))+'</p>':'')+
    '</div>';
  Array.prototype.forEach.call(box.querySelectorAll("[data-due-renew]"),function(b){
    b.addEventListener("click",function(){
      var p=(policies||[]).filter(function(x){return x.policy_id===b.dataset.dueRenew;})[0];
      if(p)renewFrom(p);
    });
  });
}
/* ---- the papers this address was given --------------------------------
   The protocol has no email address to send anything to, so what the law
   requires it to give — the order confirmed, the terms accepted, the right
   to withdraw — is kept here under the address that bought the cover. Opening
   one is what records that it was read, so the list carries no text: the
   words arrive when somebody actually asks for them. */
var PAPER_KINDS={confirmation:N("Order confirmed"),terms:N("The contract"),
  withdrawal:N("Your right to withdraw"),decision:N("The insurer's decision")};
function paperRow(paper){
  return '<li class="paper-row'+(paper.opened_at?"":" unread")+'" data-paper="'+esc(paper.paper_id)+'">'+
    '<button class="paper-open" type="button">'+
      '<span class="paper-what"><b>'+esc(t(PAPER_KINDS[paper.kind]||paper.kind))+'</b>'+
        // The heading above is this paper's name in the reader's language, so
        // the line under it carries only what it is about, not the same
        // sentence again in English.
        '<span class="fine mono">'+esc(paper.about||"")+'</span></span>'+
      '<span class="paper-when fine">'+esc(new Date(paper.given_at*1000).toLocaleDateString(LANG))+
        (paper.opened_at?"":' <span class="pill">'+esc(t("New"))+'</span>')+'</span>'+
    '</button><div class="paper-body" hidden></div></li>';
}
function renderPapers(){
  var box=$("mine-papers"); if(!box||!identity.token)return;
  api("/api/papers",{token:identity.token}).then(function(reply){
    var rows=(reply.papers||[]);
    if(!rows.length){ box.innerHTML=""; return; }
    box.innerHTML='<div class="panel paper-panel"><h2 class="due-head">'+esc(t("Your papers"))+
      (reply.unread?' <span class="pill">'+esc(t("{n} unread",{n:reply.unread}))+'</span>':'')+'</h2>'+
      '<p class="fine">'+esc(t("Kept here because nothing is sent anywhere: no email address or telephone number is asked for. Opening one is written down, and nothing is ever removed."))+'</p>'+
      '<p class="fine">'+esc(t("The papers themselves are in English, which is the binding text, as the contract is."))+'</p>'+
      '<ul class="due-list">'+rows.map(paperRow).join("")+'</ul></div>';
    Array.prototype.forEach.call(box.querySelectorAll(".paper-row"),function(row){
      row.querySelector(".paper-open").addEventListener("click",function(){
        var body=row.querySelector(".paper-body");
        if(!body.hidden){ body.hidden=true; return; }
        body.hidden=false; body.textContent=t("Opening…");
        api("/api/papers/"+encodeURIComponent(row.dataset.paper),{token:identity.token}).then(function(r){
          body.textContent=(r.paper||{}).body||"";
          row.classList.remove("unread");
          var pill=row.querySelector(".pill"); if(pill)pill.remove();
        },function(e){ body.textContent=refusalText(e); });
      });
    });
  },function(){});
}
function renderMineExtras(policies){
  var box=$("mine-extras"); if(!box||!identity.token)return;
  Promise.all([
    api("/api/payouts",{token:identity.token}).catch(function(){return null;}),
    api("/api/mandate",{token:identity.token}).catch(function(){return null;}),
    api("/api/funding",{token:identity.token}).catch(function(){return null;}),
    api("/api/rewards",{token:identity.token}).catch(function(){return null;}),
    api("/api/instructions",{token:identity.token}).catch(function(){return null;}),
  ]).then(function(all){
    box.innerHTML=rewardsPanel(all[3])+fundingPanel(all[2])+payoutPanel(all[0])+instructionsPanel(all[4])+mandatePanel(all[1]);
    bindFundingPanel(all[2]); bindPayoutPanel(all[0]); bindInstructionsPanel(); bindMandatePanel(all[1]);
    bindAutoRenew(document,(all[4]||{}).instructions||[]);
    renderDue(policies||[],(all[4]||{}).instructions||[]);
    renderPapers();
  });
}
/* ---------------- what is given back for cover held ----------------
   Three things this panel must say, because a loyalty scheme attached to
   insurance goes wrong in exactly three ways: it is not a discount on the
   premium, it is not the insurer's money, and on this build it is not a token
   anybody holds. The first two are enforced in clause/protocol/rewards.py;
   the third is said here in the same words the test network warning uses. */
function rewardsPanel(r){
  if(!r)return "";
  var earning=r.earning>0
    ? '<div class="hrow"><span>'+esc(t("Earning now"))+'</span><b class="mono">+'+esc(f2.format(r.earning))+' '+esc(r.unit)+'</b></div>' : "";
  var rows=(r.running||[]).slice(0,6).map(function(x){
    return '<div class="hrow"><span class="mono">'+esc(x.policy_id)+'</span>'+
      '<b class="mono">'+esc(t("{days} days · x{multiplier}",{days:f0.format(x.days),multiplier:x.multiplier}))+'</b></div>';
  }).join("");
  var awards=(r.awards||[]).slice(0,6).map(function(a){
    return '<div class="hrow"><span class="mono">'+esc(a.policy_id)+'</span>'+
      '<b class="mono">+'+esc(f2.format(a.points))+'</b></div>';
  }).join("");
  return '<details class="more" id="rewards-box"><summary>'+esc(t("Rewards"))+': <b>'+
      esc(f2.format(r.balance))+' '+esc(r.unit)+'</b></summary><div class="inner">'+
    '<p class="fine">'+esc(t("Cover held earns RIALO: the limit, for the time it is actually in force. A year of cover earns a year's worth, and a policy cancelled on its second day earns two days. Each term renewed without a break longer than {days} days raises the rate it earns at.",{days:r.grace_days}))+'</p>'+
    '<div class="holding" style="margin-top:10px">'+
      '<div class="hrow"><span>'+esc(t("Credited"))+'</span><b class="mono">'+esc(f2.format(r.balance))+' '+esc(r.unit)+'</b></div>'+
      earning+
      '<div class="hrow"><span>'+esc(t("Unbroken terms"))+'</span><b class="mono">'+esc(f0.format(r.streak))+
        ' · x'+esc(String(r.multiplier))+(r.next_multiplier>r.multiplier?' → x'+esc(String(r.next_multiplier)):'')+'</b></div>'+
    '</div>'+
    (rows?'<div class="label" style="margin:14px 0 6px">'+esc(t("Still earning"))+'</div><div class="holding">'+rows+'</div>':'')+
    (awards?'<div class="label" style="margin:14px 0 6px">'+esc(t("Credited when the term ended"))+'</div><div class="holding">'+awards+'</div>':'')+
    '<p class="fine" style="margin-top:12px">'+esc(t("This is not a discount: the price on the screen is the pool's price and stays so. It is paid by the platform out of its own fee, which comes from the issuing company and never from you, so it costs the insurer nothing and the pool nothing."))+'</p>'+
    '<p class="fine"><b>'+esc(t("On this demonstration it is an accrual, not a token."))+'</b> '+
      esc(t("The chain here is simulated and so is the balance: nothing is held in a wallet and nothing can be spent. What is credited is an account of what would be owed."))+'</p>'+
    '</div></details>';
}

