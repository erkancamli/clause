
"use strict";
(function(){
var $=function(id){return document.getElementById(id);};

/* ---------------- theme ---------------- */
var root=document.documentElement;
/* Three modes, in a cycle: the device's own (nothing set, the browser's
   preference applies and follows it when it changes), light, dark. A choice
   is kept on this device; the device's own is the absence of one. */
try{var saved=localStorage.getItem("clause-theme");if(saved==="dark"||saved==="light")root.setAttribute("data-theme",saved);}catch(e){}
function themeMode(){ var ex=root.getAttribute("data-theme"); return ex==="light"||ex==="dark"?ex:"system"; }
function labelTheme(){
  var b=$("theme"); if(!b)return;
  var m=themeMode(), name=m==="system"?t("Theme: follows your device"):m==="light"?t("Theme: light"):t("Theme: dark");
  b.title=name; b.setAttribute("aria-label",name);
}
function applyTheme(mode){
  if(mode==="light"||mode==="dark")root.setAttribute("data-theme",mode); else root.removeAttribute("data-theme");
  try{ if(mode==="light"||mode==="dark")localStorage.setItem("clause-theme",mode); else localStorage.removeItem("clause-theme"); }catch(e){}
  labelTheme();
}
$("theme").addEventListener("click",function(){
  var order=["system","light","dark"];
  applyTheme(order[(order.indexOf(themeMode())+1)%order.length]);
});

/* ---------------- language ----------------
   English is the source and the binding text. Every other language is a
   translation shown for convenience, and the page says so wherever a sentence
   carries legal weight.

   Keys are the English sentences themselves, with {name} where a value goes.
   That choice has one property worth more than tidiness: a sentence nobody has
   translated yet falls back to the English, never to a key name or a blank, so
   a missing translation degrades into the binding text rather than into a bug.

   Dictionaries are separate files fetched on demand, so English visitors do not
   download six languages to read one. */

var LANGS=[["en","English"],["tr","Türkçe"],["es","Español"],["fr","Français"],
           ["de","Deutsch"],["ru","Русский"],["ja","日本語"]];
var LOCALES={en:"en-US",tr:"tr-TR",es:"es-ES",fr:"fr-FR",de:"de-DE",ru:"ru-RU",ja:"ja-JP"};
var LANG="en", DICT={}, PATTERNS=[];

function supported(code){
  for(var i=0;i<LANGS.length;i++)if(LANGS[i][0]===code)return true;
  return false;
}
/* Chosen in the head, where it had to be chosen to be of any use, and only
   read here. The asked-for language, then the kept one, then the browser's. */
function pickLang(){
  var code=window.__boot&&window.__boot.lang;
  return (code&&supported(code))?code:"en";
}

/* Translate a sentence. Values are filled after translation, so a translator
   can move {name} wherever their grammar wants it. The caller escapes: pass
   escaped values into a template that contains markup, or escape the result of
   a template that does not. */
function t(en, vars){
  var s=(LANG!=="en"&&Object.prototype.hasOwnProperty.call(DICT,en)&&DICT[en])||en;
  if(vars) s=s.replace(/\{(\w+)\}/g,function(m,k){
    return Object.prototype.hasOwnProperty.call(vars,k)?String(vars[k]):m;
  });
  return s;
}

/* Sentences the protocol itself writes. They arrive in English because English
   is the binding text, and are translated here by matching them against the
   templates they were written from. Anything that matches nothing is shown as
   it came, in English, which is the correct failure. */
var VALUE_WORDS={earthquake:N("earthquake"),drought:N("drought"),flight_delay:N("flight delay"),vehicle_flood:N("vehicle flood"),storm:N("storm"),
                 stablecoin:N("stablecoin"),fiat:N("fiat")};
function compilePatterns(list){
  return list.map(function(template){
    var names=[];
    var source=template.replace(/[.*+?^$()|[\]\\]/g,"\\$&").replace(/\\?\{(\w+)\\?\}/g,function(m,k){
      names.push(k); return "(.+?)";
    });
    return {template:template, names:names, re:new RegExp("^"+source+"$")};
  });
}
var EN_COUNTRY=null;
function englishCountry(name){
  if(!EN_COUNTRY){ EN_COUNTRY={}; COUNTRIES.forEach(function(r){ EN_COUNTRY[r[1]]=r[0]; }); }
  return EN_COUNTRY[name]||null;
}
function localValue(value){
  var v=String(value);
  if(/^[A-Z]{2}$/.test(v))return regionName(v);
  var code=englishCountry(v); if(code)return regionName(code);
  if(Object.prototype.hasOwnProperty.call(VALUE_WORDS,v))return t(VALUE_WORDS[v]);
  // A company or regulator name the protocol wrote, if it is one we have.
  if(LANG!=="en"&&Object.prototype.hasOwnProperty.call(DICT,v))return DICT[v];
  return v;
}
function ts(sentence){
  var text=String(sentence==null?"":sentence);
  if(LANG==="en"||!text)return text;
  if(Object.prototype.hasOwnProperty.call(DICT,text))return DICT[text];
  for(var i=0;i<PATTERNS.length;i++){
    var p=PATTERNS[i], m=p.re.exec(text);
    if(!m||!Object.prototype.hasOwnProperty.call(DICT,p.template))continue;
    var vars={};
    p.names.forEach(function(k,j){ vars[k]=localValue(m[j+1]); });
    return t(p.template,vars);
  }
  return text;
}
/* A protocol sentence, translated, with the English it came from one click
   away. Used wherever the sentence decides something: a refusal, a disclosure,
   the terms. */
function tsHtml(sentence){
  var local=ts(sentence);
  if(LANG==="en"||local===sentence)return esc(sentence);
  return esc(local)+' <details class="orig"><summary>'+esc(t("English original"))+
    '</summary>'+esc(sentence)+'</details>';
}

var REGION_NAMES=null;
function regionName(code){
  try{
    if(!REGION_NAMES||REGION_NAMES.lang!==LANG){
      REGION_NAMES=new Intl.DisplayNames([LOCALES[LANG]||"en-US"],{type:"region"});
      REGION_NAMES.lang=LANG;
    }
    var name=REGION_NAMES.of(code);
    if(name&&name!==code)return name;
  }catch(e){}
  for(var i=0;i<COUNTRIES.length;i++)if(COUNTRIES[i][0]===code)return COUNTRIES[i][1];
  return code;
}

/* Marks an English sentence that is translated later, where it is used rather
   than where it is written. Does nothing at runtime; the extraction script
   reads it. */
function N(en){ return en; }

/* Text a script writes once that should still follow a language change: it
   carries its English with it, and translateStatic() reads that back. */
function tspan(en){
  return '<span data-i18n data-en="'+esc(en).replace(/"/g,"&quot;")+'">'+esc(t(en))+'</span>';
}

function normHtml(html){ return String(html).replace(/\s+/g," ").trim(); }

/* The markup in the page. Its English is read once, here, before anything has
   run, so switching languages twice never translates a translation, and so a
   copy of marked markup made later by a script (the first step copies the home
   page's cards) is left to the script that made it rather than mistaken for
   source text. */
var STATIC_ATTRS=[["data-i18n-ph","placeholder"],["data-i18n-aria","aria-label"],["data-i18n-title","title"]];
(function captureStatic(){
  Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"),function(el){
    el.__en=normHtml(el.innerHTML);
    // Kept on the element too, so a copy of this markup made later by a script
    // still knows its English.
    el.setAttribute("data-en",el.__en);
  });
  STATIC_ATTRS.forEach(function(pair){
    Array.prototype.forEach.call(document.querySelectorAll("["+pair[0]+"]"),function(el){
      el["__en_"+pair[1]]=el.getAttribute(pair[1])||"";
    });
  });
})();
function translateStatic(root){
  var scope=root||document;
  Array.prototype.forEach.call(scope.querySelectorAll("[data-i18n]"),function(el){
    var en=el.__en!==undefined?el.__en:el.getAttribute("data-en");
    if(en==null)return;
    var said=t(en);
    // Only if it is going to say something different. Rewriting an element
    // with the words it already holds is a new element as far as the browser
    // is concerned: it repaints, and it restarts the clock that measures when
    // the page showed its largest thing. In English that was every marked
    // element on the page, for nothing but collapsed whitespace.
    if(normHtml(el.innerHTML)===said)return;
    el.innerHTML=said;
  });
  if(root)return;
  STATIC_ATTRS.forEach(function(pair){
    Array.prototype.forEach.call(document.querySelectorAll("["+pair[0]+"]"),function(el){
      var key="__en_"+pair[1];
      if(el[key]===undefined)return;
      el.setAttribute(pair[1],t(el[key]));
    });
  });
  document.documentElement.setAttribute("lang",LANG);
  var note=$("lang-note");
  if(note){
    // Said once per language, then out of the way: the terms and every
    // refusal still carry the English original where it matters.
    var seen=false;
    try{ seen=localStorage.getItem("clause-langnote-"+LANG)==="1"; }catch(e){}
    note.hidden=LANG==="en"||seen;
    note.innerHTML='<span>'+esc(t("Translated for convenience. The English text is the binding one."))+
      '</span> <button type="button" class="linkish" id="lang-en">'+esc(t("Read in English"))+'</button>'+
      '<button type="button" class="note-x" id="lang-note-x" aria-label="'+esc(t("Close"))+'">×</button>';
    var back=$("lang-en");
    if(back)back.addEventListener("click",function(){ setLang("en"); });
    $("lang-note-x").addEventListener("click",function(){
      note.hidden=true;
      try{ localStorage.setItem("clause-langnote-"+LANG,"1"); }catch(e){}
    });
  }
  var picker=$("lang");
  if(picker)picker.value=LANG;
}

function loadDict(code){
  if(code==="en")return Promise.resolve({dict:{},patterns:[]});
  // The head asked for this language's dictionary before the page had
  // finished arriving. Taken once: a reader who then chooses another
  // language is asking a new question and gets a new request.
  var early=window.__boot&&window.__boot.dictionary;
  var got=(early&&window.__boot.lang===code)?early:fetch("i18n/"+code+".json",{cache:"no-cache"});
  if(window.__boot)window.__boot.dictionary=null;
  return got.then(function(r){
    if(!r.ok)throw new Error("no dictionary");
    return r.json();
  }).then(function(data){
    return {dict:data.strings||{}, patterns:data.patterns||[]};
  });
}

var LANG_LISTENERS=[labelTheme];   // the theme button's label, in the language chosen
function onLang(fn){ LANG_LISTENERS.push(fn); }

/* A script the Latin families do not carry, fetched only by the readers who
   need it. IBM Plex Sans JP is the Japanese cut of the body face, drawn to sit
   with it, and Google serves it as a hundred-odd slices keyed by unicode-range
   so a page pulls only the characters it actually sets. Until this, Japanese
   was not typeset at all: it fell through to whatever the reader's system
   happened to offer, which is not a decision, it is the absence of one. */
var SCRIPT_FONTS={ja:"IBM+Plex+Sans+JP:wght@400;600"};
var SCRIPT_LOADED={};
function loadScriptFont(code){
  var want=SCRIPT_FONTS[code];
  if(!want||SCRIPT_LOADED[code])return;
  SCRIPT_LOADED[code]=true;
  var link=document.createElement("link");
  link.rel="stylesheet";
  link.href="https://fonts.googleapis.com/css2?family="+want+"&display=swap";
  document.head.appendChild(link);
}
function setLang(code, first){
  if(!supported(code))code="en";
  loadScriptFont(code);
  try{ localStorage.setItem("clause-lang",code); }catch(e){}
  return loadDict(code).then(function(loaded){
    LANG=code; DICT=loaded.dict; PATTERNS=compilePatterns(loaded.patterns);
  },function(){
    LANG="en"; DICT={}; PATTERNS=[];
  }).then(function(){
    setFormatters();
    translateStatic();
    if(first&&LANG==="en")return;
    LANG_LISTENERS.forEach(function(fn){ try{ fn(); }catch(e){ console.error(e); } });
  });
}

var I18N_READY=(function(){
  var first=pickLang();
  var done=function(){ document.documentElement.classList.remove("i18n-wait"); };
  // Never hold the page hostage to a dictionary: after a second and a half it
  // renders in English and switches when the translation arrives.
  setTimeout(done,1500);
  return setLang(first,true).then(done,done);
})();

(function(){
  var picker=$("lang");
  if(!picker)return;
  picker.innerHTML=LANGS.map(function(l){
    return '<option value="'+l[0]+'">'+esc(l[1])+'</option>';
  }).join("");
  picker.value=LANG;
  picker.addEventListener("change",function(){ setLang(picker.value); });
})();


