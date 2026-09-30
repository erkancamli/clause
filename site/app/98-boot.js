/* ================= boot =================
   Three things, in this order, and none of them block the page: find out whether
   the protocol is reachable and say so at the top; pick up a key this device
   already made, so a returning buyer is recognised without signing in again;
   and load the place index, falling back to the copy compiled into this page. */
renderStep();
show(currentRoute());
fillCapBars();

// A language change redraws what is on screen from the same state, so a
// half finished purchase survives someone switching to read it in English.
onLang(function(){
  // Everything drawn from a template is drawn again in the new language,
  // including the bar that says whether the protocol is reachable.
  if(link.checked)setLink(link.live, link.note);
  renderWho();
  renderStep();
  show(currentRoute());
  fillCapBars();
  renderLive();
});
startLive();

$("place").addEventListener("input",function(e){renderResults(e.target.value);});

/* ---------------- noticing that the page has been replaced ----------------
   A single page application is downloaded once. After that a person moves
   around it by changing the part of the address after the hash, which never
   fetches the document again, so a tab opened on Monday is still running
   Monday's page on Friday however correct the cache headers are. Telling
   people to press ctrl+shift+R is not a plan; the page has to notice.

   Noticing is the easy half. The hard half is choosing when to act on it,
   because reloading somebody who is halfway through buying a policy destroys
   more than a stale page ever would. So: reload at once when nothing is at
   stake, and when something is, wait and say so quietly. */
var BUILD="__CLAUSE_BUILD__", BUILD_SEEN=null, UPDATE_READY=false, UPDATE_ASKED=false;
/* Routes where a reload costs the reader nothing but a repaint. */
var SAFE_ROUTES={"/":1,"/faq":1,"/rules":1,"/proof":1,"/how":1,"/method":1};
function midSomething(){
  /* Anything typed and not yet committed. The buying flow past its first
     step, an open dialog, a request in flight, or any field with something
     in it that the page did not put there. */
  if(typeof flow==="object"&&flow&&flow.step>1&&flow.step<DONE_STEP)return true;
  if(document.querySelector("dialog[open]"))return true;
  if(typeof PENDING==="number"&&PENDING>0)return true;
  var typed=document.querySelectorAll("input,textarea");
  for(var i=0;i<typed.length;i++){
    var el=typed[i];
    if(el.type==="hidden"||el.disabled||el.readOnly)continue;
    /* A tick box reports its value as "on" whether or not anybody ticked it,
       and a slider reports its midpoint, so for those the question is not what
       they hold but whether they have been moved. Comparing value to
       defaultValue on a checkbox is how this check spent its first run
       refusing to ever reload: one unticked consent box read as typed in. */
    if(el.type==="checkbox"||el.type==="radio"){ if(el.checked!==el.defaultChecked)return true; continue; }
    if(el.type==="range"){ if(el.hasAttribute("value")&&el.value!==el.defaultValue)return true; continue; }
    if(el.value&&el.value!==el.defaultValue)return true;
  }
  return false;
}
function safeToReload(){
  return !midSomething() && !!SAFE_ROUTES[currentRoute()];
}
function takeTheUpdate(){
  UPDATE_READY=false;
  /* reload(), and not replace(location.href): replacing an address that
     differs only after the hash is a same document navigation, so it changes
     nothing and fetches nothing. reload() keeps the address, the hash and the
     history entry, and actually goes back for the document. */
  location.reload();
}
function offerTheUpdate(){
  if(UPDATE_ASKED)return;
  UPDATE_ASKED=true;
  var bar=document.createElement("div");
  bar.className="newbuild";
  bar.setAttribute("role","status");
  bar.innerHTML='<span>'+esc(t("A newer version of this page is ready."))+'</span>'+
    '<button type="button" class="btn btn-sm">'+esc(t("Load it"))+'</button>';
  bar.querySelector("button").addEventListener("click",takeTheUpdate);
  document.body.appendChild(bar);
  requestAnimationFrame(function(){ bar.classList.add("in"); });
}
function checkTheBuild(){
  if(!BUILD||BUILD.indexOf("__")===0)return;      /* running from source */
  fetch("version.json",{cache:"no-store"}).then(function(r){ return r.ok?r.json():null; })
   .then(function(v){
     if(!v||!v.build)return;
     if(BUILD_SEEN===null)BUILD_SEEN=v.build;
     if(v.build===BUILD)return;
     UPDATE_READY=true;
     if(safeToReload())takeTheUpdate(); else offerTheUpdate();
   },function(){});
}
if(BUILD&&BUILD.indexOf("__")!==0){
  /* Asked for on the three occasions it can have changed without us looking:
     time passing, the reader coming back to the tab, and the reader moving to
     another screen, which is also the moment a held back reload becomes safe. */
  setInterval(checkTheBuild, 5*60*1000);
  addEventListener("visibilitychange",function(){ if(!document.hidden)checkTheBuild(); });
  addEventListener("hashchange",function(){ if(UPDATE_READY&&safeToReload())takeTheUpdate(); });
  /* Restored from the back/forward cache, which can hand back a document from
     days ago without running anything above. */
  addEventListener("pageshow",function(e){ if(e.persisted)checkTheBuild(); });
  setTimeout(checkTheBuild, 4000);
}

loadKey().then(function(){ restoreSession(); renderWho(); if(flow.step===CONFIRM_STEP)setNextLabel(); });

whenLinked().then(function(){
  loadCoverage().then(function(){
    if(flow.step===RISK_STEP)renderInterest();
    if(flow.step===CONFIRM_STEP)renderPrice();
  });
  loadPlaces().then(function(){
    if(flow.step===2)renderResults($("place").value);
  });
  if(flow.step===DONE_STEP&&LAST_DONE)LAST_DONE();
});

})();
