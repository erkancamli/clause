/* ---------------- applications ---------------- */
var APP_STATUS={pending:N("waiting for the insurer"),approved:N("approved: the policy and its token are in your account"),
  rejected:N("rejected, premium returned"),withdrawn:N("withdrawn, premium returned"),lapsed:N("not decided in time, premium returned")};
function renderMineApplications(){
  var box=$("mine-apps"); if(!box||!identity.token)return;
  api("/api/applications",{token:identity.token}).then(function(reply){
    var rows=(reply.applications||[]).filter(function(a){ return a.status!=="approved"; });
    if(!rows.length){ box.innerHTML=""; return; }
    box.innerHTML='<div style="margin-top:22px;display:grid;gap:12px">'+rows.map(function(a){
      return '<div class="policy-card"><div class="bar"><span class="lamp'+(a.status==="pending"?"":" off")+'"></span>'+
        '<span class="label">'+esc(t(APP_STATUS[a.status]||a.status))+'</span><span class="right label mono">'+esc(a.app_id)+'</span></div>'+
        '<div class="body"><div class="kvs">'+
          kv(a.what||"",esc(a.subject_text||""))+
          kv(t("Cover"),f0.format(a.limit)+' USDC')+
          kv(a.status==="pending"?t("Premium held"):t("Premium"),money(a.total||a.premium))+
          kv(t("Issued by"),esc(ts(a.carrier||"")))+
        '</div>'+
        (a.note?'<p class="fine">'+esc(t("The insurer wrote: {note}",{note:a.note}))+'</p>':'')+
        ((a.documents||[]).length?'<div class="fine" style="display:grid;gap:4px">'+a.documents.map(function(d){
          return '<div>'+esc(d.filename)+' ('+esc(docSize(d.bytes))+') · '+esc(docStateText(d))+
            (a.status==="pending"&&d.available?' <button class="btn btn-ghost btn-sm" type="button" data-doc-remove="'+esc(a.app_id)+'/'+esc(d.doc_id)+'">'+esc(t("Take it back"))+'</button>':'')+'</div>';
        }).join("")+'</div>':'')+
        // The page has been telling people they could add documents here. Now
        // it lets them, for as long as the application is still open.
        (a.status==="pending"&&(a.checks||[]).indexOf("ownership")>=0
          ? '<div data-docs-for="'+esc(a.app_id)+'">'+docPickerHtml("app-docs-"+esc(a.app_id),
              t("Add the paper that shows it is yours"))+'</div>' : '')+
        (a.status==="pending"&&reply.demo?'<p class="fine">'+esc(t("On this demonstration you approve it yourself: sign out, sign in as a company, take the issuer's desk on the Company page and decide it there; or decide it as the operator, under Applications."))+'</p>':'')+
        (a.status==="pending"?'<div><button class="btn btn-ghost btn-sm" type="button" data-withdraw-app="'+esc(a.app_id)+'">'+
          esc(t("Withdraw the application"))+'</button></div>':'')+
        '</div></div>';
    }).join("")+'</div>';
    Array.prototype.forEach.call(box.querySelectorAll("[data-docs-for]"),function(slot){
      var a=rows.filter(function(x){return x.app_id===slot.dataset.docsFor;})[0];
      if(a)bindDocPicker("app-docs-"+a.app_id,a,function(){ renderMineApplications(); });
    });
    Array.prototype.forEach.call(box.querySelectorAll("[data-withdraw-app]"),function(b){
      b.addEventListener("click",function(){
        b.disabled=true;
        /* Signed, because it releases the escrow. The session used to be
           enough and a session is for reading. */
        signedCall("withdraw-application",{app_id:b.dataset.withdrawApp},
                   "/api/applications/"+encodeURIComponent(b.dataset.withdrawApp)+"/withdraw",
                   function(){ return {account:identity.address}; })
          .then(function(){ renderMine(); },function(e){ b.disabled=false; b.textContent=refusalText(e); });
      });
    });
    Array.prototype.forEach.call(box.querySelectorAll("[data-doc-remove]"),function(b){
      b.addEventListener("click",function(){
        b.disabled=true;
        api("/api/applications/"+b.dataset.docRemove.split("/").map(encodeURIComponent).join("/documents/"),{method:"DELETE",token:identity.token})
          .then(function(){ renderMineApplications(); },function(e){ b.disabled=false; b.textContent=refusalText(e); });
      });
    });
  },function(){});
}
/* The review side, for the operator and for a company's own applications. */
function reviewHtml(list, waiting){
  if(!list.length) return '<div class="panel" style="padding:20px"><p>'+esc(t("No applications."))+'</p></div>';
  return '<div style="display:grid;gap:12px">'+list.map(function(a){
    var open=a.status==="pending";
    return '<div class="panel" style="padding:18px;display:grid;gap:10px">'+
      '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:baseline"><b class="mono">'+esc(a.app_id)+'</b>'+
      '<span class="pill'+(open?"":" ok")+'">'+esc(t(APP_STATUS[a.status]||a.status))+'</span>'+
      '<span class="fine">'+esc(ts(a.carrier||""))+'</span></div>'+
      '<div class="kvs">'+
        kv(t("Applicant"),esc(short(a.holder||"")),"mono")+
        kv(a.what||t("Cover"),esc(a.subject_text||""))+
        kv(t("Cover"),f0.format(a.limit)+' USDC')+
        kv(t("Premium held"),money(a.premium))+
        kv(t("Declared at risk"),money(a.value_at_risk||0))+
        (a.address?kv(t("Address given"),esc(["street","number","flat","postcode","city"].map(function(k){return a.address[k]||"";}).filter(Boolean).join(", "))):"")+
        (a.plan?kv(t("Paid in"),esc(t("{n} instalments of {amount}",{n:a.plan.count,amount:money(a.plan.amount)}))):"")+
        kv(t("Resident in"),esc(regionName(a.country||"")))+
      '</div>'+
      ((a.documents||[]).length?'<div class="fine" style="display:grid;gap:6px"><div class="label">'+esc(t("Documents, sealed to you"))+'</div>'+a.documents.map(function(d){
        return '<div data-doc-row="'+esc(d.doc_id)+'">'+esc(d.filename)+' ('+esc(docSize(d.bytes))+') · '+esc(docStateText(d))+
          (d.available?' <button class="btn btn-line btn-sm" type="button" data-open-doc="'+esc(a.app_id)+'/'+esc(d.doc_id)+'">'+esc(t("Open"))+'</button>':'')+'</div>';
      }).join("")+'</div>':(open&&a.checks.indexOf("ownership")>=0?'<p class="fine">'+esc(t("No documents were sent with this application; the applicant may still add them from My cover, or you check by other means."))+'</p>':''))+
      (open?'<div class="checks" data-checks="'+esc(a.app_id)+'">'+a.checks.map(function(c){
        return '<label><input type="checkbox" value="'+esc(c)+'"> '+esc(t("Done: {what}",{what:t(CHECK_NAMES[c]||c)}))+'</label>';
      }).join("")+'</div>'+
      '<div class="tform"><label><span>'+esc(t("Note, shown to the applicant"))+'</span><input data-note-app="'+esc(a.app_id)+'" style="min-width:280px"></label>'+
      '<button class="btn btn-primary btn-sm" type="button" data-decide="'+esc(a.app_id)+'" data-d="approve">'+esc(t("Approve and write the policy"))+'</button>'+
      '<button class="btn btn-line btn-sm" type="button" data-decide="'+esc(a.app_id)+'" data-d="reject">'+esc(t("Reject and refund"))+'</button></div>'+
      '<p class="fine" data-out-app="'+esc(a.app_id)+'"></p>'
      :(a.decided_by?'<p class="fine">'+esc(t("Decided by {who}.",{who:a.decided_by}))+(a.note?' '+esc(a.note):'')+'</p>':''))+
      '</div>';
  }).join("")+'</div>';
}
/* The statement panels on the company page: one per company, a month at a time. */
function bindStatements(root, auth){
  Array.prototype.forEach.call(root.querySelectorAll("[data-statement-for]"),function(holder){
    var id=holder.dataset.statementFor;
    function load(month){
      var o={timeout:20000}; for(var k in auth)o[k]=auth[k];
      api("/api/company/statements?carrier_id="+encodeURIComponent(id)+(month?"&month="+encodeURIComponent(month):""),o).then(function(r){
        holder.innerHTML=statementHtml(r.statement,r.months,r.statement.month,id);
        var sel=holder.querySelector("[data-statement-month]"); if(sel)sel.addEventListener("change",function(){ load(sel.value); });
        var dl=holder.querySelector("[data-statement-csv]"); if(dl)dl.addEventListener("click",function(){
          dl.disabled=true;
          downloadCsv("/api/company/statements?carrier_id="+encodeURIComponent(id)+"&month="+encodeURIComponent(r.statement.month)+"&format=csv",auth,id+"-"+r.statement.month+".csv")
            .then(function(){ dl.disabled=false; },function(e){ dl.disabled=false; dl.textContent=refusalText(e); });
        });
      },function(e){ holder.innerHTML='<p class="fine">'+esc(refusalText(e))+'</p>'; });
    }
    load("");
  });
}
function bindReview(root, auth, done){
  Array.prototype.forEach.call(root.querySelectorAll("[data-open-doc]"),function(b){
    b.addEventListener("click",function(){
      b.disabled=true; b.textContent=t("Opening…");
      var opts={timeout:60000}; for(var k in auth)opts[k]=auth[k];
      var parts=b.dataset.openDoc.split("/");
      api("/api/applications/"+encodeURIComponent(parts[0])+"/documents/"+encodeURIComponent(parts[1]),opts).then(function(envelope){
        return openSealed(envelope).then(function(blob){
          var url=URL.createObjectURL(blob), a=document.createElement("a");
          a.className="btn btn-line btn-sm"; a.href=url; a.target="_blank"; a.rel="noopener"; a.download=envelope.filename||"document";
          a.textContent=t("Open {name}",{name:envelope.filename||"document"});
          b.replaceWith(a);
          if(/^image\//.test(blob.type)){ var img=document.createElement("img"); img.src=url; img.style.cssText="display:block;max-width:100%;max-height:420px;margin-top:6px;border:1px solid var(--line)"; a.parentNode.appendChild(img); }
        },function(){
          b.disabled=false; b.textContent=t("Open");
          var row=b.parentNode; if(row){ var note=document.createElement("span"); note.className="fine"; note.textContent=" "+t("This browser does not hold the key these were sealed to. The applicant sent them to the browser that registered the reading key; open them there, or ask for them again from this one."); row.appendChild(note); }
        });
      },function(e){ b.disabled=false; b.textContent=refusalText(e); });
    });
  });
  Array.prototype.forEach.call(root.querySelectorAll("[data-decide]"),function(b){
    b.addEventListener("click",function(){
      var id=b.dataset.decide, d=b.dataset.d;
      var boxes=root.querySelector('[data-checks="'+id+'"]');
      var checked=boxes?Array.prototype.filter.call(boxes.querySelectorAll("input"),function(i){return i.checked;}).map(function(i){return i.value;}):[];
      var note=(root.querySelector('[data-note-app="'+id+'"]')||{}).value||"";
      var out=root.querySelector('[data-out-app="'+id+'"]');
      b.disabled=true;
      var opts={method:"POST",body:{decision:d,checked:checked,note:note},timeout:40000};
      for(var k in auth)opts[k]=auth[k];
      api("/api/review/applications/"+encodeURIComponent(id),opts).then(done,function(e){
        b.disabled=false; if(out)out.textContent=refusalText(e);
      });
    });
  });
}

