/* ================= pool view ================= */
var height=412000,armed=1284;
function tick(){
  height+=8+Math.floor(Math.random()*5);
  if(Math.random()<.3)armed+=Math.random()<.55?1:-1;
  $("r-height").textContent=f0.format(height);
  $("r-armed").textContent=f0.format(armed);
  $("map-block").textContent=t("block {n}",{n:f0.format(height)});
}
var TICKER=null;
function startTick(){ if(!TICKER){ tick(); TICKER=setInterval(tick,1000); } }
function stopTick(){ if(TICKER){ clearInterval(TICKER); TICKER=null; } }
function fillCapBars(){
  requestAnimationFrame(function(){
    Array.prototype.forEach.call(document.querySelectorAll(".cap-row .fill"),function(f){
      f.style.width=f.dataset.w+"%";
    });
  });
}

var TR=[[26.1,41.7],[28.0,41.98],[31.4,41.1],[35.0,42.0],[38.4,40.9],[41.0,41.5],[43.5,40.9],[44.8,39.7],
  [44.0,37.7],[42.5,37.2],[40.0,36.8],[36.6,36.2],[36.2,36.6],[34.0,36.3],[32.0,36.1],[30.5,36.3],
  [29.0,36.6],[27.3,36.7],[27.2,38.4],[26.2,39.5],[26.2,40.1]];
var BOOK=[{code:"IST-KADIKOY",n:4,limit:180000},{code:"IST-BAKIRKOY",n:3,limit:150000},
  {code:"IZM-KONAK",n:3,limit:140000},{code:"ADY-MERKEZ",n:2,limit:120000},{code:"ANK-CANKAYA",n:3,limit:90000}];
var DEG_Y=340/7,DEG_X=DEG_Y*Math.cos(39*Math.PI/180);
function px(lon){return (lon-25.2)*DEG_X+118;}
function py(lat){return (42.6-lat)*DEG_Y+22;}
function buildMap(){
  var out="",i,j;
  for(i=26;i<=45;i+=4)out+='<line class="grat" x1="'+px(i).toFixed(1)+'" y1="16" x2="'+px(i).toFixed(1)+'" y2="372"/>';
  for(i=36;i<=42;i+=2)out+='<line class="grat" x1="0" y1="'+py(i).toFixed(1)+'" x2="1000" y2="'+py(i).toFixed(1)+'"/>';
  var d="";
  for(i=0;i<TR.length;i++)d+=(i?"L":"M")+px(TR[i][0]).toFixed(1)+" "+py(TR[i][1]).toFixed(1);
  out+='<path class="outline" d="'+d+'Z"/>';
  out+='<circle class="ring" id="ring" cx="0" cy="0" r="0"/><circle class="epi" id="epi" cx="0" cy="0" r="0"/>';
  // A label that would land on one already placed steps down instead. Kadıköy
  // and Bakırköy are the same city: six units apart on this map, with names
  // ninety units long, so side by side they were one smear in every language.
  var placed=[];
  BOOK.forEach(function(e,index){
    var p=PLACES[e.code],cx=px(p.lon),cy=py(p.lat);
    for(j=0;j<e.n;j++){
      var a=(j/e.n)*Math.PI*2+index,ox=Math.cos(a)*(e.n>1?9:0),oy=Math.sin(a)*(e.n>1?9:0);
      out+='<circle class="pt" data-code="'+e.code+'" data-limit="'+e.limit+'" cx="'+(cx+ox).toFixed(1)+
           '" cy="'+(cy+oy).toFixed(1)+'" r="5"/>';
    }
    var lx=cx+14,ly=cy+4,guard=0;
    while(guard++<6&&placed.some(function(q){
      return Math.abs(q.x-lx)<Math.max(q.w,p.name.length*5.6)&&Math.abs(q.y-ly)<11;
    }))ly+=13;
    placed.push({x:lx,y:ly,w:p.name.length*5.6});
    out+='<text class="lbl" x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'">'+esc(p.name.toUpperCase())+'</text>';
  });
  $("map").innerHTML=out;
}
buildMap();
function pushEv(target,text,amount){
  var row=document.createElement("div");
  row.className="ev";
  row.innerHTML='<span class="tag paid">'+esc(t("paid"))+'</span><span>'+t("<b>{place}</b> settled",{place:esc(text)})+'</span><span class="amt">'+esc(amount)+'</span>';
  target.insertBefore(row,target.firstChild);
  while(target.children.length>6)target.removeChild(target.lastChild);
}
$("quake-btn").addEventListener("click",function(){
  var e=PLACES["IST-KADIKOY"],cx=px(e.lon),cy=py(e.lat);
  var ring=$("ring"),epi=$("epi");
  [ring,epi].forEach(function(n){n.setAttribute("cx",cx);n.setAttribute("cy",cy);n.style.transition="none";n.setAttribute("r",0);});
  ring.style.opacity=0; epi.style.opacity=.9;
  void ring.getBoundingClientRect();
  ring.style.transition="r .7s cubic-bezier(.22,1,.36,1), opacity .7s";
  epi.style.transition="r 1.1s ease-out, opacity 1.1s ease-out";
  ring.setAttribute("r",62); ring.style.opacity=1;
  epi.setAttribute("r",150); epi.style.opacity=0;
  var hit=Array.prototype.filter.call(document.querySelectorAll(".pt"),function(n){
    return n.dataset.code==="IST-KADIKOY"||n.dataset.code==="IST-BAKIRKOY";});
  var total=0; $("ev-feed").innerHTML="";
  hit.forEach(function(n,i){
    setTimeout(function(){
      n.classList.add("paid"); n.setAttribute("r",7);
      total+=+n.dataset.limit;
      $("ev-total").textContent=money(total);
      pushEv($("ev-feed"),PLACES[n.dataset.code].name,"+"+money(+n.dataset.limit));
    },300+i*85);
  });
  setTimeout(function(){
    $("ev-sub").textContent=t("{n} policies, one reading, block {block}. No claim was filed.",{n:hit.length,block:f0.format(height)});
  },300+hit.length*85+150);
});
$("reset-btn").addEventListener("click",function(){
  buildMap(); $("ev-total").textContent="0"; $("ev-sub").textContent=t("no event yet"); $("ev-feed").innerHTML="";
});
