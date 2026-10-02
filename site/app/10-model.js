/* ================= the model, ported from clause/ ================= */
var LN=[76.18009172947146,-86.50532032941677,24.01409824083091,-1.231739572450155,0.1208650973866179e-2,-0.5395239384953e-5];
function logGamma(x){var y=x,t=x+5.5;t-=(x+.5)*Math.log(t);var s=1.000000000190015;
  for(var j=0;j<6;j++){y+=1;s+=LN[j]/y;}return -t+Math.log(2.5066282746310005*s/x);}
function lowerGamma(a,x){
  if(x<=0)return 0;
  if(x<a+1){var ap=a,sum=1/a,del=sum;
    for(var n=0;n<400;n++){ap+=1;del*=x/ap;sum+=del;if(Math.abs(del)<Math.abs(sum)*1e-14)break;}
    return sum*Math.exp(-x+a*Math.log(x)-logGamma(a));}
  var tiny=1e-300,b=x+1-a,c=1/tiny,d=1/b,h=d;
  for(var i=1;i<400;i++){var an=-i*(i-a);b+=2;d=an*d+b;if(Math.abs(d)<tiny)d=tiny;
    c=b+an/c;if(Math.abs(c)<tiny)c=tiny;d=1/d;var dl=d*c;h*=dl;if(Math.abs(dl-1)<1e-14)break;}
  return 1-Math.exp(-x+a*Math.log(x)-logGamma(a))*h;}
function gammaCdf(x,shape,scale){return x<=0?0:lowerGamma(shape,x/scale);}
function erf(z){var s=z<0?-1:1;z=Math.abs(z);var t=1/(1+.3275911*z);
  return s*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-z*z));}
function normalCdf(x,mu,sg){return .5*(1+erf((x-mu)/(sg*Math.SQRT2)));}

var PLACES={
  "IST-KADIKOY":{name:"Istanbul, Kadıköy",zone:"TR-MARMARA",lat:40.99,lon:29.03,bg:1.55,cm:7.2,cr:88,fd:18},
  "IST-BAKIRKOY":{name:"Istanbul, Bakırköy",zone:"TR-MARMARA",lat:40.98,lon:28.87,bg:1.62,cm:7.2,cr:88,fd:14},
  "IZM-KONAK":{name:"İzmir, Konak",zone:"TR-AEGEAN",lat:38.42,lon:27.13,bg:2.40,cm:6.9,cr:210,fd:32},
  "ADY-MERKEZ":{name:"Adıyaman",zone:"TR-EAST",lat:37.76,lon:38.28,bg:1.10,cm:7.4,cr:140,fd:26},
  "ANK-CANKAYA":{name:"Ankara, Çankaya",zone:"TR-CENTRAL",lat:39.90,lon:32.85,bg:.18,cm:null,cr:null,fd:null}};
var STATIONS={"TR-EDIRNE":{"name":"Edirne","lat":41.68,"lon":26.56,"season":"April to August","opens":[4,1],"window":150,"normal":189.5,"cv":0.249},"TR-KIRKLARELI":{"name":"Kırklareli","lat":41.74,"lon":27.22,"season":"April to August","opens":[4,1],"window":150,"normal":167.4,"cv":0.316},"TR-TEKIRDAG":{"name":"Tekirdağ","lat":40.98,"lon":27.51,"season":"April to August","opens":[4,1],"window":150,"normal":153.5,"cv":0.352},"TR-BALIKESIR":{"name":"Balıkesir","lat":39.65,"lon":27.89,"season":"April to August","opens":[4,1],"window":150,"normal":133.7,"cv":0.365},"TR-BURSA":{"name":"Bursa","lat":40.19,"lon":29.06,"season":"April to August","opens":[4,1],"window":150,"normal":162.9,"cv":0.35},"TR-CANAKKALE":{"name":"Çanakkale","lat":40.15,"lon":26.41,"season":"April to August","opens":[4,1],"window":150,"normal":122.6,"cv":0.384},"TR-SAKARYA":{"name":"Sakarya","lat":40.78,"lon":30.4,"season":"April to August","opens":[4,1],"window":150,"normal":236.6,"cv":0.395},"TR-IZMIR":{"name":"İzmir","lat":38.42,"lon":27.14,"season":"April to August","opens":[4,1],"window":150,"normal":94.4,"cv":0.401},"TR-MANISA":{"name":"Manisa","lat":38.62,"lon":27.43,"season":"April to August","opens":[4,1],"window":150,"normal":107.2,"cv":0.383},"TR-AYDIN":{"name":"Aydın","lat":37.85,"lon":27.84,"season":"April to August","opens":[4,1],"window":150,"normal":127.5,"cv":0.371},"TR-DENIZLI":{"name":"Denizli","lat":37.78,"lon":29.09,"season":"April to August","opens":[4,1],"window":150,"normal":162.8,"cv":0.279},"TR-MUGLA":{"name":"Muğla","lat":37.22,"lon":28.36,"season":"April to August","opens":[4,1],"window":150,"normal":97.8,"cv":0.417},"TR-USAK":{"name":"Uşak","lat":38.68,"lon":29.41,"season":"April to August","opens":[4,1],"window":150,"normal":163.1,"cv":0.288},"TR-AFYON":{"name":"Afyonkarahisar","lat":38.76,"lon":30.54,"season":"April to August","opens":[4,1],"window":150,"normal":168.5,"cv":0.324},"TR-KUTAHYA":{"name":"Kütahya","lat":39.42,"lon":29.99,"season":"April to August","opens":[4,1],"window":150,"normal":167.4,"cv":0.302},"TR-ADANA":{"name":"Çukurova","lat":37,"lon":35.33,"season":"March to July","opens":[3,1],"window":140,"normal":191.3,"cv":0.273},"TR-MERSIN":{"name":"Mersin","lat":36.81,"lon":34.64,"season":"March to July","opens":[3,1],"window":140,"normal":138.1,"cv":0.314},"TR-HATAY":{"name":"Hatay","lat":36.2,"lon":36.16,"season":"March to July","opens":[3,1],"window":140,"normal":149.8,"cv":0.293},"TR-ANTALYA":{"name":"Antalya","lat":36.9,"lon":30.69,"season":"March to July","opens":[3,1],"window":140,"normal":191.1,"cv":0.41},"TR-ISPARTA":{"name":"Isparta","lat":37.77,"lon":30.55,"season":"April to August","opens":[4,1],"window":150,"normal":163.3,"cv":0.251},"TR-BURDUR":{"name":"Burdur","lat":37.72,"lon":30.29,"season":"April to August","opens":[4,1],"window":150,"normal":149.4,"cv":0.264},"TR-KMARAS":{"name":"Kahramanmaraş","lat":37.58,"lon":36.93,"season":"March to July","opens":[3,1],"window":140,"normal":159.2,"cv":0.344},"TR-OSMANIYE":{"name":"Osmaniye","lat":37.07,"lon":36.25,"season":"March to July","opens":[3,1],"window":140,"normal":186,"cv":0.282},"TR-KONYA":{"name":"Konya Plain","lat":37.87,"lon":32.48,"season":"April to August","opens":[4,1],"window":150,"normal":114.6,"cv":0.347},"TR-ANKARA":{"name":"Ankara","lat":39.93,"lon":32.86,"season":"April to August","opens":[4,1],"window":150,"normal":164.1,"cv":0.295},"TR-ESKISEHIR":{"name":"Eskişehir","lat":39.78,"lon":30.52,"season":"April to August","opens":[4,1],"window":150,"normal":177.9,"cv":0.341},"TR-KAYSERI":{"name":"Kayseri","lat":38.73,"lon":35.49,"season":"April to August","opens":[4,1],"window":150,"normal":137.8,"cv":0.275},"TR-SIVAS":{"name":"Sivas","lat":39.75,"lon":37.02,"season":"April to August","opens":[4,1],"window":150,"normal":175.3,"cv":0.243},"TR-YOZGAT":{"name":"Yozgat","lat":39.82,"lon":34.81,"season":"April to August","opens":[4,1],"window":150,"normal":185.1,"cv":0.244},"TR-AKSARAY":{"name":"Aksaray","lat":38.37,"lon":34.03,"season":"April to August","opens":[4,1],"window":150,"normal":122.9,"cv":0.284},"TR-NIGDE":{"name":"Niğde","lat":37.97,"lon":34.68,"season":"April to August","opens":[4,1],"window":150,"normal":118.3,"cv":0.248},"TR-NEVSEHIR":{"name":"Nevşehir","lat":38.62,"lon":34.71,"season":"April to August","opens":[4,1],"window":150,"normal":136.5,"cv":0.259},"TR-KIRSEHIR":{"name":"Kırşehir","lat":39.15,"lon":34.16,"season":"April to August","opens":[4,1],"window":150,"normal":139.8,"cv":0.258},"TR-KARAMAN":{"name":"Karaman","lat":37.18,"lon":33.22,"season":"April to August","opens":[4,1],"window":150,"normal":88.9,"cv":0.457},"TR-CANKIRI":{"name":"Çankırı","lat":40.6,"lon":33.62,"season":"April to August","opens":[4,1],"window":150,"normal":194.1,"cv":0.253},"TR-SANLIURFA":{"name":"Şanlıurfa","lat":37.16,"lon":38.79,"season":"March to July","opens":[3,1],"window":140,"normal":120.4,"cv":0.464},"TR-DIYARBAKIR":{"name":"Diyarbakır","lat":37.91,"lon":40.24,"season":"March to July","opens":[3,1],"window":140,"normal":186.6,"cv":0.346},"TR-GAZIANTEP":{"name":"Gaziantep","lat":37.07,"lon":37.38,"season":"March to July","opens":[3,1],"window":140,"normal":139.5,"cv":0.388},"TR-MARDIN":{"name":"Mardin","lat":37.31,"lon":40.74,"season":"March to July","opens":[3,1],"window":140,"normal":147.9,"cv":0.377},"TR-ADIYAMAN":{"name":"Adıyaman","lat":37.76,"lon":38.28,"season":"March to July","opens":[3,1],"window":140,"normal":151.3,"cv":0.373},"TR-BATMAN":{"name":"Batman","lat":37.88,"lon":41.13,"season":"March to July","opens":[3,1],"window":140,"normal":203.7,"cv":0.302},"TR-SIIRT":{"name":"Siirt","lat":37.93,"lon":41.94,"season":"March to July","opens":[3,1],"window":140,"normal":211.9,"cv":0.284},"TR-KILIS":{"name":"Kilis","lat":36.72,"lon":37.12,"season":"March to July","opens":[3,1],"window":140,"normal":149.6,"cv":0.314},"TR-MALATYA":{"name":"Eastern Anatolia","lat":38.36,"lon":38.31,"season":"April to August","opens":[4,1],"window":150,"normal":105.4,"cv":0.335},"TR-ELAZIG":{"name":"Elazığ","lat":38.68,"lon":39.22,"season":"April to August","opens":[4,1],"window":150,"normal":126,"cv":0.358},"TR-ERZURUM":{"name":"Erzurum","lat":39.9,"lon":41.27,"season":"April to August","opens":[4,1],"window":150,"normal":224.3,"cv":0.27},"TR-VAN":{"name":"Van","lat":38.49,"lon":43.38,"season":"April to August","opens":[4,1],"window":150,"normal":132,"cv":0.304},"TR-MUS":{"name":"Muş","lat":38.73,"lon":41.49,"season":"April to August","opens":[4,1],"window":150,"normal":156.6,"cv":0.385},"TR-AGRI":{"name":"Ağrı","lat":39.72,"lon":43.05,"season":"April to August","opens":[4,1],"window":150,"normal":173.4,"cv":0.289},"TR-SAMSUN":{"name":"Samsun","lat":41.29,"lon":36.33,"season":"April to August","opens":[4,1],"window":150,"normal":169.2,"cv":0.325},"TR-TOKAT":{"name":"Tokat","lat":40.31,"lon":36.55,"season":"April to August","opens":[4,1],"window":150,"normal":190.9,"cv":0.23},"TR-CORUM":{"name":"Çorum","lat":40.55,"lon":34.95,"season":"April to August","opens":[4,1],"window":150,"normal":196.9,"cv":0.253},"TR-AMASYA":{"name":"Amasya","lat":40.65,"lon":35.83,"season":"April to August","opens":[4,1],"window":150,"normal":189,"cv":0.248},"TR-ORDU":{"name":"Ordu","lat":40.98,"lon":37.88,"season":"April to August","opens":[4,1],"window":150,"normal":304.1,"cv":0.255},"TR-TRABZON":{"name":"Trabzon","lat":41,"lon":39.72,"season":"April to August","opens":[4,1],"window":150,"normal":250.2,"cv":0.215},"TR-DUZCE":{"name":"Düzce","lat":40.84,"lon":31.16,"season":"April to August","opens":[4,1],"window":150,"normal":260,"cv":0.353},"TR-BOLU":{"name":"Bolu","lat":40.74,"lon":31.61,"season":"April to August","opens":[4,1],"window":150,"normal":221,"cv":0.293},"TR-KASTAMONU":{"name":"Kastamonu","lat":41.39,"lon":33.78,"season":"April to August","opens":[4,1],"window":150,"normal":235.4,"cv":0.28}};
var ROUTES={
  "TK-IST-LHR":{carrier:"Turkish Airlines",from:"Istanbul",to:"London",cancel:.012,late:.243,median:41},
  "TK-IST-JFK":{carrier:"Turkish Airlines",from:"Istanbul",to:"New York",cancel:.009,late:.281,median:52},
  "TK-IST-AMS":{carrier:"Turkish Airlines",from:"Istanbul",to:"Amsterdam",cancel:.014,late:.262,median:44},
  "PC-SAW-ESB":{carrier:"Pegasus",from:"Istanbul Sabiha",to:"Ankara",cancel:.018,late:.197,median:33},
  "LH-FRA-IST":{carrier:"Lufthansa",from:"Frankfurt",to:"Istanbul",cancel:.011,late:.221,median:38},
  "BA-LHR-IST":{carrier:"British Airways",from:"London",to:"Istanbul",cancel:.016,late:.254,median:46}};
var ANCHOR=4,BG_MAX=6.6,REF_R=50,CHAR_HALF=.25,CANCEL_MIN=1440,LOG_SIGMA=.86;
var SOLVENCY=.995,COST_OF_CAPITAL=.12,EXPENSE=.08;

function droughtExc(code){var s=STATIONS[code],shape=1/(s.cv*s.cv),scale=s.normal/shape;
  return function(mm){return mm<=0?0:gammaCdf(mm,shape,scale);};}
/* Published on-time performance exists for a handful of routes and people fly
   all of them, so most flights are priced on what routes of that length do.
   The bands are the protocol's, kept here so the page can show a figure before
   the protocol answers; the protocol's own price replaces it when it does. */
var SECTOR_BANDS=[[1500,.016,.22,33],[4000,.013,.25,40],[8000,.010,.28,50],[Infinity,.008,.30,58]];
function routeStats(key,km){
  var known=ROUTES[key];
  if(known)return known;
  var d=(km===undefined||km===null)?2000:km;
  for(var i=0;i<SECTOR_BANDS.length;i++)
    if(d<=SECTOR_BANDS[i][0])
      return {cancel:SECTOR_BANDS[i][1],late:SECTOR_BANDS[i][2],median:SECTOR_BANDS[i][3]};
  return {cancel:.008,late:.30,median:58};
}
function flightExc(key,km){var r=routeStats(key,km),mu=Math.log(r.median);
  return function(x){if(x<=0)return 1;if(x>=CANCEL_MIN)return r.cancel;
    return r.cancel+(1-r.cancel)*r.late*(1-normalCdf(Math.log(x),mu,LOG_SIGMA));};}

var CURVES={quake:{shape:"step",pts:[[5.5,.25],[6.5,.60],[7.0,1]]},
            shake:{shape:"step",pts:[[7.0,.35],[8.0,.75],[9.0,1]]},
            drought:{shape:"ramp",pts:[[.80,0],[.60,.50],[.40,1]]},
            flight:{shape:"step",pts:[[120,.30],[240,.70],[1440,1]]}};
function levelForShare(c,s){var p=c.pts,i;
  if(c.shape==="step"){for(i=0;i<p.length;i++)if(p[i][1]>=s-1e-12)return p[i][0];return p[p.length-1][0];}
  var pl=p[0][0],ps=p[0][1];
  for(i=0;i<p.length;i++){if(p[i][1]>=s-1e-12&&p[i][1]>ps){var f=(s-ps)/(p[i][1]-ps);return pl+(p[i][0]-pl)*f;}
    pl=p[i][0];ps=p[i][1];}
  return p[p.length-1][0];}
function shareAt(c,level){var p=c.pts,i,sh=0;
  if(c.shape==="step"){for(i=0;i<p.length;i++)if(level>=p[i][0])sh=p[i][1];return sh;}
  if(level>=p[0][0])return 0;
  for(i=1;i<p.length;i++){if(level>=p[i][0]){var f=(p[i-1][0]-level)/(p[i-1][0]-p[i][0]);
    return p[i-1][1]+(p[i][1]-p[i-1][1])*f;}}
  return 1;}
function priceIt(curve,exc,limit,days){
  var N=900,q=1-SOLVENCY,i,ys=new Float64Array(N),S=new Float64Array(N);
  for(i=0;i<N;i++){var s=(i+1)/N;ys[i]=s*limit;S[i]=Math.min(1,Math.max(0,exc(levelForShare(curve,s))));}
  var el=0,prev=0;
  for(i=0;i<N;i++){el+=S[i]*(ys[i]-prev);prev=ys[i];}
  var v=limit;
  for(i=0;i<N;i++)if(S[i]<=q){v=ys[i];break;}
  var integral=0;prev=v;
  for(i=0;i<N;i++){if(ys[i]<=v)continue;integral+=S[i]*(ys[i]-prev);prev=ys[i];}
  var tvar=Math.min(limit,v+integral/q),capital=Math.max(0,tvar-el);
  /* The cost of holding the capital, and nothing cheaper. This used to take
     the lesser of that and a reinsurer's price at three times expected loss,
     which for a catastrophe always won and capped every premium at 3.08 times
     expected loss. The protocol stopped doing that -- no treaty exists, so
     there is nothing to cede to and no cheaper branch to take -- and this line
     went on doing it, which is a second reason the two numbers differed. */
  var years=days/365.25,rl=capital*COST_OF_CAPITAL*years,ex=el*EXPENSE;
  return {el:el,capital:capital,riskLoad:rl,expenses:ex,premium:el+rl+ex,trigger:S[0]};
}

