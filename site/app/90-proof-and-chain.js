/* ---------------- proof ----------------
   Wake, folded into Clause. The question an insurer normally answers out of its
   own file, answered instead from what the chain stored. */


/* ---------------- the public chain beside the protocol's ----------------
   Keccak-256 in the browser, so a proof can be checked without trusting the
   page's server: BigInt lanes, a proof is a dozen hashes, speed is nothing. */
var KC_RC=["0x1","0x8082","0x800000000000808a","0x8000000080008000","0x808b","0x80000001","0x8000000080008081","0x8000000000008009","0x8a","0x88","0x80008009","0x8000000a","0x8000808b","0x800000000000008b","0x8000000000008089","0x8000000000008003","0x8000000000008002","0x8000000000000080","0x800a","0x800000008000000a","0x8000000080008081","0x8000000000008080","0x80000001","0x8000000080008008"].map(function(h){ return BigInt(h); });
var KC_ROT=[[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]];
var KC_M=(1n<<64n)-1n;
function kcRol(x,n){ if(!n)return x; var b=BigInt(n); return ((x<<b)|(x>>(64n-b)))&KC_M; }
function kcF(s){
  for(var r=0;r<24;r++){
    var c=[],d=[],b=new Array(25),x,y;
    for(x=0;x<5;x++)c[x]=s[x]^s[x+5]^s[x+10]^s[x+15]^s[x+20];
    for(x=0;x<5;x++)d[x]=c[(x+4)%5]^kcRol(c[(x+1)%5],1);
    for(x=0;x<5;x++)for(y=0;y<5;y++)s[x+5*y]^=d[x];
    for(x=0;x<5;x++)for(y=0;y<5;y++)b[y+5*((2*x+3*y)%5)]=kcRol(s[x+5*y],KC_ROT[x][y]);
    for(x=0;x<5;x++)for(y=0;y<5;y++)s[x+5*y]=b[x+5*y]^(((~b[(x+1)%5+5*y])&KC_M)&b[(x+2)%5+5*y]);
    s[0]^=KC_RC[r];
  }
}
function keccak256(bytes){
  var rate=136,len=bytes.length,padded=new Uint8Array((Math.floor(len/rate)+1)*rate),i,k;
  padded.set(bytes); padded[len]^=0x01; padded[padded.length-1]^=0x80;
  var s=[]; for(i=0;i<25;i++)s.push(0n);
  for(var off=0;off<padded.length;off+=rate){
    for(i=0;i<17;i++){ var v=0n; for(k=7;k>=0;k--)v=(v<<8n)|BigInt(padded[off+8*i+k]); s[i]^=v; }
    kcF(s);
  }
  var out="0x";
  for(i=0;i<4;i++)for(k=0;k<8;k++)out+=Number((s[i]>>BigInt(8*k))&0xffn).toString(16).padStart(2,"0");
  return out;
}
function hexBytes(hex){ hex=hex.replace(/^0x/,""); var out=new Uint8Array(hex.length/2); for(var i=0;i<out.length;i++)out[i]=parseInt(hex.substr(2*i,2),16); return out; }
function kcWord(n){ return BigInt(n).toString(16).padStart(64,"0"); }
/* The leaf as the contract lays it out, the sibling walk in sorted order, and
   the root it must reach. Anything that does not match is "does not match":
   the page never explains a failure away. */
function anchorCheck(p){
  var f=p.fields;
  if(keccak256(new TextEncoder().encode(f.policy_id))!==f.policy_hash.toLowerCase())return false;
  var leaf=keccak256(hexBytes(f.policy_hash.slice(2)+f.holder_hash.slice(2)+kcWord(f.status_code)+kcWord(f.limit_cents)+kcWord(f.starts_at)+kcWord(f.ends_at)+f.terms_hash.slice(2)));
  if(leaf!==p.leaf.toLowerCase())return false;
  var node=leaf;
  p.proof.forEach(function(sib){ sib=sib.toLowerCase(); node=node<=sib?keccak256(hexBytes(node.slice(2)+sib.slice(2))):keccak256(hexBytes(sib.slice(2)+node.slice(2))); });
  return node===p.root.toLowerCase();
}
var ANCHOR_KINDS={mint:N("token mint"),burn:N("token burn"),settle:N("settlement record"),root:N("book root")};
function anchorState(st){ return {pending:t("waiting to be sent"),sent:t("sent"),confirmed:t("confirmed"),failed:t("failed")}[st]||st; }
function anchorLink(url,text){ return url?'<a href="'+esc(url)+'" target="_blank" rel="noreferrer noopener">'+esc(text)+'</a>':esc(text); }
function anchorShort(h){ return h?h.slice(0,10)+"…"+h.slice(-6):""; }
function renderAnchorStatus(box){
  api("/api/anchor",{timeout:9000}).then(function(a){
    var chain=a.chain||{},c=a.counts||{},lr=a.last_root,el=document.createElement("div");
    el.className="panel"; el.style.cssText="padding:26px;display:grid;gap:12px";
    var h='<div class="label">'+esc(t("On a public chain"))+' · '+esc(chain.name||"")+'</div>'+
      '<p style="font-size:14.5px;color:var(--ink-2)">'+esc(t("The protocol's own chain is the record. A public chain beside it holds a witness nobody here controls: each policy token, each settlement, and the root of the whole book, anchored on a timer."))+'</p>';
    if(a.mode!=="live")h+='<p class="fine">'+esc(t("Recorded here, not yet sent: the chain will be told the day the signer is funded."))+'</p>';
    else h+='<div class="kvs">'+kv(t("Signer"),'<span class="mono">'+anchorLink(a.signer_url,anchorShort(a.signer))+'</span>'+(a.balance_eth!=null?' · '+esc(Number(a.balance_eth).toFixed(4))+' ETH':''))+
      kv(t("Contracts"),'<span class="mono">'+anchorLink(a.contracts.policy_url,anchorShort(a.contracts.policy))+' · '+anchorLink(a.contracts.book_url,anchorShort(a.contracts.book))+'</span>')+'</div>';
    if(lr)h+='<div class="kvs">'+kv(t("Last root"),'<span class="mono" style="overflow-wrap:anywhere">'+esc(lr.payload.root)+'</span><br>'+esc(t("{n} policies, epoch {e}",{n:f0.format(lr.payload.count),e:lr.payload.epoch}))+' · '+esc(anchorState(lr.status))+(lr.tx_url?' · '+anchorLink(lr.tx_url,anchorShort(lr.tx_hash)):''))+'</div>';
    h+='<p class="fine">'+esc(t("Sent {s} · confirmed {c} · waiting {p} · failed {f}",{s:f0.format(c.sent||0),c:f0.format(c.confirmed||0),p:f0.format(c.pending||0),f:f0.format(c.failed||0)}))+'</p>';
    if((a.recent||[]).length)h+='<div style="display:grid;gap:4px">'+a.recent.map(function(i){ return '<div class="fine">'+esc(t(ANCHOR_KINDS[i.kind]||i.kind))+(i.policy_id?' · <span class="mono">'+esc(i.policy_id)+'</span>':'')+' · '+esc(anchorState(i.status))+(i.tx_url?' · <span class="mono">'+anchorLink(i.tx_url,anchorShort(i.tx_hash))+'</span>':'')+'</div>'; }).join("")+'</div>';
    el.innerHTML=h; box.appendChild(el);
  },function(){});
}
function renderAnchorFor(id,box){
  api("/api/policies/"+encodeURIComponent(id)+"/anchor",{timeout:9000}).then(function(a){
    var p=a.proof||{},el=document.createElement("div");
    el.className="panel"; el.style.cssText="padding:24px;display:grid;gap:12px;margin-top:14px";
    var h='<div class="label">'+esc(t("On a public chain"))+' · '+esc((a.chain||{}).name||"")+'</div>';
    if(a.mode!=="live")h+='<p class="fine">'+esc(t("Recorded here, not yet sent: the chain will be told the day the signer is funded."))+'</p>';
    h+='<div style="display:grid;gap:4px">'+(a.intents||[]).map(function(i){ return '<div class="fine">'+esc(t(ANCHOR_KINDS[i.kind]||i.kind))+' · '+esc(anchorState(i.status))+(i.tx_url?' · <span class="mono">'+anchorLink(i.tx_url,anchorShort(i.tx_hash))+'</span>':'')+'</div>'; }).join("")+'</div>';
    if(a.token_url&&a.mode==="live")h+='<p class="fine">'+anchorLink(a.token_url,t("The token on the explorer"))+'</p>';
    h+='<h4 style="font-size:15px;margin-top:6px">'+esc(t("Its place in the book"))+'</h4>';
    if(!p.root)h+='<p class="fine">'+esc(t("Not yet in a root: the next one will carry it."))+'</p>';
    else{
      if(!p.current)h+='<p class="fine">'+esc(t("Changed since the last root (now {status}); the next root will carry the change.",{status:t(POLICY_STATUS[p.fields.status]||p.fields.status)}))+'</p>';
      h+='<div class="kvs">'+kv(t("Leaf"),'<span class="mono" style="overflow-wrap:anywhere">'+esc(p.leaf)+'</span>')+
        kv(t("Siblings ({n})",{n:p.proof.length}),'<span class="mono" style="overflow-wrap:anywhere">'+(p.proof.length?p.proof.map(esc).join("<br>"):"–")+'</span>')+
        kv(t("Root"),'<span class="mono" style="overflow-wrap:anywhere">'+esc(p.root)+'</span>'+(p.tx_url?'<br>'+anchorLink(p.tx_url,t("anchored in this transaction")):''))+'</div>';
      h+='<div><button class="btn btn-ghost btn-sm" type="button" id="anchor-check">'+esc(t("Check it in this browser"))+'</button> <span id="anchor-check-out" class="fine"></span></div>';
      h+='<p class="fine">'+esc(t("The same check on the chain: verify(root, proof, leaf) on the book contract returns true."))+'</p>';
    }
    el.innerHTML=h; box.appendChild(el);
    var btn=$("anchor-check");
    if(btn)btn.addEventListener("click",function(){
      var out=$("anchor-check-out"),ok=false;
      try{ ok=anchorCheck(p); }catch(e){ ok=false; }
      out.textContent=ok?t("Checks out: this leaf, hashed up through its siblings, gives the root."):t("Does not match.");
    });
  },function(){});
}

/* The rulebook, read from the protocol so the page and the contract never
   differ: the same words, peril by peril. */
/* Pointing a question at a source and showing what came back.

   The protocol settles policies this way and the only way to watch it was to
   buy cover and wait for the weather. Here the same reading happens with
   nothing staked on the answer, which is the half of a prediction market
   worth having; the stake is the half this will not have, because what makes
   cover insurance rather than a bet is that the buyer has something at risk.

   The form is drawn from what the protocol says it can answer, not from a
   list here, so a question shape it stops answering stops being offered. */
var ASK={kind:"quake",shapes:[],places:[],airports:[],point:null,busy:false};

function askShape(kind){
  for(var i=0;i<ASK.shapes.length;i++)if(ASK.shapes[i].kind===kind)return ASK.shapes[i];
  return null;
}

function renderAskForm(){
  var form=$("ask-form"); if(!form)return;
  if(!ASK.shapes.length){
    api("/api/ask/shapes",{timeout:15000}).then(function(r){
      ASK.shapes=r.shapes||[]; ASK.places=r.places||[]; ASK.airports=r.airports||[];
      drawAskFields();
    },function(){ drawAskFields(); });
  }
  drawAskFields();
}

/* One field: its label, the box, and the unit beside the box rather than
   under it. A number field is given the width of a number; left to share the
   row equally, a two digit answer sat in a 560px box, which is the same empty
   frame this site has drawn around a drawing before. */
function fld(open,label,input,unit){
  return open+'<span>'+esc(label)+'</span><span class="in">'+input+
         (unit?'<i>'+esc(unit)+'</i>':'')+'</span></label>';
}
/* Given whole rather than pasted together from a size, so the class attribute
   is written in the source exactly as it reaches the page. A class built by
   concatenation cannot be read back by anything, including the guard that
   holds this page's styles to this page. */
var FLD_WIDE='<label class="fld wide">', FLD_NUM='<label class="fld num">';

function drawAskFields(){
  var box=$("ask-fields"), note=$("ask-source"); if(!box)return;
  var shape=askShape(ASK.kind), unit=shape?shape.unit:"";
  var line=shape&&shape.defaults?shape.defaults.threshold:0;
  var rows=[];

  function chooser(id,options,empty){
    return options.length
      ? '<select id="'+id+'">'+options.map(function(o){ return '<option>'+esc(o)+'</option>'; }).join("")+'</select>'
      : '<select id="'+id+'" disabled><option value="">'+esc(empty)+'</option></select>';
  }

  if(ASK.kind==="quake"){
    rows.push(fld(FLD_WIDE,t("Place"),
      '<input id="ask-place" type="text" autocomplete="off" placeholder="'+esc(t("a town or an address"))+'" value="'+esc(ASK.placeText||"")+'">',""));
    rows.push(fld(FLD_NUM,t("At least"),
      '<input id="ask-line" type="number" step="0.1" min="0" max="10" value="'+esc(String(line))+'">',"Mw"));
    rows.push(fld(FLD_NUM,t("Within"),
      '<input id="ask-radius" type="number" step="10" min="1" max="1000" value="'+esc(String((shape&&shape.defaults.radius_km)||300))+'">',"km"));
  }else if(ASK.kind==="wind"||ASK.kind==="rain"){
    rows.push(fld(FLD_WIDE,t("Place"),chooser("ask-place",ASK.places,t("the source is not answering")),""));
    rows.push(fld(FLD_NUM,t("Reaches"),
      '<input id="ask-line" type="number" step="1" min="0" value="'+esc(String(line))+'">',unit));
  }else{
    rows.push(fld(FLD_WIDE,t("Airport"),chooser("ask-place",ASK.airports,t("no airport is reporting a delay right now")),""));
    rows.push(fld(FLD_NUM,t("At least"),
      '<input id="ask-line" type="number" step="1" min="1" max="500" value="'+esc(String(line))+'">',t("flights")));
  }
  box.innerHTML=rows.join("");
  if(note)note.textContent=shape?t("Read from {source}",{source:shape.source}):"";
  Array.prototype.forEach.call(form_chips(),function(b){
    var on=b.getAttribute("data-kind")===ASK.kind;
    b.classList.toggle("on",on);
    b.setAttribute("aria-pressed",on?"true":"false");
  });
}

function form_chips(){ var f=$("ask-form"); return f?f.querySelectorAll(".askrow .chip"):[]; }

/* Wired once, on the form rather than on each button, because the buttons are
   redrawn every time the question changes. */
(function(){
  var form=$("ask-form"); if(!form)return;
  form.addEventListener("click",function(e){
    var chip=e.target.closest?e.target.closest(".askrow .chip"):null;
    if(chip&&chip.getAttribute("data-kind")){
      ASK.kind=chip.getAttribute("data-kind");
      var out=$("ask-out"); if(out)out.innerHTML="";
      drawAskFields();
      return;
    }
    if(e.target.id==="ask-run")runAsk();
  });
  form.addEventListener("keydown",function(e){
    if(e.key==="Enter"&&e.target.tagName==="INPUT"){ e.preventDefault(); runAsk(); }
  });
})();

/* A place typed as text has to become a point before the source can be asked
   about it, because a seismic catalogue knows coordinates and not town names. */
function askPoint(text){
  if(ASK.point&&ASK.point.text===text)return Promise.resolve(ASK.point);
  return api("/api/geocode?q="+encodeURIComponent(text),{timeout:12000}).then(function(r){
    var first=(r.places||[])[0];
    if(!first)throw new Error("nowhere");
    ASK.point={text:text,name:first.name,latitude:first.latitude,longitude:first.longitude};
    return ASK.point;
  });
}

function runAsk(){
  var out=$("ask-out"); if(!out||ASK.busy)return;
  var line=parseFloat(($("ask-line")||{}).value);
  if(!isFinite(line)){ askFailed(t("Write down the line the question turns on.")); return; }
  var field=$("ask-place"), said=field?String(field.value||"").trim():"";
  if(!said){ askFailed(t("Say where to ask about.")); return; }

  ASK.busy=true;
  out.innerHTML='<div class="panel" style="padding:20px">'+esc(t("Asking the source…"))+'</div>';
  var ready;
  if(ASK.kind==="quake"){
    ASK.placeText=said;
    ready=askPoint(said).then(function(p){
      var radius=parseFloat(($("ask-radius")||{}).value)||300;
      return "kind=quake&latitude="+encodeURIComponent(p.latitude)+
             "&longitude="+encodeURIComponent(p.longitude)+
             "&place="+encodeURIComponent(p.name)+
             "&threshold="+encodeURIComponent(line)+"&radius_km="+encodeURIComponent(radius);
    });
  }else if(ASK.kind==="delays"){
    ready=Promise.resolve("kind=delays&airport="+encodeURIComponent(said)+"&threshold="+encodeURIComponent(line));
  }else{
    ready=Promise.resolve("kind="+ASK.kind+"&place="+encodeURIComponent(said)+"&threshold="+encodeURIComponent(line));
  }
  ready.then(function(query){ return api("/api/ask?"+query,{timeout:20000}); })
    .then(function(a){ ASK.busy=false; drawAnswer(a); },
          function(err){ ASK.busy=false; askFailed(readableAskError(err)); });
}

function readableAskError(err){
  /* The protocol's refusals are written to be read, so they are shown as they
     came rather than replaced with something vaguer. A 422 here is the
     protocol saying the question cannot be answered as asked, which is the
     most useful thing a reader can be told; anything else is a failure to
     reach it, which is a different sentence. */
  var said=err&&err.payload&&err.payload.detail;
  if(said)return ts(String(said));
  if(err&&err.message==="nowhere")return t("Nowhere by that name was found.");
  return t("The source did not answer.");
}

function askFailed(text){
  var out=$("ask-out"); if(!out)return;
  out.innerHTML='<div class="panel" style="padding:20px"><p class="fine" style="margin:0">'+esc(text)+'</p></div>';
}

function drawAnswer(a){
  var out=$("ask-out"); if(!out)return;
  var yes=!!a.verdict, d=a.detail||{};
  var figure=(a.reading===null||a.reading===undefined)
    ? t("nothing the source published met it")
    : f2.format(a.reading)+" "+a.unit;
  var rows=[];
  function row(k,v){ if(v!==""&&v!==null&&v!==undefined)rows.push('<div class="kv"><div class="k">'+esc(k)+'</div><div class="v">'+v+'</div></div>'); }

  row(t("Source"),esc(a.source)+(a.url?' · <a href="'+esc(a.url)+'" target="_blank" rel="noopener noreferrer">'+esc(t("the record"))+'</a>':''));
  row(t("What it said"),esc(figure));
  row(t("The line asked about"),esc(f2.format(a.threshold)+" "+a.unit));
  if(d.event)row(t("The event"),esc(d.event)+(d.distance_km!=null?' · '+esc(t("{n} km away",{n:f0.format(d.distance_km)})):""));
  if(d.worst_minutes!=null)row(t("Worst delay there"),esc(t("{n} minutes",{n:f0.format(d.worst_minutes)})));
  if(d.events_in_radius!=null)row(t("Records inside the circle"),esc(f0.format(d.events_in_radius)));

  var clocks=[];
  if(a.measured_at)clocks.push('<div><div class="k">'+esc(t("When the world did it"))+'</div><div>'+esc(docWhen(a.measured_at))+'</div></div>');
  if(a.retrieved_at)clocks.push('<div><div class="k">'+esc(t("When the source was read"))+'</div><div>'+esc(docWhen(a.retrieved_at))+'</div></div>');
  if(a.asked_at)clocks.push('<div><div class="k">'+esc(t("When you asked"))+'</div><div>'+esc(docWhen(a.asked_at))+'</div></div>');

  /* The class is written whole rather than pasted together, and the verdict
     rides an attribute. A class attribute built by concatenation cannot be
     read back by anything: the guard against a page's styles reaching another
     screen looks for the class being worn, and found nothing wearing this. */
  out.innerHTML='<div class="answer" data-yes="'+(yes?"1":"0")+'">'+
    '<div class="vd">'+esc(yes?t("Yes"):t("No"))+'</div>'+
    '<p class="q">'+esc(ts(a.question))+'</p>'+
    (a.stale?'<p class="fine warn">'+esc(t("This source has not answered for a while, so this is what it last said rather than what it says now."))+'</p>':'')+
    '<div class="kvs rulebook">'+rows.join("")+'</div>'+
    (clocks.length?'<div class="clocks">'+clocks.join("")+'</div>':'')+
    '<p class="fine" style="margin-top:14px">'+esc(t("Nothing was staked on this answer and nothing was paid on it. It is a reading, not a settlement."))+'</p>'+
    '</div>';
}

/* The rulebook, read rather than remembered.

   Five of its eleven rows carry the same text for every peril: how a reading
   is attested, how long you have to object, what happens if a publisher goes
   away, what is archived, and which version of the rulebook this is. Printed
   peril by peril they came out five times each, which pushed what actually
   differs between perils down a page of repetition.

   So a row whose text is the same everywhere is stated once, above. Which
   rows those are is decided by reading the answer, not by a list written here:
   the day a peril gets an archive rule of its own, that row drops out of the
   shared panel and appears in the peril's own, and nobody has to remember to
   come back and change this. */
function renderRules(){
  var box=$("rules-out"), top=$("rules-common"), nav=$("rules-nav"); if(!box)return;
  box.innerHTML='<div class="panel" style="padding:22px">'+esc(t("Reading the chain…"))+'</div>';
  if(top)top.innerHTML=""; if(nav)nav.innerHTML="";
  whenLinked().then(function(){
    if(!link.live){ box.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("This page cannot reach the protocol, so there is no record to read. It will not show you one it made up."))+'</p></div>'; return; }
    return api("/api/rulebook",{timeout:12000}).then(function(r){
      var perils=r.perils||{}, keys=Object.keys(perils);
      if(!keys.length){ box.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("The protocol did not answer."))+'</p></div>'; return; }

      /* Whether every peril says the same thing here. */
      function common(field){
        var first=JSON.stringify(perils[keys[0]][field]);
        if(first===undefined)return false;
        return keys.every(function(k){ return JSON.stringify(perils[k][field])===first; });
      }
      function days(h){ return Math.round(h/24); }

      /* The rulebook is the terms, and the English is the binding text, so it
         is never more than a click away. Once per peril rather than once per
         sentence: a reader who wants the binding wording wants all of it, and
         eleven separate toggles in one panel is a page of controls.

         Both readings are built by the same function, which is given the way
         to say a sentence: translated, or left as the protocol wrote it. Two
         functions would drift, and the one that drifted would be the one
         nobody reads until it matters. */
      function rows(x, en){
        var say=en?function(s){return String(s==null?"":s);}:ts;
        var lab=en?function(s){return s;}:t;
        var out=[];
        function row(label,html){ out.push('<div class="kv"><div class="k">'+esc(lab(label))+'</div><div class="v">'+html+'</div></div>'); }
        function list(tag,items){ return '<'+tag+' style="margin:0;padding-left:18px">'+(items||[]).map(function(i){ return '<li>'+esc(say(i))+'</li>'; }).join("")+'</'+tag+'>'; }

        if(!common("attestation")||en)row("Attestation",esc(say(x.attestation||"")));
        row("Primary source",esc(say(x.primary)));
        row("Fallbacks, in order",list("ol",x.fallbacks));
        var frozen=en?("frozen "+days(x.freeze_hours)+" days after the event")
                     :t("frozen {days} days after the event",{days:days(x.freeze_hours)});
        row("Final figure",esc(say(x.final_data))+' · '+esc(frozen));
        row("Tests a reading must pass",list("ul",x.criteria));
        if(x.waiting)row("When the cover applies",esc(say(x.waiting)));
        if(x.deadline_days)row("Silence",esc(
          en?("No final figure "+x.deadline_days+" days after the term ends: "+say(x.on_missing_data||""))
            :t("No final figure {days} days after the term ends: {then}",{days:x.deadline_days,then:ts(x.on_missing_data||"")})));
        if(!common("objection_days")||en)row("Objection",esc(
          en?("Within "+x.objection_days+" days of a settlement, on the Proof page, naming the reading you dispute; the operator answers with the archived inputs.")
            :t("Within {days} days of a settlement, on the Proof page, naming the reading you dispute; the operator answers with the archived inputs.",{days:x.objection_days})));
        if(!common("successor")||en)row("Successor source",esc(say(x.successor)));
        if(!common("archive")||en)row("Archive",esc(say(x.archive)));
        return out.join("");
      }

      /* The same for every peril, said once. Only the rows that really are. */
      function sharedRows(x, en){
        var say=en?function(s){return String(s==null?"":s);}:ts;
        var lab=en?function(s){return s;}:t;
        var out=[];
        function row(label,html){ out.push('<div class="kv"><div class="k">'+esc(lab(label))+'</div><div class="v">'+html+'</div></div>'); }
        if(common("attestation"))row("Attestation",esc(say(x.attestation||"")));
        if(common("objection_days"))row("Objection",esc(
          en?("Within "+x.objection_days+" days of a settlement, on the Proof page, naming the reading you dispute; the operator answers with the archived inputs.")
            :t("Within {days} days of a settlement, on the Proof page, naming the reading you dispute; the operator answers with the archived inputs.",{days:x.objection_days})));
        if(common("successor"))row("Successor source",esc(say(x.successor)));
        if(common("archive"))row("Archive",esc(say(x.archive)));
        return out.join("");
      }

      /* Shown only where there is something to show: in English the two
         readings are the same text, and a toggle onto an identical copy of
         what is already on screen is a control that does nothing. */
      function binding(body){
        if(LANG==="en"||!body)return "";
        return '<details class="orig"><summary>'+esc(t("English original"))+'</summary>'+
               '<div class="kvs rulebook" style="margin-top:10px">'+body+'</div></details>';
      }

      if(top){
        var same=sharedRows(perils[keys[0]],false);
        top.innerHTML=same
          ? '<div class="common"><h2>'+esc(t("The same for every peril"))+'</h2>'+
            '<p class="fine">'+esc(t("These four rules do not change from one peril to the next, so they are set down once here. Each of them is still part of section 10 of your own contract, whichever cover you hold."))+'</p>'+
            '<div class="kvs rulebook">'+same+'</div>'+
            binding(sharedRows(perils[keys[0]],true))+
            (common("version")?'<p class="fine" style="margin:14px 0 0">'+esc(t("Rulebook version {v}",{v:perils[keys[0]].version}))+'</p>':'')+
            '</div>'
          : "";
      }

      if(nav)nav.innerHTML=keys.map(function(k){
        return '<a href="#rule-'+esc(k)+'">'+esc(t(perils[k].title))+'</a>';
      }).join("");

      box.innerHTML=keys.map(function(k){
        var x=perils[k];
        /* Two waits that happen to be the same length on every peril today:
           how long before the figure is final, and how long the protocol
           waits for a figure before giving up and returning the premium. Two
           cards side by side carrying the same digit read as a mistake, so
           they are one card while they agree. Read from the answer, not
           assumed: the day a peril sets them apart, there are two again. */
        var frozen=days(x.freeze_hours), figs=[];
        if(x.deadline_days===frozen)
          figs.push({n:frozen,c:t("days until the figure is final, and the same wait before silence returns the premium")});
        else{
          figs.push({n:frozen,c:t("days until the figure is final")});
          if(x.deadline_days)figs.push({n:x.deadline_days,c:t("days of silence and the premium comes back")});
        }
        if(!common("objection_days"))figs.push({n:x.objection_days,c:t("days to object")});

        return '<div class="panel" id="rule-'+esc(k)+'" style="padding:22px;scroll-margin-top:84px">'+
          '<div class="perilhead"><h2>'+esc(t(x.title))+'</h2><div class="u"><b>'+esc(t("Index"))+'</b>'+esc(ts(x.index))+'</div></div>'+
          '<div class="rulefigs">'+figs.map(function(g){
            return '<div><div class="n">'+esc(f0.format(g.n))+'</div><div class="c">'+esc(g.c)+'</div></div>';
          }).join("")+'</div>'+
          '<div class="kvs rulebook">'+rows(x,false)+'</div>'+
          binding('<div class="kv"><div class="k">Index</div><div class="v">'+esc(x.index)+'</div></div>'+rows(x,true))+
          (common("version")?'':'<p class="fine" style="margin-top:10px">'+esc(t("Rulebook version {v}",{v:x.version}))+'</p>')+
          '</div>';
      }).join("");
    },function(){ box.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("The protocol did not answer."))+'</p></div>'; });
  });
}

/* What a decision is called, in the reader's language. The chain's own word
   for a policy that ran its term without the index reaching the line is
   "lapsed", which is right in a ledger and wrong on a page: it says the policy
   ended, not that nothing happened. */
var DECIDED_PILL={paid:N("Paid"),lapsed:N("Not triggered"),expired:N("No data")};

function decidedReason(row){
  if(row.kind==="paid")
    return t("{n} blocks after the reading",{n:f0.format(row.latency_blocks)});
  if(row.kind==="expired")
    return t("the source went silent before the deadline");
  return row.direction==="below"
    ? t("the figure never fell to the line")
    : t("the figure never reached the line");
}

/* The line the policy was written on, and the figure that met it or did not,
   in the same words and the same formatting the record itself uses: M7.2 for a
   magnitude, 204.8 mm for a season's rainfall. The predicate is the true rule
   and the record prints it in full; a register wants the two numbers it turns
   on. A reading of zero is nothing read when the policy pays on a figure going
   up, and a real reading when it pays on one coming down. */
function decidedRule(row){
  var o={unit:row.unit};
  var nothing=row.measured===null||row.measured===undefined||
    (row.direction!=="below"&&!row.measured);
  return nothing
    ? t("pays at {trigger} · nothing read",{trigger:outcomeValue(o,row.trigger)})
    : t("pays at {trigger} · {value} read",
        {trigger:outcomeValue(o,row.trigger),value:outcomeValue(o,row.measured)});
}

function decidedRow(row){
  var paid=row.kind==="paid", href="#/proof/"+encodeURIComponent(row.policy_id);
  return '<article class="reg">'+
    '<div class="reg-who">'+
      '<a class="reg-id" href="'+href+'">'+esc(row.policy_id)+'</a>'+
      '<span class="pill '+esc(row.kind)+'">'+esc(t(DECIDED_PILL[row.kind]||row.kind))+'</span>'+
    '</div>'+
    '<div class="reg-what">'+
      '<div class="reg-where">'+esc(ts(row.peril_name))+' · '+esc(ts(row.subject_text))+'</div>'+
      '<div class="reg-rule">'+esc(decidedRule(row))+'</div>'+
    '</div>'+
    '<div class="reg-out'+(paid?'':' quiet')+'"><b>'+
      (paid?esc(money(row.amount)):esc(t("Nothing paid")))+'</b>'+
      '<span>'+esc(decidedReason(row))+'</span></div>'+
    '<div class="reg-foot">'+
      '<span class="mono">'+esc(t("block {n}",{n:f0.format(row.block_number)}))+'</span>'+
      '<a class="btn btn-line btn-sm" href="'+href+'">'+
        esc(paid?t("Read the record"):t("Read why not"))+'</a>'+
    '</div>'+
  '</article>';
}

function lookupHtml(){
  return '<div class="lookup">'+
    '<div class="txt"><b>'+esc(t("Or look one up"))+'</b>'+
      '<span>'+esc(t("Any policy id. You do not have to hold it, and you do not have to be signed in: the record is the chain's, not ours."))+'</span></div>'+
    '<div class="go">'+
      '<label class="label" for="proof-id">'+esc(t("Policy id"))+'</label>'+
      '<input id="proof-id" type="text" placeholder="CLS-…" autocomplete="off" spellcheck="false">'+
      '<button class="btn btn-primary btn-sm" type="button" id="proof-go">'+esc(t("Read it"))+'</button>'+
    '</div></div>';
}

function bindLookup(){
  var go=$("proof-go"), field=$("proof-id");
  if(!go||!field)return;
  go.addEventListener("click",function(){
    var value=field.value.trim();
    if(value)location.hash="#/proof/"+encodeURIComponent(value);
  });
  field.addEventListener("keydown",function(e){
    if(e.key==="Enter")go.click();
  });
}

/* ---------------- the three questions ----------------
   Somebody deciding whether to trust an insurer asks three things, in this
   order: is there money to pay me, who decides that it pays, and has it paid
   anyone else. This page used to open with the third and leave the first two
   on other pages, which is the order the protocol finds interesting rather
   than the order a buyer does. Each band answers from the protocol or says it
   could not ask; not one of them is filled with a figure this page made up,
   because a proof page that invents its evidence is the thing it argues
   against. */
function qband(n,question,lead,body){
  var ground = n % 2 ? " full-sunk" : " full-edge";
  return '<section class="qband full full-y'+ground+'">'+
    '<div class="qhead"><span class="qnum" aria-hidden="true">'+esc(String(n))+'</span>'+
      '<h2>'+esc(question)+'</h2></div>'+
    '<p class="qlead">'+esc(lead)+'</p>'+
    '<div class="qbody">'+body+'</div></section>';
}

/* How many put capital behind the book. The pool's own summary carries a
   count under this name, but the endpoint replaces it with the full list of
   providers, so the field arrives as an array here and as a number elsewhere.
   Counting the ones still holding shares is the honest answer either way: a
   provider who has taken everything back out is not standing behind anything. */
function backers(pool){
  var p=pool&&pool.providers;
  if(Array.isArray(p))
    return p.filter(function(one){ return (one&&one.shares||0)>0; }).length;
  return p||0;
}

function qmoney(pool){
  var question=t("Is there money to pay you?"),
      lead=t("A promise to pay is worth what stands behind it, which is why this is the first question here and not the last one.");
  if(!pool)
    return qband(1,question,lead,
      '<p class="fine">'+esc(t("This page could not reach the pool, so it will not tell you what is in it."))+'</p>');
  var required=pool.required_capital||0,
      own=pool.own_funds!=null?pool.own_funds:pool.balance||0,
      ratio=pool.own_funds_ratio!=null?pool.own_funds_ratio:pool.solvency_ratio,
      holds=ratio===null||ratio===undefined||ratio>=1;
  return qband(1,question,lead,
    '<div class="ratio"><b>'+(ratio==null?"–":esc(f2.format(ratio))+"×")+'</b>'+
      '<span>'+esc(t("the capital a 99.5% standard asks of the book already written"))+'</span></div>'+
    '<div class="verdict '+(holds?"ok":"no")+'"><p>'+esc(holds
      ? t("The money is in the pool before the event, not raised after it. While this stays above one the pool may keep writing.")
      : t("Under one the pool stops writing: the next policy asked for is refused until capital is added, and this page says so rather than selling you one."))+'</p></div>'+
    '<div class="figures">'+
      '<div><b>'+esc(money(own))+'</b><span>'+esc(t("own funds in the pool, USDC"))+'</span></div>'+
      '<div><b>'+esc(money(required))+'</b><span>'+esc(t("capital the standard requires"))+'</span></div>'+
      '<div><b>'+esc(money(pool.limit_at_risk||0))+'</b><span>'+esc(t("promised and still open"))+'</span></div>'+
      '<div><b>'+esc(f0.format(backers(pool)))+'</b><span>'+esc(t("who put that capital there"))+'</span></div>'+
    '</div>'+
    '<p class="fine">'+esc(t("Own funds and not the balance: premium taken for cover that has not run yet is owed to that cover, and cannot also be the capital that makes the next sale safe. The pool's own page has the layers, the ledger and every deposit."))+
      ' <a href="#/pool">'+esc(t("Open the pool"))+'</a></p>');
}

function qdecides(cov){
  var question=t("Who decides that it pays?"),
      lead=t("Not us. The figure comes from instruments this protocol does not own, and the paper is a supervised company's.");
  var registry=(cov&&cov.__registry)||{}, rule=cov&&cov.__aggregation, body="";
  if(rule)
    body+='<div class="panel" style="padding:18px 20px">'+
      '<div class="label">'+esc(t("The reading, by the rule written into the policy"))+'</div>'+
      /* The protocol's own sentence, and it decides settlement, so it is
         translated and the binding English stays one click away. Printed raw
         here for as long as this band has existed: a Turkish reader got this
         heading in Turkish and the rule under it in English, on the one page
         whose whole job is to be worth trusting. */
      '<p style="margin-top:8px;font-size:14.5px;line-height:1.6">'+tsHtml(rule)+'</p>'+
      '<p class="fine" style="margin-top:9px">'+esc(t("Refused, not guessed. When the sources disagree by more than the tolerance, that round writes nothing and the next one is taken."))+'</p></div>';
  else
    body+='<p class="fine">'+esc(t("This page could not reach the protocol, so it cannot show you the rule it aggregates by."))+'</p>';
  if(registry.active)
    body+='<div class="figures">'+
      '<div><b>'+esc(f0.format(registry.carriers||0))+'</b><span>'+esc(t("licensed companies carrying the risk"))+'</span></div>'+
      '<div><b>'+esc(f0.format(registry.reinsurers||0))+'</b><span>'+esc(t("reinsurers standing behind them"))+'</span></div>'+
      '<div><b>'+esc(f0.format(registry.countries||0))+'</b><span>'+esc(t("countries their licences cover"))+'</span></div>'+
      '<div><b>'+esc(money(registry.capacity||0))+'</b><span>'+esc(t("capacity left on those licences"))+'</span></div>'+
    '</div>';
  else if(registry.companies!==undefined)
    /* An empty register is a fact about the protocol, not a gap in the page.
       Saying nothing here would let the paragraph below imply a company that
       is not there. */
    body+='<p class="fine">'+esc(t("No company is active in the register yet, so this page has none to name."))+'</p>';
  body+='<p class="fine">'+esc(t("A company cannot register itself into this. It arrives able to write nothing, and somebody checks its licence number against the regulator's own register before it may carry a single policy. That is the one step here which is deliberately a person's, because no block can read a regulator's register. Your policy names the company on it."))+'</p>'+
    '<p class="fine"><a href="#/rules">'+esc(t("Where cover may be written"))+'</a> · <a href="#/how">'+esc(t("How it works"))+'</a></p>';
  return qband(2,question,lead,body);
}

function qpaid(rows,book){
  var question=t("Has it paid anyone else?"),
      lead=t("Both halves are here. A policy that ran its term without the index ever reaching the line is the harder promise to keep, and hiding it would make this page an advertisement.");
  return qband(3,question,lead,
    '<div class="figures">'+
      '<div><b>'+esc(f0.format(book.policies||0))+'</b><span>'+esc(t("policies in the book"))+'</span></div>'+
      '<div><b>'+esc(f0.format(book.evaluated||0))+'</b><span>'+esc(t("conditions evaluated"))+'</span></div>'+
      '<div><b>'+esc(f0.format(book.paid||0))+'</b><span>'+esc(t("paid without a claim"))+'</span></div>'+
      '<div><b>'+esc(f0.format(book.height||0))+'</b><span>'+esc(t("the chain's current block"))+'</span></div>'+
    '</div>'+
    sieveHtml(book)+
    '<p class="fine" style="margin:-6px 2px 14px">'+
      esc(t("The most recent {n}. The figure on each button counts all of them, and nothing caps it.",
            {n:f0.format(REGISTER_LIMIT)}))+'</p>'+
    '<div id="register-out">'+registerHtml(rows,book)+'</div>'+
    lookupHtml());
}

/* Which half of the register to read.
   The last twelve decisions of any kind are, in a book where most policies run
   their term quietly, twelve quiet ones -- so a reader looking for a payment
   found none, on a page whose own figures said thousands had been made. The
   counts are on the buttons because a filter that hides how large the other
   half is would be the advertisement this page exists not to be. */
/* How many of each kind the register shows. It is a window on purpose and says
   so: nobody needs the whole book to see that the protocol decides, and a page
   that looked like an archive while being a window was the thing that made the
   count beside it read as a contradiction. The count is the count -- every
   decision this protocol has made, uncapped -- and this is the last ten of them. */
var REGISTER_LIMIT=10;
var SIEVE=[{kind:"",label:N("Every decision"),count:"evaluated"},
           {kind:"paid",label:N("Paid"),count:"paid"},
           {kind:"lapsed",label:N("Not triggered"),count:"lapsed"},
           {kind:"expired",label:N("No data"),count:"expired"}];
var sieveNow="";
function sieveHtml(book){
  return '<div class="sieve" role="group" aria-label="'+esc(t("Which decisions to show"))+'">'+
    SIEVE.map(function(one){
      var n=book?book[one.count]:null;
      return '<button type="button" class="sv'+(one.kind===sieveNow?" on":"")+'" '+
        'data-sieve="'+esc(one.kind)+'" aria-pressed="'+(one.kind===sieveNow?"true":"false")+'">'+
        esc(t(one.label))+
        (n===null||n===undefined?"":'<span class="n">'+esc(f0.format(n))+'</span>')+
        '</button>';
    }).join("")+'</div>';
}
/* How many decisions of the kind now being read the book says there are. The
   buttons carry the same figures; "" is every decision, and the book calls that
   one evaluated. */
function countedNow(book){
  return book?Number(book[sieveNow||"evaluated"]||0):0;
}

function registerHtml(rows,book){
  var counted=countedNow(book);
  if(rows.length)return '<div class="register">'+rows.map(decidedRow).join("")+'</div>';
  /* Empty does not always mean none. A tally outlives the record it counted:
     this is a demonstration and it forgets its own old policies, so a filter
     can come back with nothing while the button beside it says thousands. The
     page said "no decision of this kind has been made yet" in that case, next
     to a count of 2,974, which is a page contradicting itself on the one
     subject it exists to be trusted about. */
  var why=!sieveNow
    ? t("Nothing has been decided yet. The first policy to reach its line will appear here.")
    : counted>0
      ? t("{n} of these have been decided, and none of their records are still here. This is a demonstration and it forgets its own old policies; the count outlives the record. Any one of them still answers to its id below.",{n:f0.format(counted)})
      : t("No decision of this kind has been made yet.");
  return '<div class="panel" style="padding:22px"><p>'+esc(why)+'</p></div>';
}
/* Bound by delegation, on the box rather than on the buttons: the register is
   redrawn on every choice, and a handler attached to a button that has been
   replaced is a handler on nothing. */
function bindSieve(box){
  if(!box||box.dataset.sieveBound)return;
  box.dataset.sieveBound="1";
  box.addEventListener("click",function(event){
    var button=event.target.closest?event.target.closest("[data-sieve]"):null;
    if(!button||!box.contains(button))return;
    var want=button.dataset.sieve||"";
    if(want===sieveNow)return;
    sieveNow=want;
    Array.prototype.forEach.call(box.querySelectorAll("[data-sieve]"),function(b){
      var on=(b.dataset.sieve||"")===sieveNow;
      b.classList.toggle("on",on);
      b.setAttribute("aria-pressed",on?"true":"false");
    });
    var out=box.querySelector("#register-out");
    if(out)out.innerHTML='<p class="fine" style="padding:14px 2px">'+esc(t("Reading the chain…"))+'</p>';
    api("/api/decided?limit="+REGISTER_LIMIT+(sieveNow?"&kind="+encodeURIComponent(sieveNow):""),
        {timeout:9000}).then(function(reply){
      if(!out)return;
      out.innerHTML=registerHtml((reply&&reply.items)||[],(reply&&reply.book)||null);
    },function(){
      if(out)out.innerHTML='<div class="panel" style="padding:22px"><p>'+
        esc(t("The protocol did not answer."))+'</p></div>';
    });
  });
}

function renderProof(id){
  var box=$("proof-out");
  if($("proof-intro-book"))$("proof-intro-book").hidden=!!id;
  if($("proof-intro-one"))$("proof-intro-one").hidden=!id;
  if(!id){
    /* Open with the work. The lookup still exists, inside the third band, for
       somebody who arrived holding an id; it is no longer the only way in. */
    box.className="proof-open";
    box.innerHTML='<p class="fine">'+esc(t("Reading the chain…"))+'</p>';
    /* Three requests, one paint. A band whose request failed says so in its
       own place rather than taking the other two down with it, which is why
       the two that are not the register swallow their own error. */
    Promise.all([
      api("/api/decided?limit="+REGISTER_LIMIT,{timeout:9000}),
      api("/api/pool",{timeout:9000}).then(null,function(){return null;}),
      loadCoverage().then(null,function(){return null;})
    ]).then(function(got){
      var reply=got[0]||{}, rows=reply.items||[], book=reply.book||{};
      box.innerHTML=qmoney(got[1])+qdecides(got[2])+qpaid(rows,book);
      bindLookup();
      bindSieve(box);
      /* The witness on the public chain belongs to the third question, not
         below all three: it is the part of "has it paid anyone" that somebody
         else can check. Into that band's body, or the box if the band is not
         there to hold it. */
      whenLinked().then(function(){
        if(!link.live)return;
        var bands=box.querySelectorAll(".qband .qbody");
        renderAnchorStatus(bands.length?bands[bands.length-1]:box);
      });
    },function(){
      /* No protocol to reach: the page still lets somebody with an id ask. It
         will not invent a register to fill the space. */
      box.innerHTML='<div class="panel" style="padding:22px"><p>'+esc(t("This page cannot reach the protocol, so there is no record to read. It will not show you one it made up."))+'</p></div>'+lookupHtml();
      bindLookup();
    });
    return;
  }
  box.className="";
  box.innerHTML='<div class="panel" style="padding:24px">'+esc(t("Reading the chain…"))+'</div>';
  whenLinked().then(function(){
    if(!link.live){
      box.innerHTML='<div class="panel" style="padding:26px"><p>'+esc(t("This page cannot reach the protocol, so there is no record to read. It will not show you one it made up."))+'</p></div>';
      return;
    }
    return api("/api/lineage/"+encodeURIComponent(id)).then(function(story){
      box.innerHTML=proofHtml(story); bindTokens(box); renderAnchorFor(id,box);
    },function(error){
      box.innerHTML='<div class="panel" style="padding:26px"><p>'+
        esc(error&&error.status===404?t("No policy with that id."):t("The protocol did not answer."))+
        '</p></div>';
    });
  });
}

/* A reading is a measurement, not a float. Printing fourteen decimals of a
   rainfall total suggests a precision the instrument does not have, and it is
   the kind of thing that makes a person stop believing the rest of the page. */
function reading(value){
  if(value===null||value===undefined)return "–";
  var number=Number(value);
  if(!isFinite(number))return esc(String(value));
  if(Math.abs(number-Math.round(number))<1e-9)return f0.format(number);
  return f2.format(number);
}

var AGREEMENT={agreed:N("agreed"),disputed:N("disputed"),no_quorum:N("no quorum")};

/* Why this policy did or did not pay, in one plain sentence and a status a
   reader can trust at a glance. Every outcome is explained, not only the
   payments: the complaints about parametric cover come from the ones that did
   not pay, and "the reading was 5.8 and your cover needed 6.0" is an answer. */
function bindTokens(root){
  Array.prototype.forEach.call(root.querySelectorAll("[data-token]"),function(b){
    b.addEventListener("click",function(){ showToken(b.dataset.token); });
  });
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
/* Whose wallet holds the token on the public chain, and the holder's way to
   make it their own: a wallet they linked on their profile, proved by its
   signature. The token cannot move, so "to my wallet" is a burn and a new
   mint, in that order; the page says so rather than pretending otherwise. */
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
function outcomeValue(o,v){
  if(v===null||v===undefined)return "–";
  var num=Number(v);
  if(/MMI/.test(o.unit||"")) return (ROMAN[Math.round(num)]||f1.format(num))+" ("+f1.format(num)+")";
  return /magnitude/.test(o.unit||"")?"M"+f1.format(num):f1.format(num)+" "+t(o.unit||"");
}
function outcomeHtml(story){
  var o=story.outcome; if(!o)return "";
  var status=story.status, pill="", sentence="";
  var trigger=outcomeValue(o,o.trigger), measured=outcomeValue(o,o.measured);
  if(story.provisional){
    pill='<span class="pill">'+esc(t("Provisional"))+'</span>';
    sentence=t("The index reached {value} at block {since}. It pays at block {final}, once the window for corrections by the sources has passed; the final figure is the one that pays.",
      {value:outcomeValue(o,story.provisional.index),since:f0.format(story.provisional.since_block),final:f0.format(story.provisional.final_block)});
  } else if(status==="paid"){
    pill='<span class="pill ok">'+esc(t("Verified"))+'</span>';
    sentence=t("Paid. The final reading was {value}; this policy starts paying at {trigger}.",{value:measured,trigger:trigger});
  } else if(status==="expired"){
    pill='<span class="pill no">'+esc(t("Source silent"))+'</span>';
    sentence=t("No source published a reading before the deadline, so the premium was returned in full. No reading is not the same as no event.");
  } else if(status==="lapsed"){
    pill='<span class="pill">'+esc(t("Ended"))+'</span>';
    sentence=o.measured===null||!o.measured
      ? t("The term ended without a reading reaching the trigger of {trigger}.",{trigger:trigger})
      : t("The term ended. The highest reading was {value}; this policy needed {trigger} to pay.",{value:measured,trigger:trigger});
  } else {
    pill='<span class="pill">'+esc(t("Waiting"))+'</span>';
    sentence=o.measured===null||o.measured===0
      ? t("Nothing has been recorded yet. It pays when the reading reaches {trigger}.",{trigger:trigger})
      : t("The highest reading so far is {value}. It pays when the reading reaches {trigger}.",{value:measured,trigger:trigger});
  }
  var extra=o.withdrawn?'<p class="fine">'+esc(t("A reading reached the trigger earlier and was then revised by the sources to {value}, so the policy went back to waiting.",{value:outcomeValue(o,o.withdrawn.index)}))+'</p>':'';
  var steps=(o.steps||[]).map(function(b){ return outcomeValue(o,b.level)+" → "+pct(b.share,0); }).join(" · ");
  return '<div class="verdict" style="margin-top:18px"><div class="vrow">'+pill+'<span>'+esc(t("What happened"))+'</span></div>'+
    '<p>'+esc(sentence)+'</p>'+extra+'<p class="fine">'+esc(t("Pays in steps: {steps}",{steps:steps}))+'</p></div>';
}

function proofHtml(story){
  var sub=story.subscription||{},source=story.source||{};
  var out='<div class="holding">'+
    '<div class="hrow"><span>'+esc(t("Policy"))+'</span><b class="mono">'+esc(story.policy_id)+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Status"))+'</span><b>'+esc(t(POLICY_STATUS[story.status]||story.status))+'</b></div>'+
    (sub.account
      ? '<div class="hrow"><span>'+esc(t("Subscription"))+'</span><b class="mono">'+esc(sub.account)+'</b></div>'+
        '<div class="hrow"><span>'+esc(t("Registered"))+'</span><b>'+esc(t("block {n}",{n:f0.format(sub.registered_block||0)}))+'</b></div>'
      : '<div class="hrow"><span>'+esc(t("Subscription"))+'</span><b>'+esc(t("closed when the policy settled"))+'</b></div>')+
    '<div class="hrow"><span>'+esc(t("Kind"))+'</span><b>'+esc(sub.kind||"OneShot")+'</b></div>'+
    '<div class="hrow"><span>'+esc(t("Policy token"))+'</span><b><button class="linkish" type="button" data-token="'+esc(story.policy_id)+'">'+esc(t("Non-transferable, show it"))+'</button></b></div>'+
    '</div>';
  out+=outcomeHtml(story);

  out+='<div style="margin-top:22px"><div class="label" style="margin-bottom:7px">'+
       esc(t("The topic it listens to"))+'</div><div class="code mono">'+esc(sub.topic||"—")+'</div></div>';
  out+='<div style="margin-top:18px"><div class="label" style="margin-bottom:7px">'+
       esc(t("What has to be true"))+'</div><div class="code">'+esc(sub.predicate||"—")+'</div></div>';

  // Three pieces from three places, two of them fragments and one a whole
  // sentence. Joined with a bare space they ran together: "taken at window
  // close If the station publishes no closing total". Each part is closed
  // before the next one starts, and an absent part leaves no stray stop.
  var sourceParts=[source.publisher,source.resolution,source.on_missing_data]
    .map(function(part){ return ts(part||"").trim(); })
    .filter(Boolean)
    .map(function(part){ return /[.!?…]$/.test(part) ? part : part+"."; });
  out+='<div style="margin-top:18px"><div class="label" style="margin-bottom:7px">'+esc(t("The source"))+'</div>'+
       '<p style="font-size:13.5px;color:var(--ink-2)">'+esc(sourceParts.join(" "))+'</p></div>';

  out+='<div style="margin-top:26px"><div class="label" style="margin-bottom:9px">'+
       esc(t("Every round of validator reports"))+'</div>'+
       '<p style="font-size:13.5px;color:var(--ink-2);margin-bottom:12px">'+esc(ts(story.rule||LOCAL_RULE))+
       (story.refused?' <b>'+esc(story.refused===1
         ? t("1 round was refused rather than aggregated.")
         : t("{n} rounds were refused rather than aggregated.",{n:f0.format(story.refused)}))+'</b>':'')+'</p>';

  var rounds=story.rex_rounds||[];
  out+='<p class="fine" style="margin:6px 0 12px">'+esc(t("Each validator reads three independent official sources and keeps their median; the settled figure is the median of the validators. Every value is listed below, so you can recompute it yourself."))+'</p>';
  if(!rounds.length){
    out+='<p style="font-size:13.5px;color:var(--ink-3)">'+esc(t("No reading has been published on this topic yet."))+'</p>';
  } else {
    out+='<div class="tbl-wrap"><table><tbody>'+
      '<tr><th>'+esc(t("Round"))+'</th><th>'+esc(t("Field"))+'</th><th>'+esc(t("Reported"))+'</th><th>'+esc(t("Settled at"))+'</th>'+
      '<th>'+esc(t("Spread"))+'</th><th>'+esc(t("Verdict"))+'</th></tr>';
    rounds.forEach(function(round){
      out+='<tr><td class="mono">'+f0.format(round.round)+'</td>'+
        '<td class="mono">'+esc(round.field||"")+'</td>'+
        '<td>'+esc(t("{n} of {m}",{n:f0.format(round.reported),m:f0.format(round.expected)}))+'</td>'+
        '<td>'+reading(round.median)+'</td>'+
        '<td>'+(round.dispersion===null||round.dispersion===undefined?"–":pct(round.dispersion,2))+'</td>'+
        '<td><span class="pill '+(round.settles?"ok":"no")+'">'+esc(t(AGREEMENT[round.agreement]||round.agreement))+'</span></td></tr>';
      if(!round.settles&&round.note)
        out+='<tr><td colspan="6" style="color:var(--ink-3);font-size:12.5px">'+tsHtml(round.note)+'</td></tr>';
      if(round.updates&&round.updates.length)
        out+='<tr><td colspan="6" class="mono" style="font-size:11.5px;color:var(--ink-3)">'+
          round.updates.map(function(update){
            var src=(update.sources||[]).map(function(x){
              return esc(ts(x.source))+" "+(x.value===null||x.value===undefined?esc(t("no answer")):reading(x.value));
            }).join(", ");
            return esc(update.validator)+" "+reading(update.value)+(src?" ("+src+")":"")+" ["+esc(update.authority_key)+"]";
          }).join("<br>")+'</td></tr>';
    });
    out+='</tbody></table></div>';
  }
  out+='</div>';

  var settlements=story.settlements||[];
  out+='<div style="margin-top:26px"><div class="label" style="margin-bottom:9px">'+esc(t("Settlement"))+'</div>';
  if(!settlements.length){
    out+='<p style="font-size:13.5px;color:var(--ink-2)">'+esc(t("Nothing has settled. The subscription is still listening, or the term ended without the trigger being crossed."))+'</p>';
  } else {
    settlements.forEach(function(item){
      out+='<div class="policy-card" style="margin-bottom:12px"><div class="bar">'+
        '<span class="lamp"></span><span class="label">'+esc(ts(item.kind))+'</span>'+
        '<span class="right label mono">'+esc(item.signature)+'</span></div>'+
        '<div class="body"><div class="kvs">'+
        kv(t("Amount"),money(item.amount)+' USDC')+
        kv(t("Block"),f0.format(item.block_number),"mono")+
        kv(t("Reading"),reading(item.index_value))+
        kv(t("Blocks after the reading"),f0.format(item.latency_blocks||0))+'</div>'+
        '<p style="font-size:13.5px;color:var(--ink-2)">'+tsHtml(item.summary||"")+'</p>'+
        '</div></div>';
    });
  }
  out+='</div>';

  out+='<p style="margin-top:22px;font-size:12.5px;color:var(--ink-3)">'+esc(t("You can assemble all of this yourself without this page, through get_subscription, get_triggered_transactions and get_workflow_lineage. That is the point of showing it: not to be believed, but to be checked."))+'</p>';
  return out;
}

