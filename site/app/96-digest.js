/* ---------------- the digest above the hero ----------------
   The three bands each answer their own feed and paint as soon as it replies.
   The digest is the three of them in one row, so it cannot be painted by any
   one of them: each stores what it built, and whoever finishes last draws the
   merged row. Kept in LIVE so a country change replaces a feed's share rather
   than adding to it.

   Severe readings come first, because the row scrolls and the first thing in
   view is what a glance gets. Three from each feed at most: one noisy source
   -- a hundred late departures -- would otherwise be the whole digest and the
   other two would never appear in it. */
var DIGEST_FEEDS = ["quakes", "weather", "flights"];
var DIGEST_PER_FEED = 3;

function chipRank(html){
  return /\blv-crit\b/.test(html) ? 0 : /\blv-warn\b/.test(html) ? 1 : 2;
}

/* The same chip without its link. The quake chips are anchors to USGS and they
   belong in the band at the foot of the page, which has the source line beside
   them; in front of the hero they would be tab stops on the way to the first
   thing a buyer came to do. The class is what carries the colour, so it stays. */
function chipUnlinked(html){
  return html.replace(/<a\b([^>]*)>/g, function(all, attrs){
    return "<span" + attrs.replace(/\s(?:href|target|rel)="[^"]*"/g, "") + ">";
  }).replace(/<\/a>/g, "</span>");
}

function digestKeep(feed, chips){
  LIVE.digest = LIVE.digest || {};
  LIVE.digest[feed] = (chips || []).slice()
    .sort(function(a, b){ return chipRank(a) - chipRank(b); })
    .slice(0, DIGEST_PER_FEED);
  paintDigest();
}

function paintDigest(){
  if(!$("band-now-run"))return;
  var held = LIVE.digest || {}, all = [];
  DIGEST_FEEDS.forEach(function(feed){
    (held[feed] || []).forEach(function(chip){ all.push(chip); });
  });
  // Nothing yet from any of them: the row keeps its height and says so, rather
  // than standing empty above the hero and then pushing it down when it fills.
  if(!DIGEST_FEEDS.some(function(feed){ return held[feed] !== undefined; })){
    if(LIVE.digestDrawn === null)return;
    LIVE.digestDrawn = null;
    digestSaying(t("Reading the sources…"));
    return;
  }
  all.sort(function(a, b){ return chipRank(a) - chipRank(b); });
  var drawn = all.join("");
  if(drawn === LIVE.digestDrawn)return;
  LIVE.digestDrawn = drawn;
  /* Keep where the row had got to. Filling a band rewrites its contents, which
     restarts the animation at the left, and the digest is repainted whenever
     any one of the three feeds answers -- three times on a load, and again each
     minute, because a reading carries its own "fifteen minutes ago" and that
     sentence changes while the earthquake does not. A row that jumped back to
     the beginning every minute, above the hero, reads as a fault rather than as
     a refresh. The three bands below are left as they are: each is rewritten
     only by its own feed, and each is at the foot of the page. */
  if(!all.length){
    digestSaying(t("Nothing to report right now."));
    return;
  }
  var run = $("band-now-run"), was = null;
  try{
    if(run.getAnimations)
      run.getAnimations().forEach(function(a){ if(was === null)was = a.currentTime; });
  }catch(err){}
  run.classList.remove("one-line");
  bandFill("band-now-run", all.map(chipUnlinked), "");
  try{
    if(was !== null && run.getAnimations)
      run.getAnimations().forEach(function(a){ a.currentTime = was; });
  }catch(err){}
}

/* What the row says before it has readings, said in a chip.
   It was a line of text, and the row was then a different height from the row it
   stands in for: 65px against 55, a ten pixel shift at the top of the page,
   which is the whole reason the stand-in exists. Two constants were tried and
   both were wrong -- a chip measures 35.19px here, not the 37 that was assumed,
   and the figure moves with the font. A chip is the same height as a chip, so
   the stand-in is one. The shift was measured as zero before that because the
   measurement filled the row before it read it: feeds that answer instantly
   make "before" the same moment as "after". */
function digestSaying(text){
  var run = $("band-now-run");
  if(!run)return;
  // Measured at 390px: the track is 252px and the sentence this used to carry
  // wanted 451px, so a phone was shown two thirds of it under a mask that made
  // the cut look like a fade. What the digest says is kept to one row's worth.
  run.style.animation = "none";
  run.style.removeProperty("--dur");
  run.classList.add("one-line");
  run.innerHTML = '<span class="chip saying"><span>' + esc(text) + '</span></span>';
}

function digestUnreachable(){
  LIVE.digest = {};
  LIVE.digestDrawn = undefined;
  if($("band-now-run"))
    // The short one, which the sign in strip already uses and which already has
    // its six translations: the long sentence is the three bands' to say, where
    // there is a row each to say it in.
    digestSaying(t("The protocol is not answering."));
}

function renderLive(){
  if(!link.live){
    digestUnreachable();
    $("band-quakes-src").textContent=""; $("band-flights-src").textContent="";
    bandFill("band-quakes",[],t("The protocol is not reachable, so there is nothing live to show."));
    bandFill("band-flights",[],t("The protocol is not reachable, so there is nothing live to show."));
    $("band-weather-src").textContent=""; bandFill("band-weather",[],t("The protocol is not reachable, so there is nothing live to show."));
    return;
  }
  fillNowCountries();
  var code=LIVE.country||"", name=code?regionName(code):"";
  // A country change starts the digest over, because holding the previous
  // country's readings while the new ones arrive would put a reading from
  // somewhere else at the top of the page. A refresh must not: this runs every
  // sixty seconds, and clearing it there made the row read "Reading the
  // sources" for a moment every minute, above the hero.
  if(LIVE.digestCountry!==code){ LIVE.digest={}; LIVE.digestCountry=code; paintDigest(); }
  var query=code?"?country="+encodeURIComponent(code):"";
  var asked=code;
  api("/api/live/quakes"+query,{timeout:10000}).then(function(feed){
    if(asked!==(LIVE.country||""))return;
    var now=Date.now()/1000, week=feed.window==="week";
    $("band-quakes-src").textContent=(!code ? t("USGS, worldwide, past 24 hours")
        : week ? t("USGS, {country}, past 7 days",{country:name})
        : t("USGS, {country}, past 24 hours",{country:name}))+
      (feed.stale&&feed.age_seconds!=null?" · "+t("last updated {ago}",{ago:agoText(feed.age_seconds)}):"");
    var quakeChips=(feed.items||[]).map(function(q){return quakeChip(q,now);});
    digestKeep("quakes",quakeChips);
    bandFill("band-quakes",quakeChips,
      code ? t("No earthquake of magnitude 2.5 or more has been recorded in {country} in the past week.",{country:name})
           : t("No earthquake of magnitude 2.5 or more has been recorded in the past day."));
  },function(){ digestKeep("quakes",[]); bandFill("band-quakes",[],t("The earthquake feed did not answer.")); });
  api("/api/live/weather?country="+encodeURIComponent(code||""),{timeout:45000}).then(function(feed){
    if(asked!==(LIVE.country||""))return;
    var where=code?name:t("worldwide");
    if(feed.available===false){
      $("band-weather-src").textContent=t("No places listed for {country}",{country:where});
      digestKeep("weather",[]);
      bandFill("band-weather",[],t("No places are listed for {country} yet.",{country:where}));
      return;
    }
    $("band-weather-src").textContent=t("Open-Meteo, {country}, today",{country:where})+
      (feed.stale&&feed.age_seconds!=null?" · "+t("last updated {ago}",{ago:agoText(feed.age_seconds)}):"");
    var weatherChips=(feed.items||[]).map(weatherChip);
    digestKeep("weather",weatherChips);
    bandFill("band-weather",weatherChips,t("The weather feed did not answer."));
  },function(){ digestKeep("weather",[]); bandFill("band-weather",[],t("The weather feed did not answer.")); });
  api("/api/live/flights"+query,{timeout:10000}).then(function(feed){
    if(asked!==(LIVE.country||""))return;
    if(feed.available===false){
      $("band-flights-src").textContent=t("No public feed for {country}",{country:name});
      digestKeep("flights",[]);
      bandFill("band-flights",[],t("There is no public live flight delay feed for {country}. The United States publishes one, through the FAA; other countries follow when a licensed feed is connected.",{country:name}));
      return;
    }
    var usa=code==="US"||(!code&&feed.source==="FAA");
    $("band-flights-src").textContent=(usa ? t("FAA, United States airports only")
        : feed.source==="AirLabs" ? t("AirLabs, {country}, departures 45 minutes late or more",{country:code?name:t("worldwide")})
        : t("FlightAware, {country}",{country:code?name:t("worldwide")}))+
      (feed.stale&&feed.age_seconds!=null?" · "+t("last updated {ago}",{ago:agoText(feed.age_seconds)}):"");
    var flightChips=(feed.items||[]).map(flightChip);
    digestKeep("flights",flightChips);
    bandFill("band-flights",flightChips,
      usa ? t("No delay programmes are in force at United States airports right now.")
          : t("No airport in {country} is reporting delays right now.",{country:code?name:t("the world")}));
  },function(){ digestKeep("flights",[]); bandFill("band-flights",[],t("The flight delay feed did not answer.")); });
}
function startLive(){
  paintDigest();
  fillNowCountries();
  $("now-country").addEventListener("change",function(e){
    LIVE.country=e.target.value;
    try{ localStorage.setItem("clause.nowCountry",LIVE.country); }catch(err){}
    renderLive();
  });
  whenLinked().then(renderLive);
  if(LIVE.timer)clearInterval(LIVE.timer);
  LIVE.timer=setInterval(function(){ if(currentRoute()==="/"&&!document.hidden)renderLive(); },60000);
}

