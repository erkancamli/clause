/* ================= formatting ================= */
var f0, f1, f2, fLevel;
/* Numbers in the reader's convention: 1,000.50 here, 1.000,50 in German. */
function setFormatters(){
  var locale=LOCALES[LANG]||"en-US";
  f0=new Intl.NumberFormat(locale,{maximumFractionDigits:0});
  f2=new Intl.NumberFormat(locale,{minimumFractionDigits:2,maximumFractionDigits:2});
  f1=new Intl.NumberFormat(locale,{maximumFractionDigits:1});
  /* A level on a peril's scale, which is always written to one decimal.

     f1 drops a trailing zero, because it is the general one-decimal format
     and most of its sixty-odd uses are ratios and percentages where 7 is the
     right answer. A level is not one of those. The magnitude ladder read "A
     magnitude 6.5 to 7" and "A magnitude 7 or more" beside a summary row
     reading "M7.0": two spellings of one number, adjacent, on the screen
     where the money moves.

     rungWords wrote the magnitude with toFixed(1), which keeps the zero and
     loses the reader's own decimal mark: a Turkish reader was shown M5.2
     where every other number on the page is written 5,2. This does both. */
  fLevel=new Intl.NumberFormat(locale,{minimumFractionDigits:1,maximumFractionDigits:1});
}
setFormatters();
function money(v){return v>=1000?f0.format(Math.round(v)):f2.format(v);}
function pct(v,d){
  d=d===undefined?2:d;
  try{ return new Intl.NumberFormat(LOCALES[LANG]||"en-US",
         {style:"percent",minimumFractionDigits:d,maximumFractionDigits:d}).format(v); }
  catch(e){ return (v*100).toFixed(d)+"%"; }
}
/* "a, b and c" in the reader's own grammar. */
function listText(items){
  try{ return new Intl.ListFormat(LOCALES[LANG]||"en-US",{type:"conjunction"}).format(items); }
  catch(e){ return items.join(", "); }
}
function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}


