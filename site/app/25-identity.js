/* ================= a key, made here and kept here =================
   The private half is generated non extractable, so it cannot be read back out
   of this page by anything, including this page. What is stored is the handle
   to it, which only this origin in this browser can use. */

var KEYSTORE = "clause-key";

function idb(){
  return new Promise(function(resolve, reject){
    var request = indexedDB.open("clause", 1);
    request.onupgradeneeded = function(){
      request.result.createObjectStore("keys");
    };
    request.onsuccess = function(){ resolve(request.result); };
    request.onerror = function(){ reject(request.error); };
  });
}
function idbGet(key){
  return idb().then(function(db){
    return new Promise(function(resolve, reject){
      var tx = db.transaction("keys", "readonly").objectStore("keys").get(key);
      tx.onsuccess = function(){ resolve(tx.result || null); };
      tx.onerror = function(){ reject(tx.error); };
    });
  });
}
function idbPut(key, value){
  return idb().then(function(db){
    return new Promise(function(resolve, reject){
      var tx = db.transaction("keys", "readwrite").objectStore("keys").put(value, key);
      tx.onsuccess = function(){ resolve(); };
      tx.onerror = function(){ reject(tx.error); };
    });
  });
}
function idbDelete(key){
  return idb().then(function(db){
    return new Promise(function(resolve){
      var tx = db.transaction("keys", "readwrite").objectStore("keys").delete(key);
      tx.onsuccess = function(){ resolve(); };
      tx.onerror = function(){ resolve(); };
    });
  });
}

function unb64url(text){
  var s=String(text||"").replace(/-/g,"+").replace(/_/g,"/"); while(s.length%4)s+="=";
  var bin=atob(s), out=new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++)out[i]=bin.charCodeAt(i);
  return out;
}
/* ---------------- sealed documents ----------------
   A second key, for reading: ECDH rather than ECDSA, because WebCrypto keeps
   the two apart. Non extractable, kept in this browser, its public half
   registered with the protocol. A document an applicant sends is sealed in
   their browser to that public half and opens only here, with the private
   half that never left. The envelope is written up in
   clause/protocol/documents.py. */
var READKEY="clause-reading-key";
var DOC_INFO="clause application document v1";
function readingKey(){
  return idbGet(READKEY).then(function(stored){
    if(stored&&stored.pair)return stored;
    return crypto.subtle.generateKey({name:"ECDH",namedCurve:"P-256"},false,["deriveBits"]).then(function(pair){
      return crypto.subtle.exportKey("raw",pair.publicKey).then(function(raw){
        var rec={pair:pair,publicKey:b64url(raw)};
        return idbPut(READKEY,rec).then(function(){return rec;});
      });
    });
  });
}
function ensureReadingKey(path, opts){
  // Registered on every visit to the desk: cheap, idempotent, and the way a
  // new browser announces itself as the one that reads from now on.
  return readingKey().then(function(rec){
    var o={method:"POST",body:{public_key:rec.publicKey},timeout:12000};
    for(var k in opts)o[k]=opts[k];
    return api(path,o).then(function(){return rec;});
  }).catch(function(){return null;});
}
function hkdfKey(secret, salt, info, use){
  return crypto.subtle.importKey("raw",secret,"HKDF",false,["deriveKey"]).then(function(hk){
    return crypto.subtle.deriveKey({name:"HKDF",hash:"SHA-256",salt:salt,info:new TextEncoder().encode(info)},hk,{name:"AES-GCM",length:256},false,[use]);
  });
}
function sealFile(file, recipientKey, appId){
  var recipient, ephemeral, salt=crypto.getRandomValues(new Uint8Array(16)), iv=crypto.getRandomValues(new Uint8Array(12));
  return crypto.subtle.importKey("raw",unb64url(recipientKey),{name:"ECDH",namedCurve:"P-256"},false,[]).then(function(k){
    recipient=k;
    return crypto.subtle.generateKey({name:"ECDH",namedCurve:"P-256"},false,["deriveBits"]);
  }).then(function(pair){
    ephemeral=pair;
    return crypto.subtle.deriveBits({name:"ECDH",public:recipient},pair.privateKey,256);
  }).then(function(secret){
    return hkdfKey(secret,salt,DOC_INFO,"encrypt");
  }).then(function(aes){
    return Promise.all([file.arrayBuffer(), crypto.subtle.exportKey("raw",ephemeral.publicKey)]).then(function(parts){
      return crypto.subtle.encrypt({name:"AES-GCM",iv:iv,additionalData:new TextEncoder().encode(appId)},aes,parts[0]).then(function(sealed){
        return {filename:file.name.slice(0,120),content_type:file.type,bytes:parts[0].byteLength,
                ephemeral:b64url(parts[1]),salt:b64url(salt),iv:b64url(iv),data:b64url(sealed)};
      });
    });
  });
}
function openSealed(envelope){
  return readingKey().then(function(rec){
    return crypto.subtle.importKey("raw",unb64url(envelope.ephemeral),{name:"ECDH",namedCurve:"P-256"},false,[]).then(function(peer){
      return crypto.subtle.deriveBits({name:"ECDH",public:peer},rec.pair.privateKey,256);
    });
  }).then(function(secret){ return hkdfKey(secret,unb64url(envelope.salt),envelope.info||DOC_INFO,"decrypt"); })
  .then(function(aes){ return crypto.subtle.decrypt({name:"AES-GCM",iv:unb64url(envelope.iv),additionalData:new TextEncoder().encode(envelope.additional_data)},aes,unb64url(envelope.data)); })
  .then(function(plain){ return new Blob([plain],{type:envelope.content_type||"application/octet-stream"}); });
}
function docSize(n){ return n>=1000000?(n/1000000).toFixed(1)+" MB":Math.max(1,Math.round(n/1000))+" KB"; }
function docWhen(at){ return new Date(at*1000).toLocaleString(LOCALES[LANG]||"en-US"); }
/* One line per document, for the applicant and for the reviewer alike. */
function docStateText(d){
  if(!d.available)return t("sealed copy deleted after the decision");
  if(!d.opened||!d.opened.length)return t("not opened yet");
  var last=d.opened[d.opened.length-1];
  return t("opened by {who}, {when}",{who:last.by,when:docWhen(last.at)});
}

function b64url(buffer){
  var bytes = new Uint8Array(buffer), binary = "";
  for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/* address is the address this page acts as. For most people it is the one
   their device key derives. For someone who signed in through Privy it is
   their account's address, which may have been made on another of their
   devices; this device's own key has been allowed to sign for it. */
var identity = {address:null, device:null, token:null, key:null, via:null};
/* The operator's session, when this browser is the operator's. */
var OP = {token:null, reviewer:"", expires:0, bound:false};

function loadKey(){
  return idbGet(KEYSTORE).then(function(stored){
    if (!stored) return null;
    identity.key = stored.pair;
    identity.device = stored.address;
    identity.address = stored.account || stored.address;
    identity.via = stored.via || null;
    return stored;
  }).catch(function(){ return null; });
}
function saveKey(){
  var record = {pair:identity.key, address:identity.device};
  if (identity.via === "privy"){ record.account = identity.address; record.via = "privy"; }
  return idbPut(KEYSTORE, record);
}

function makeKey(){
  // P-256 because that is what platform authenticators sign with, and what
  // Rialo's published secp256r1 program verifies.
  return crypto.subtle.generateKey(
    {name:"ECDSA", namedCurve:"P-256"}, false, ["sign", "verify"]
  ).then(function(pair){
    return crypto.subtle.exportKey("raw", pair.publicKey).then(function(raw){
      return {pair:pair, publicKey:b64url(raw)};
    });
  });
}

function sign(message){
  return crypto.subtle.sign(
    {name:"ECDSA", hash:{name:"SHA-256"}},
    identity.key.privateKey,
    new TextEncoder().encode(message)
  ).then(b64url);
}

/* The key is registered every time, not only the first. Registering is
   idempotent on the protocol's side, and the protocol keeps its records in
   memory: after it restarts, a device that skipped this step presented a key
   the protocol had never heard of, every signature was refused, and the
   person was locked out of their own address with no way back in. The public
   half of a key can always be read, even from a key whose private half never
   leaves the device, so there is nothing to lose by sending it again. */
function ensureDevice(){
  return loadKey().then(function(stored){
    if (stored) {
      return crypto.subtle.exportKey("raw", stored.pair.publicKey).then(function(raw){
        return {pair:stored.pair, publicKey:b64url(raw), stored:true};
      });
    }
    return makeKey().then(function(made){
      identity.key = made.pair;
      return made;
    });
  }).then(function(made){
    return api("/api/auth/register", {
      method:"POST", body:{public_key:made.publicKey},
    }).then(function(reply){
      var changed = identity.device !== reply.address;
      identity.device = reply.address;
      if (!identity.address || identity.via !== "privy") identity.address = reply.address;
      if (!made.stored || changed) return saveKey();
    });
  });
}

function signIn(){
  return loadKey().then(function(stored){
    // An account made through Privy is joined again through Privy: after the
    // protocol restarts, only Privy can say this device belongs to it.
    if (stored && stored.via === "privy") return privySignIn();
    return deviceSignIn();
  });
}

function deviceSignIn(){
  return ensureDevice().then(function(){
    return api("/api/auth/challenge", {
      method:"POST", body:{address:identity.address, purpose:"sign-in"},
    });
  }).then(function(challenge){
    return sign(challenge.message).then(function(signature){
      return api("/api/auth/verify", {
        method:"POST",
        body:{address:identity.address, nonce:challenge.nonce, signature:signature},
      });
    });
  }).then(function(reply){
    setSession(reply.session.token);
    return reply;
  });
}

/* A session is this visit being signed in. A key remembered by the browser is
   not: it only makes signing back in one click. So the header says "Sign in"
   until the person signs in, and the session is kept for this tab only. */
var SESSION_KEY="clause-session";
function setSession(token){
  identity.token=token||null;
  try{
    if(token) sessionStorage.setItem(SESSION_KEY, JSON.stringify({token:token, address:identity.address}));
    else sessionStorage.removeItem(SESSION_KEY);
  }catch(e){}
  if(typeof renderWho==="function")renderWho();
}
function restoreSession(){
  try{
    var kept=JSON.parse(sessionStorage.getItem(SESSION_KEY)||"null");
    if(kept&&kept.token&&kept.address&&kept.address===identity.address)identity.token=kept.token;
  }catch(e){}
}
function signOut(){
  // The operator's session goes whichever role the page is showing: a
  // token kept in memory after a role switch would still be a way in.
  if(OP.token)opSignOut();
  if(getRole()==="admin"){ setRole("person"); renderWho(); location.hash="#/"; return; }
  setSession(null);
  if (window.ClausePrivy) window.ClausePrivy.logout().catch(function(){});
}

function forgetDevice(){
  try{ sessionStorage.removeItem(SESSION_KEY); }catch(e){}
  identity = {address:null, device:null, token:null, key:null, via:null};
  setTimeout(function(){ if (typeof renderWho === "function") renderWho(); }, 0);
  if (window.ClausePrivy) window.ClausePrivy.logout().catch(function(){});
  return idbDelete(KEYSTORE).then(function(){ return idbDelete(READKEY); });
}

/* ---------------- signing in through Privy ----------------
   Email, Google, a passkey or a wallet, checked by Privy. Privy's window is a
   large script, so it is fetched only when someone asks for it. What comes
   back is a short lived token naming the person; the protocol checks it, and
   this device's key is joined to that person's account. Purchases are still
   signed by the device key, exactly as before. */
var PRIVY = {config:null, loading:null};
function privyConfig(){
  if (PRIVY.config) return Promise.resolve(PRIVY.config);
  return api("/api/privy", {timeout:8000}).then(function(reply){
    PRIVY.config = reply || {enabled:false};
    return PRIVY.config;
  }, function(){ return {enabled:false}; });
}
function loadPrivy(){
  if (PRIVY.loading) return PRIVY.loading;
  PRIVY.loading = privyConfig().then(function(config){
    if (!config.enabled) throw new Error("Privy is not enabled");
    return new Promise(function(resolve, reject){
      if (window.ClausePrivy) return resolve();
      var script = document.createElement("script");
      script.type = "module";
      script.src = "privy/privy.js";
      script.onload = function(){ resolve(); };
      script.onerror = function(){ reject(new Error("the sign in window did not load")); };
      document.head.appendChild(script);
    }).then(function(){
      var theme = document.documentElement.getAttribute("data-theme") ||
        (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
      return window.ClausePrivy.start(config.app_id, theme);
    });
  });
  PRIVY.loading.catch(function(){ PRIVY.loading = null; });
  return PRIVY.loading;
}
function privySignIn(){
  var privyToken;
  return loadPrivy().then(function(){
    return window.ClausePrivy.token();
  }).then(function(existing){
    return existing || window.ClausePrivy.login();
  }).then(function(token){
    privyToken = token;
    return ensureDevice();
  }).then(function(){
    return api("/api/auth/challenge", {
      method:"POST", body:{address:identity.device, purpose:"link"},
    });
  }).then(function(challenge){
    return sign(challenge.message).then(function(signature){
      return api("/api/privy/link", {method:"POST", body:{
        privy_token:privyToken, address:identity.device,
        nonce:challenge.nonce, signature:signature,
      }});
    });
  }).then(function(reply){
    identity.address = reply.address;
    identity.via = "privy";
    setSession(reply.session.token);
    return saveKey().then(function(){ return reply; });
  });
}

