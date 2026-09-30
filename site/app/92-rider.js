/* ================= Rider =================
   The one part of this page that reasons. It reads, prices and explains, and it
   cannot spend: every movement of value in this protocol is authorised by a
   signature made on the buyer's own device, and that is as true for a policy
   Rider assembled as for one somebody typed themselves.

   Nothing said to it is stored anywhere. The transcript lives in this tab and
   goes with the request; the protocol keeps none of it. */

var rider = {open:false, busy:false, ready:null, turns:[]};

function riderState(){
  if(rider.ready)return Promise.resolve(rider.ready);
  return api("/api/rider",{timeout:8000}).then(function(reply){
    rider.ready=reply; return reply;
  },function(){
    rider.ready={available:false, authority:
      N("This page cannot reach the protocol, so Rider is not here either.")};
    return rider.ready;
  });
}

function riderSay(role, text, extra){
  rider.turns.push({role:role, content:text});
  renderThread(extra);
}

function renderThread(extra){
  var thread=$("rider-thread");
  thread.innerHTML=rider.turns.map(function(turn){
    return '<div class="msg '+(turn.role==="user"?"me":"it")+'">'+
      esc(turn.content).replace(/\n\n/g,"<br><br>").replace(/\n/g,"<br>")+'</div>';
  }).join("")+(extra||"");
  thread.scrollTop=thread.scrollHeight;
}

function openRider(){
  rider.open=true;
  $("rider").hidden=false;
  $("rider-open").hidden=true;
  $("rider-input").focus();

  riderState().then(function(state){
    $("rider-tag").textContent=state.available
      ? (state.constrained?t("latched, cannot spend"):t("reads and prices, cannot spend"))
      : t("not configured here");
    $("rider-foot").textContent=ts(state.authority||"");
    if(!rider.turns.length){
      if(state.available){
        renderThread('<div class="msg note">'+esc(t("Rider prices cover from the same "+
          "engine the protocol uses, and cannot buy anything: it prepares, you "+
          "sign. Ask it what a policy would cost, what it would not pay for, or "+
          "why one settled the way it did."))+'</div>');
      } else {
        renderThread('<div class="msg note">'+esc(ts(state.authority||""))+
          '</div>');
      }
    }
  });
}

function closeRider(){
  rider.open=false;
  $("rider").hidden=true;
  $("rider-open").hidden=false;
}

/* ---------------- readings behind the hero ---------------- */
(function(){
  // One policy, all the way through, moved by the reader rather than by a
  // timer. Whichever step is crossing the middle of the window owns the
  // picture, and every layer below it stays drawn: the rule does not stop
  // existing when the ground moves, and the reading does not stop existing
  // when the money lands. Nothing here runs on an interval, so there is
  // nothing to drift, nothing burning a background tab, and nothing at all
  // for a browser that asked for less motion beyond choosing the step.
  (function(){
    var stage=$("hero-stage"), cap=$("hero-cap");
    if(!stage)return;

    // Both drawings draw their trace by unrolling a dash the length of the
    // path. The upright one was left on the 1100 fallback, which is longer
    // than it is, so the line finished early and then waited.
    [].slice.call(document.querySelectorAll(".hx-trace")).forEach(function(trace){
      if(!trace.getTotalLength)return;
      try{ trace.style.setProperty("--len",String(Math.ceil(trace.getTotalLength()))); }catch(e){}
    });

    var beats=[].slice.call(document.querySelectorAll("#hero-beats .beat"));
    var ticks=[].slice.call(stage.querySelectorAll(".ticks i"));
    var CAPS={1:N("CLS-7F42 · written"),2:N("M7.2 · 09:41:04"),3:N("3 of 4 attested"),
              4:N("evaluate → true"),5:N("25,000 · block 412,388")};
    var at=1;

    function paintCap(){ if(cap)cap.textContent=t(CAPS[at]||CAPS[1]); }
    LANG_LISTENERS.push(paintCap);

    function show(n){
      if(n===at)return;
      at=n;
      stage.dataset.beat=String(n);
      for(var i=1;i<=5;i++)stage.classList.toggle("on-"+i,i<=n);
      ticks.forEach(function(tick,i){ tick.classList.toggle("lit",i<n); });
      paintCap();
      beats.forEach(function(b){ b.dataset.live=Number(b.dataset.beat)===n?"on":"off"; });
    }

    if(!beats.length)return;

    /* Wide enough for the steps to be a row rather than a stack, and then the
       reader is not moving through them one at a time -- all five are on the
       screen at once, so "whichever one is crossing the middle" picks whatever
       it likes and the picture jumps. One run instead: the instrument plays the
       policy through once when it arrives, from written to paid, and then
       stays at the whole picture. It plays once and never again, so there is
       still nothing on an interval and nothing burning a background tab. */
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");

    /* Beside the steps, the reading follows how far through them the reader is.
       "Whichever step is crossing the middle of the window" is the right rule
       when the steps are a page tall each; here the five of them are 875px on a
       1400px screen, so the middle of the window is past the last one before
       the second has been read and the instrument jumps to the end and stays
       there -- measured, at 2560 by 1400. Distance through the block is the
       thing that actually tracks the reading, so that is what moves it. */
    var pinned = window.matchMedia && window.matchMedia("(min-width:1300px)");
    if(pinned && pinned.matches){
      if(still && still.matches){
        show(5);
        beats.forEach(function(b){ b.dataset.live = "on"; });
        return;
      }
      var box = $("hero-beats"), waiting = false;
      var follow = function(){
        waiting = false;
        if(!box)return;
        var r = box.getBoundingClientRect();
        // Where the reader is inside the block, from its top edge reaching the
        // middle of the window to its bottom edge doing the same.
        var through = (window.innerHeight * 0.55 - r.top) / Math.max(1, r.height);
        var n = Math.min(5, Math.max(1, Math.ceil(through * 5)));
        if(n !== at){
          show(n);
          beats.forEach(function(b){
            b.dataset.live = Number(b.dataset.beat) === n ? "on" : "off";
          });
        }
      };
      var onScroll = function(){
        if(waiting)return;
        waiting = true;
        (window.requestAnimationFrame || setTimeout)(follow, 16);
      };
      window.addEventListener("scroll", onScroll, {passive:true});
      window.addEventListener("resize", onScroll, {passive:true});
      follow();
      return;
    }


    if(!("IntersectionObserver" in window)){
      // No observer: show the whole picture rather than the first fifth of it.
      at=0; show(5);
      beats.forEach(function(b){ b.dataset.live="on"; });
      return;
    }
    var live=[];
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(e){ live[Number(e.target.dataset.beat)]=e.isIntersecting; });
      for(var n=5;n>=1;n--)if(live[n]){ show(n); return; }
    },{rootMargin:"-48% 0px -48% 0px",threshold:0});
    beats.forEach(function(b){ io.observe(b); });
  })();
  var canvas=$("hero-fx"); if(!canvas||!canvas.getContext)return;
  if(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches){ canvas.remove(); return; }
  var ctx=canvas.getContext("2d"), hero=canvas.parentNode, swarms=[], w=0, h=0, dpr=1, last=0, nextAt=0, seen=true, pointer=null, pointerAt=0;
  var narrow=function(){ return w<760; };
  function colours(){
    var cs=getComputedStyle(document.documentElement);
    return [cs.getPropertyValue("--signal").trim()||"#E66700", cs.getPropertyValue("--settled").trim()||"#24D3A5", cs.getPropertyValue("--ink-3").trim()||"#5B6875"];
  }
  var palette=colours();
  new MutationObserver(function(){ palette=colours(); }).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
  function size(){
    var r=hero.getBoundingClientRect(); w=Math.max(1,Math.round(r.width)); h=Math.max(1,Math.round(r.height));
    dpr=Math.min(2,window.devicePixelRatio||1); canvas.width=w*dpr; canvas.height=h*dpr; ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  function spawn(x,y,strong){
    if(swarms.length>=(narrow()?8:14))return;
    var bars=Math.random()<0.45, life=3200+Math.random()*2200;
    swarms.push({x:x,y:y,bars:bars,born:performance.now(),life:life,
      cols:bars?10+Math.floor(Math.random()*12):5+Math.floor(Math.random()*5),
      rows:bars?1:3+Math.floor(Math.random()*4),
      cell:bars?4:5, tall:bars?14+Math.random()*26:0,
      colour:palette[Math.floor(Math.random()*palette.length)],
      phase:Math.random()*Math.PI*2, drift:(Math.random()-.5)*6, rise:4+Math.random()*10,
      seed:Math.random()*1000, alpha:strong?.95:.75});
  }
  function place(){
    // Mostly off the text: the right two thirds on a wide screen, anywhere
    // when the hero is a single column.
    var x=narrow()?Math.random()*w:w*(0.42+Math.random()*0.58), y=h*(0.08+Math.random()*0.84);
    spawn(x,y,false);
  }
  var frame=0;
  function draw(now){
    if(!seen||document.hidden||hero.offsetParent===null){ last=now; requestAnimationFrame(draw); return; }
    // Sized when first seen, and again if the hero changes shape: at load
    // the home view may not be shown yet and would measure as nothing.
    if(frame++%30===0){ var r=hero.getBoundingClientRect(); if(Math.round(r.width)!==w||Math.round(r.height)!==h)size(); }
    if(now>=nextAt){ place(); nextAt=now+(narrow()?1400:750)+Math.random()*700; }
    if(pointer&&now-pointerAt<80&&Math.random()<0.5){ spawn(pointer.x+(Math.random()-.5)*90,pointer.y+(Math.random()-.5)*60,true); pointerAt=0; }
    ctx.clearRect(0,0,w,h);
    for(var i=swarms.length-1;i>=0;i--){
      var s=swarms[i], t=(now-s.born)/s.life;
      if(t>=1){ swarms.splice(i,1); continue; }
      var env=Math.sin(Math.PI*t), ox=s.x+s.drift*t*10, oy=s.y-s.rise*t;
      ctx.fillStyle=s.colour;
      if(s.bars){
        for(var c=0;c<s.cols;c++){
          var k=Math.sin(s.phase+c*0.55+t*6)*0.5+0.5, hh=2+s.tall*k*env;
          ctx.globalAlpha=s.alpha*env*(0.35+0.65*k);
          ctx.fillRect(ox+c*s.cell,oy-hh/2,1.6,hh);
        }
      }else{
        for(var r=0;r<s.rows;r++)for(var c2=0;c2<s.cols;c2++){
          var n=Math.sin(s.seed+r*1.7+c2*2.3+t*5)*0.5+0.5;
          if(n<0.35)continue;
          ctx.globalAlpha=s.alpha*env*n;
          ctx.fillRect(ox+c2*s.cell,oy+r*s.cell,2,2);
        }
      }
    }
    ctx.globalAlpha=1; last=now;
    requestAnimationFrame(draw);
  }
  size(); window.addEventListener("resize",size);
  if("IntersectionObserver" in window)new IntersectionObserver(function(es){ seen=es[0].isIntersecting; }).observe(hero);
  hero.addEventListener("pointermove",function(e){ var r=hero.getBoundingClientRect(); pointer={x:e.clientX-r.left,y:e.clientY-r.top}; pointerAt=performance.now(); },{passive:true});
  // Rider thinking or hovered: the readings come faster, as if it were reading them.
  var rider=$("rider"), fab=$("rider-open");
  if(fab)fab.addEventListener("pointerenter",function(){ for(var i=0;i<3;i++)spawn(w*(0.7+Math.random()*0.3),h*(0.5+Math.random()*0.5),true); });
  if(rider)new MutationObserver(function(){ if(rider.classList.contains("thinking"))nextAt=0; }).observe(rider,{attributes:true,attributeFilter:["class"]});
  requestAnimationFrame(draw);
})();
(function(){
  // Twenty eight bars, a wave running through them: each starts a little
  // later than the one before, so the crest travels right to left.
  var wave=$("rider-wave"); if(!wave)return;
  var bars="";
  for(var i=0;i<24;i++)bars+='<i style="left:'+(i*4)+'px;animation-delay:'+(-(i*0.11)).toFixed(2)+'s"></i>';
  wave.innerHTML=bars;
})();
function askRider(question){
  if(rider.busy||!question)return;
  rider.busy=true;
  $("rider").classList.add("thinking");
  $("rider-send").disabled=true;
  riderSay("user", question);
  renderThread('<div class="msg it">…</div>');

  api("/api/rider",{method:"POST",timeout:120000,body:{
    messages:rider.turns.slice(-24).map(function(turn){
      return {role:turn.role, content:turn.content};
    }),
    lang:LANG,
    // Only this browser holds it; the model never sees it.
    mandate_token:mandateToken()||undefined,
  }}).then(function(reply){
    rider.busy=false; $("rider-send").disabled=false; $("rider").classList.remove("thinking");
    if(reply.bought&&currentRoute()==="/mine")renderMine();
    var used=(reply.tools||[]).map(function(tool){return tool.name;});
    riderSay("assistant", reply.text||t("I could not answer that."));
    if(used.length){
      renderThread('<div class="used">'+esc(t("asked the protocol: {tools}",{tools:used.join(", ")}))+'</div>');
    }
  },function(error){
    rider.busy=false; $("rider-send").disabled=false; $("rider").classList.remove("thinking");
    var detail=(error&&error.payload&&error.payload.detail)||
      t("Rider could not answer just now.");
    riderSay("assistant", ts(String(detail)));
  });
}

$("rider-open").addEventListener("click",openRider);
$("rider-close").addEventListener("click",closeRider);
$("rider-form").addEventListener("submit",function(e){
  e.preventDefault();
  var input=$("rider-input"), question=input.value.trim();
  input.value="";
  askRider(question);
});
addEventListener("keydown",function(e){
  if(e.key==="Escape"&&rider.open)closeRider();
});


