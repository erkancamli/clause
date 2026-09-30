/* ================= routing ================= */
var VIEWS={"/":"view-home","/cover":"view-cover","/mine":"view-mine","/profile":"view-profile",
           "/how":"view-how","/pool":"view-pool","/proof":"view-proof","/rialo":"view-rialo",
           "/insurers":"view-insurers","/privacy":"view-privacy","/faq":"view-faq","/rules":"view-rules",
           "/company":"view-company","/admin":"view-admin","/ask":"view-ask"};
function currentRoute(){return (location.hash||"#/").replace(/^#/,"")||"/";}
function show(route, moved){
  // A proof link carries the policy it is about: #/proof/CLS-XXXX
  var proof = route.match(/^\/proof(?:\/(.+))?$/);
  if (proof) { route = "/proof"; renderProof(proof[1] ? decodeURIComponent(proof[1]) : null); }
  // And a purchase carries the question it is on: #/cover/3
  var step = stepAsked(route);
  if (step !== null) {
    route = "/cover";
    if (flow.step >= DONE_STEP) resetFlow();
    flow.step = step;
    renderStep();
    if (location.hash !== stepHash(step)) settle(stepHash(step));
  }
  if (route === "/rules") renderRules();
  if (route === "/ask") renderAskForm();
  if(!VIEWS[route])route="/";
  // Which screen, if any, the stylesheet showed before this script was read.
  var already=document.documentElement.getAttribute("data-first");
  document.documentElement.removeAttribute("data-first");
  Object.keys(VIEWS).forEach(function(k){
    var view=$(VIEWS[k]);
    view.classList.toggle("settled",k===already&&k===route);
    view.classList.toggle("on",k===route);
  });
  Array.prototype.forEach.call($("mainnav").querySelectorAll("a"),function(a){
    if(a.dataset.route===route)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
  });
  window.scrollTo(0,0);
  if(route==="/pool"){ fillCapBars(); startTick(); whenLinked().then(renderTranches); } else stopTick();
  if(route==="/mine")renderMine();
  if(route==="/profile")renderProfile();
  if(route==="/insurers"){ renderInsurers(); renderAskedDocuments(); }
  if(route==="/company")renderCompany();
  if(route==="/admin"){ whenLinked().then(bindOperator); }
  if(route==="/rialo")renderRialo();
  announce(route, moved);
}

/* Each question in a purchase is a place, with its own entry in the browser's
   history: #/cover, then #/cover/2 through #/cover/5. Baymard's testing found
   that people in a checkout reach for the browser's Back button rather than
   for a Change link on the page, and that a flow living at a single address
   throws them out of the purchase entirely when they do. Back is a step back
   now, and every answer already given is still on the screen when they
   arrive, which is what 3.3.7 asks for.

   The done screen is not a question and takes no entry of its own: a purchase
   that has gone through is not somewhere to return to. Going back from it
   begins a fresh one at the first question rather than reopening a finished
   one. */
function stepHash(n){ return n > 1 && n < DONE_STEP ? "#/cover/" + n : "#/cover"; }
function settle(hash){
  try{ history.replaceState(null, "", location.pathname + location.search + hash); }
  catch(e){ location.hash = hash; }
}
function goStep(n, quietly){
  flow.step = n;
  if(n > flow.reached)flow.reached = n;
  var want = stepHash(n);
  if(location.hash === want){ renderStep(); return; }
  if(quietly){ settle(want); renderStep(); return; }
  location.hash = want;                       // the hashchange draws it
}
function stepAsked(route){
  var asked = route.match(/^\/cover(?:\/([2-9]))?$/);
  if(!asked)return null;
  var want = asked[1] ? +asked[1] : 1;
  // Backwards is free. Forwards is not: a question the reader has not reached
  // is a question whose answers do not exist, so a pasted or bookmarked link
  // into the middle of a purchase that never started lands at the beginning.
  if(flow.step >= DONE_STEP)return 1;
  if(want > flow.reached)return flow.chosen ? flow.step : 1;
  return want;
}

/* What this screen is called, in the language it is being read in.
   Twelve screens in seven languages shared one title, "Clause", because the
   title was written once in the markup and never touched again: a tab, a
   bookmark and the first thing a screen reader says all named the site
   rather than the page (2.4.2). The name is taken from the screen's own h1
   rather than from a second table, because a second table is a second place
   for the words to go stale, and the h1 is already translated.

   Focus goes there too, but only when somebody navigated. A router that
   leaves focus where it was sends the next Tab back to the top of a page
   that is no longer on the screen; one that resets focus to the document
   says nothing at all about where the reader has arrived (2.4.3). The
   heading is both, so it is told once, by the heading it now sits on. */
function announce(route, moved){
  var heading = $(VIEWS[route]).querySelector("h1");
  if(!heading)return;
  var called = heading.textContent.trim().replace(/[.。]\s*$/, "");
  document.title = route === "/" ? "Clause · " + called : called + " · Clause";
  if(!moved)return;
  heading.setAttribute("tabindex", "-1");
  try{ heading.focus({preventScroll:true}); }catch(e){ heading.focus(); }
}
addEventListener("hashchange",function(){show(currentRoute(), true);});

/* A hash router and an anchor inside the page want the same character.

   Routes here are written "#/rules"; an anchor is written "#main". The router
   reads whatever follows the hash, finds no screen of that name, and falls
   through to "/" -- so following an in page anchor took the reader home. The
   skip link at the top of the document, which exists so that somebody on a
   keyboard can reach the content of the page they are on, did exactly that
   from every page. So did the rulebook's index of perils.

   Anything whose fragment begins with a slash is the router's business and is
   left alone. Anything else that names an element in the document is scrolled
   to and focused here, and the hash is not touched, so there is nothing for
   the router to mishear. */
addEventListener("click",function(e){
  if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
  var a=e.target&&e.target.closest?e.target.closest('a[href^="#"]'):null;
  if(!a)return;
  var name=a.getAttribute("href").slice(1);
  if(!name||name.charAt(0)==="/")return;
  var el=document.getElementById(name);
  if(!el)return;
  e.preventDefault();
  if(!el.hasAttribute("tabindex"))el.setAttribute("tabindex","-1");
  try{ el.focus({preventScroll:true}); }catch(err){ el.focus(); }
  el.scrollIntoView({behavior:"smooth",block:"start"});
});
/* Sections rise into place as they come into view: the cards on the home
   page, the steps and the columns on the other pages. Each waits its turn
   after the one before it, so a row reads left to right. Nothing is hidden
   until the observer exists, so a browser without it sees everything at once. */
(function(){
  var ok=!(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  if(!ok||!("IntersectionObserver" in window))return;
  var io=new IntersectionObserver(function(entries){
    entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add("in"); io.unobserve(e.target); } });
  },{rootMargin:"0px 0px -8% 0px",threshold:.08});
  var groups=["#home-picks .pick",".flowline > div",".view .card",".vrule",".trust > span"];
  var fold=(window.innerHeight||0)*0.92;
  groups.forEach(function(sel){
    Array.prototype.forEach.call(document.querySelectorAll(sel),function(el,i){
      // The stylesheet paints the opening screen before this script is read,
      // so by now the top of it has been on the reader's screen for a second
      // or more. Fading in what somebody is already looking at is a blink,
      // not an entrance: only what is still below the fold rises. A screen
      // that is not the opening one has no box yet, and keeps its entrance.
      var box=el.getBoundingClientRect();
      if(box.height && box.top < fold)return;
      el.classList.add("reveal"); el.style.setProperty("--i",String(i%4)); io.observe(el);
    });
  });
})();
(function(){
  var ok=!(window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  if(!ok)return;
  var SEL=".btn-primary,.btn-line,.mainnav a,.pick,.opt,.offer,.choice,.step-dot";
  document.addEventListener("click",function(ev){
    var el=ev.target&&ev.target.closest?ev.target.closest(SEL):null;
    if(!el||el.disabled)return;
    var x=ev.clientX, y=ev.clientY;
    if(!x&&!y){ var r=el.getBoundingClientRect(); x=r.left+r.width/2; y=r.top+r.height/2; }   // a key press
    var burst=document.createElement("span"); burst.className="tburst"; burst.setAttribute("aria-hidden","true");
    burst.style.transform="translate("+x+"px,"+y+"px)";
    burst.innerHTML="<i></i><i></i><i></i><b></b>";
    document.body.appendChild(burst);
    setTimeout(function(){ if(burst.parentNode)burst.parentNode.removeChild(burst); },1100);
    if(el.classList.contains("btn")||el.matches(".mainnav a")){
      el.classList.remove("fired"); void el.offsetWidth; el.classList.add("fired");
      setTimeout(function(){ el.classList.remove("fired"); },700);
    }
  },true);
})();
/* How tall the price bar is, and whether it is on screen: the assistant's
   button reads both so it never covers the button that buys the cover. */
(function(){
  var bar=$("pricebar"); if(!bar)return;
  function measure(){
    // Its height, not its attribute: the bar lives inside a view that may be
    // switched off entirely, in which case it is there but takes no room.
    var h=bar.hidden?0:Math.round(bar.getBoundingClientRect().height);
    document.body.classList.toggle("has-pricebar",h>0);
    document.documentElement.style.setProperty("--pricebar-h", h+"px");
  }
  measure();
  new MutationObserver(measure).observe(bar,{attributes:true,attributeFilter:["hidden","class"],childList:true,subtree:true});
  addEventListener("resize",measure,{passive:true});
})();
(function(){
  var top=document.querySelector("header.top"); if(!top)return;
  var last=null;
  function look(){ var on=window.scrollY>6; if(on!==last){ top.classList.toggle("is-scrolled",on); last=on; } }
  addEventListener("scroll",look,{passive:true}); look();

  /* Everything that stops below the header -- the instrument, the summary
     rail, the map, the answers -- was written against a 61px header and added
     its own margin to that by hand. The header is 89px as soon as the
     navigation wraps, which happens at 1024 in English and sooner in a
     language whose words are longer, and a panel stuck at 76 then sat under
     it. Measured here instead, and published as one number the sheet reads.
     ResizeObserver rather than the resize event, because the header changes
     height when its own contents change too: a language with longer words,
     the sign-in button becoming an address, the strip above it appearing. */
  var seen=0;
  function height(){
    var h=Math.round(top.getBoundingClientRect().height);
    if(!h||h===seen)return;
    seen=h;
    document.documentElement.style.setProperty("--header-h",h+"px");
  }
  height();
  if(window.ResizeObserver)new ResizeObserver(height).observe(top);
  else addEventListener("resize",height,{passive:true});
  LANG_LISTENERS.push(height);
})();


