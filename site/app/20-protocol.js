/* ================= the protocol, over the wire =================
   This page is a client. When it can reach the protocol it shows what the
   protocol says; when it cannot it falls back to computing the same model in
   the browser and says so in the bar at the top. What it never does is show a
   figure from one and imply it came from the other. */

var API = (function(){
  // Same origin when this page is served by the protocol itself; the API host
  // otherwise. A query parameter overrides both, which is how you point the
  // published page at a server before its name exists.
  var override = new URLSearchParams(location.search).get("api");
  if (override) return override.replace(/\/+$/, "");
  if (location.protocol === "file:") return "https://api.clause.insure";
  if (/^(localhost|127\.)/.test(location.hostname)) return "";
  if (/(^|\.)clause\.insure$/.test(location.hostname)) return "https://api.clause.insure";
  return "https://api.clause.insure";
})();

var link = {live:false, checked:false, note:""};

/* One retry, for reads only.
   Replacing the protocol takes a second or two with nothing listening, and a
   page that happened to ask during it showed the reader that nothing could be
   reached. A GET asked again a moment later is free of consequence -- it is
   the same question -- so it is asked again once, and the restart is invisible
   instead of being reported.
   Never a write. A POST that failed may have been received and acted on, and
   the failure can be the reply going missing rather than the request: sending
   it twice is how somebody is charged twice. Those still surface, and the
   flow's own checkpoint is what recovers them. */
function api(path, options){
  options = options || {};
  var method = (options.method || "GET").toUpperCase();
  if (method === "GET" && !options.noRetry) {
    var again = Object.assign({}, options, {noRetry: true});
    return api(path, again).then(null, function(reason){
      var status = reason && reason.status;
      var worthAsking = !status || status === 502 || status === 503 || status === 504;
      if (!worthAsking) throw reason;
      return new Promise(function(done){ setTimeout(done, 900); })
        .then(function(){ return api(path, again); });
    });
  }
  var headers = {"content-type":"application/json"};
  if (options.token) headers["authorization"] = "Bearer " + options.token;
  if (options.headers) for (var h in options.headers) headers[h] = options.headers[h];
  var controller = new AbortController();
  var timer = setTimeout(function(){ controller.abort(); }, options.timeout || 12000);
  return fetch(API + path, {
    method: options.method || "GET",
    headers: headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: controller.signal,
  }).then(function(reply){
    clearTimeout(timer);
    if (options.raw && reply.ok) return reply.blob();
    // Reading the body can fail on its own, after the headers arrived: a
    // connection cut part way through leaves a rejection with no status and
    // no payload, and that fell through every branch of the buy banner to the
    // one sentence that names no reason. The request was sent and may have
    // been acted on, so it is marked unanswered like any other silence, which
    // is also what makes the page ask the same question again.
    return reply.text().then(null, function(cut){
      var error = new Error("the answer was cut off while it was being read");
      error.status = reply.status;
      error.kind = "answer cut off after http " + reply.status
                 + " (" + ((cut && cut.name) || "network") + ")";
      error.unanswered = true;
      throw error;
    }).then(function(text){
      var payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch (e) { payload = {detail:text}; }
      if (!reply.ok) {
        var error = new Error("request failed");
        error.status = reply.status;
        error.payload = payload;
        // What the page can say about it afterwards. A banner that reports
        // every failure with one sentence cannot be acted on by the person
        // reading it or by anybody they send the screenshot to.
        error.kind = "http " + reply.status;
        throw error;
      }
      return payload;
    });
  }, function(reason){
    clearTimeout(timer);
    if (reason && !reason.kind) {
      // An abort is this page giving up, and it is the failure that reaches a
      // buyer most often on a slow line; a TypeError from fetch is the
      // request never arriving at all. They have different answers and used
      // to read identically.
      reason.kind = (reason.name === "AbortError")
        ? "no answer within " + Math.round((options.timeout || 12000) / 1000) + "s"
        : "could not reach the server (" + (reason.name || "network") + ")";
      // Nothing came back at all. Which is not the same as being refused: the
      // request may have been read and acted on, so the only safe thing a
      // caller can do with it is ask the same question again -- never send a
      // different one.
      reason.unanswered = true;
    }
    throw reason;
  });
}

function setLink(live, note){
  link.live = live; link.checked = true; link.note = note || "";
  var bar = $("link-state");
  bar.hidden = false;
  bar.className = "linkstate " + (live ? "live" : "offline");
  bar.innerHTML = live
    ? '<span class="pip"></span><span>'+t("<b>Live.</b> Prices, policies and settlement come from the protocol at {host}.",
        {host:esc(API.replace(/^https?:\/\//, ""))})+'</span>'
    : '<span class="pip"></span><span>'+t("<b>Not connected.</b> {why} Everything below is computed in your browser from the same model, and nothing you do here is real.",
        {why:esc(t(note || "The protocol is unreachable."))})+'</span>';
}

/* Opened straight onto a deep link, a screen has to know whether the protocol
   is reachable before it can say anything true about it. One check, shared, so
   nothing renders "not connected" merely because it asked first. */
var linkReady = null;
function whenLinked(){ return linkReady || (linkReady = checkLink()); }

function checkLink(){
  return api("/api/health", {timeout:6000}).then(function(payload){
    setLink(true);
    return payload;
  }, function(){
    setLink(false, N("The protocol is not answering."));
    // Not remembered: the next screen asks again, so one slow start does
    // not mark the whole session as offline.
    linkReady=null;
    return null;
  });
}

