"""The live SPA shell served at / by server.py.

A launch console: search any place on Earth, watch the physics compute with
live staged progress, then the 3D forecast loads in-frame. A persistent
live-conditions strip polls current rainfall + river discharge to the second.
Fonts are loaded from the server's /static-free inline block."""

import os


def _fonts():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "assets", "web_cache", "fonts_inline.css")
    with open(p, encoding="utf-8") as f:
        return f.read()


SHELL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin — live flood intelligence</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128167;</text></svg>">
<style>
__FONTS_CSS__
:root {
  --bg0:#04070c; --bg1:#0b111b; --panel:rgba(9,13,20,.92);
  --line:rgba(148,178,215,.12); --line2:rgba(148,178,215,.24);
  --text:#e6edf6; --dim:#8494a9; --dimmer:#71829a;
  --accent:#45cfe9; --accent2:#7c9cf5; --red:#ff5c57; --safe:#4cd97b;
  --orange:#ffab40;
  --fd:"Space Grotesk","Segoe UI",system-ui,sans-serif;
  --fm:"IBM Plex Mono",ui-monospace,Consolas,monospace;
}
*{margin:0;padding:0;box-sizing:border-box;}
html,body{height:100%;overflow:hidden;color:var(--text);font:14px/1.5 var(--fd);
  background:radial-gradient(120% 90% at 70% 8%,var(--bg1),var(--bg0));}
#frame{position:absolute;inset:0;border:0;width:100%;height:100%;
  opacity:0;transition:opacity .6s;}
#frame.on{opacity:1;}

/* top bar */
#topbar{position:absolute;top:0;left:0;right:0;z-index:20;display:flex;
  align-items:center;gap:18px;padding:12px 20px;
  background:linear-gradient(180deg,rgba(4,7,12,.92),rgba(4,7,12,0));
  pointer-events:none;}
#topbar>*{pointer-events:auto;}
#brand{font-size:18px;font-weight:700;letter-spacing:2.5px;white-space:nowrap;}
#brand em{font-style:normal;color:var(--accent);}
#brand small{display:block;font-family:var(--fm);font-size:8px;font-weight:400;
  letter-spacing:2px;color:var(--dimmer);text-transform:uppercase;}
#searchwrap{position:relative;flex:1;max-width:440px;}
#search{width:100%;background:var(--panel);border:1px solid var(--line2);
  border-radius:10px;padding:10px 14px;color:var(--text);font:inherit;
  font-size:14px;backdrop-filter:blur(12px);}
#search::placeholder{color:var(--dimmer);}
#search:focus{outline:2px solid var(--accent);outline-offset:1px;}
#results{position:absolute;top:46px;left:0;right:0;background:var(--panel);
  border:1px solid var(--line2);border-radius:10px;overflow:hidden;
  backdrop-filter:blur(12px);box-shadow:0 12px 40px rgba(0,0,0,.55);
  display:none;z-index:30;}
#results div{padding:9px 14px;cursor:pointer;font-size:13px;
  border-bottom:1px solid var(--line);}
#results div:last-child{border-bottom:0;}
#results div:hover,#results div.sel{background:rgba(69,207,233,.12);
  color:var(--accent);}
#results div small{color:var(--dimmer);font-family:var(--fm);font-size:10px;
  margin-left:6px;}

/* live conditions strip */
#live{display:flex;align-items:center;gap:16px;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;padding:8px 15px;
  backdrop-filter:blur(12px);font-family:var(--fm);font-size:11px;
  white-space:nowrap;}
#live .ld{color:var(--dimmer);font-size:8.5px;letter-spacing:1.4px;
  text-transform:uppercase;}
#live b{color:var(--text);font-weight:600;font-size:13px;
  font-variant-numeric:tabular-nums;}
#live .sep{width:1px;height:26px;background:var(--line);}
#livedot{width:8px;height:8px;border-radius:50%;background:var(--safe);
  box-shadow:0 0 0 0 rgba(76,217,123,.5);animation:lp 2s ease-out infinite;}
#livedot.stale{background:var(--dimmer);animation:none;}
@keyframes lp{0%{box-shadow:0 0 0 0 rgba(76,217,123,.5);}
  100%{box-shadow:0 0 0 8px rgba(76,217,123,0);}}
#clock{color:var(--accent);}

/* presets chips */
#presets{position:absolute;left:20px;bottom:18px;z-index:15;display:flex;
  gap:8px;flex-wrap:wrap;max-width:60%;}
#presets button{background:var(--panel);border:1px solid var(--line);
  color:var(--dim);border-radius:20px;padding:6px 14px;font:inherit;
  font-size:12px;cursor:pointer;backdrop-filter:blur(12px);
  transition:all .15s;}
#presets button:hover{color:var(--text);border-color:var(--accent);}

/* welcome / compute overlay */
#overlay{position:absolute;inset:0;z-index:18;display:flex;align-items:center;
  justify-content:center;background:radial-gradient(120% 90% at 70% 8%,
  var(--bg1),var(--bg0));transition:opacity .5s;}
#overlay.hide{opacity:0;pointer-events:none;}
#ov{width:min(560px,86vw);text-align:center;}
#ov h1{font-size:clamp(30px,5vw,46px);font-weight:700;letter-spacing:5px;
  line-height:1.05;}
#ov h1 em{font-style:normal;color:var(--accent);}
#ov p{color:var(--dim);margin:14px auto 0;max-width:46ch;text-wrap:pretty;
  font-size:15px;}
#ov .earth{font-size:60px;margin-bottom:8px;filter:saturate(.85);}
#prog{margin-top:30px;display:none;}
#progtrack{height:5px;border-radius:3px;background:rgba(148,178,215,.14);
  overflow:hidden;}
#progbar{height:100%;width:0;border-radius:3px;
  background:linear-gradient(90deg,var(--accent),var(--accent2));
  transition:width .5s cubic-bezier(.22,1,.36,1);}
#progstage{font-family:var(--fm);font-size:12px;color:var(--dim);
  margin-top:12px;letter-spacing:.5px;min-height:16px;}
#progstage b{color:var(--accent);font-weight:600;}
#overlay.computing #ov h1,#overlay.computing #ov>p,#overlay.computing .earth{
  opacity:.35;transition:opacity .4s;}
#err{color:var(--red);font-family:var(--fm);font-size:12px;margin-top:14px;
  display:none;}

@media (prefers-reduced-motion:reduce){
  #frame,#overlay,#progbar{transition:none;}#livedot{animation:none;}}
</style>
</head>
<body>
<iframe id="frame" title="3D flood forecast"></iframe>

<div id="topbar">
  <div id="brand">HYDRO<em>TWIN</em>
    <small>live flood intelligence</small></div>
  <div id="searchwrap">
    <input id="search" autocomplete="off" spellcheck="false"
      placeholder="Search any city or lat,lon on Earth  —  e.g. Jakarta">
    <div id="results"></div>
  </div>
  <div id="live">
    <span id="livedot"></span>
    <div><div class="ld">UTC now</div><b id="clock">--:--:--</b></div>
    <div class="sep"></div>
    <div><div class="ld">rain now</div><b id="crain">--</b></div>
    <div class="sep"></div>
    <div><div class="ld">river</div><b id="criver">--</b></div>
    <div class="sep"></div>
    <div><div class="ld">forecast age</div><b id="cage">--</b></div>
  </div>
</div>

<div id="overlay">
  <div id="ov">
    <div class="earth">&#127757;</div>
    <h1>HYDRO<em>TWIN</em></h1>
    <p>Physics-informed flood forecasting for <b>any location on Earth</b>.
      Search a city or coordinates — HydroTwin pulls live terrain, rainfall
      and river-discharge data and simulates the flood in real time.</p>
    <div id="prog">
      <div id="progtrack"><div id="progbar"></div></div>
      <div id="progstage"></div>
    </div>
    <div id="err"></div>
  </div>
</div>

<div id="presets"></div>

<script>
var API = "";
var curLoc = null, issuedAt = null, pollTimer = null, clockTimer = null;

// ---------- live clock + conditions ----------
function pad(n){return ("0"+n).slice(-2);}
function tickClock(){
  var d=new Date();
  document.getElementById("clock").textContent =
    pad(d.getUTCHours())+":"+pad(d.getUTCMinutes())+":"+pad(d.getUTCSeconds());
  if(issuedAt){
    var age=Math.max(0,(Date.now()-issuedAt)/1000);
    var m=Math.floor(age/60), s=Math.floor(age%60);
    document.getElementById("cage").textContent =
      (m>0?m+"m ":"")+s+"s ago";
  }
}
clockTimer=setInterval(tickClock,1000); tickClock();

function pollConditions(){
  if(!curLoc) return;
  fetch(API+"/api/conditions?lat="+curLoc.lat+"&lon="+curLoc.lon)
    .then(function(r){return r.json();})
    .then(function(c){
      var dot=document.getElementById("livedot");
      var rain=c.rain_now_mm_hr;
      document.getElementById("crain").textContent =
        (rain==null?"n/a":rain.toFixed(1)+" mm/h");
      document.getElementById("criver").textContent =
        (c.discharge_m3s==null?"n/a"
          :Math.round(c.discharge_m3s).toLocaleString()+" m³/s");
      dot.className = (rain==null&&c.discharge_m3s==null)?"stale":"";
    })
    .catch(function(){document.getElementById("livedot").className="stale";});
}

// ---------- search ----------
var search=document.getElementById("search");
var results=document.getElementById("results");
var debounce=null, sel=-1, curResults=[];
search.addEventListener("input",function(){
  clearTimeout(debounce);
  var q=search.value.trim();
  if(q.length<2){results.style.display="none";return;}
  debounce=setTimeout(function(){doGeocode(q);},250);
});
search.addEventListener("keydown",function(e){
  if(results.style.display==="none")return;
  if(e.key==="ArrowDown"){sel=Math.min(sel+1,curResults.length-1);paintSel();e.preventDefault();}
  else if(e.key==="ArrowUp"){sel=Math.max(sel-1,0);paintSel();e.preventDefault();}
  else if(e.key==="Enter"){
    if(sel>=0&&curResults[sel])pick(curResults[sel]);
    else if(curResults[0])pick(curResults[0]);
  } else if(e.key==="Escape")results.style.display="none";
});
function doGeocode(q){
  fetch(API+"/api/geocode?q="+encodeURIComponent(q))
    .then(function(r){return r.json();})
    .then(function(d){
      curResults=d.results||[];sel=-1;
      if(!curResults.length){results.style.display="none";return;}
      results.innerHTML="";
      curResults.forEach(function(g,i){
        var div=document.createElement("div");
        div.innerHTML=g.name+(g.population?
          "<small>pop "+Number(g.population).toLocaleString()+"</small>":"");
        div.addEventListener("click",function(){pick(g);});
        results.appendChild(div);
      });
      results.style.display="block";
    }).catch(function(){});
}
function paintSel(){
  [].forEach.call(results.children,function(c,i){
    c.className=i===sel?"sel":"";});
}
document.addEventListener("click",function(e){
  if(!document.getElementById("searchwrap").contains(e.target))
    results.style.display="none";
});

// ---------- simulate a location ----------
function pick(g){
  results.style.display="none"; search.value=g.name;
  runLocation(g.lat,g.lon,g.name,g.pop_density);
}
function runLocation(lat,lon,title,pop){
  var ov=document.getElementById("overlay");
  ov.className="computing"; ov.classList.remove("hide");
  document.getElementById("frame").classList.remove("on");
  document.getElementById("prog").style.display="block";
  document.getElementById("err").style.display="none";
  setProg(3,"contacting server…");
  fetch(API+"/api/simulate",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({lat:lat,lon:lon,title:title,pop_density:pop})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){showErr(d.error);return;}
      pollJob(d.job_id,lat,lon,title);
    }).catch(function(e){showErr(String(e));});
}
function pollJob(jid,lat,lon,title){
  fetch(API+"/api/job/"+jid).then(function(r){return r.json();})
    .then(function(j){
      if(j.error){showErr(j.error);return;}
      setProg(j.pct||0,j.stage||"working…");
      if(j.status==="done"){loadResult(jid,lat,lon,title,j.summary);}
      else setTimeout(function(){pollJob(jid,lat,lon,title);},700);
    }).catch(function(e){showErr(String(e));});
}
function loadResult(jid,lat,lon,title,summary){
  setProg(100,"loading scene…");
  fetch(API+"/api/job/"+jid+"?html=1").then(function(r){return r.json();})
    .then(function(j){
      var frame=document.getElementById("frame");
      frame.onload=function(){
        frame.classList.add("on");
        document.getElementById("overlay").classList.add("hide");
      };
      frame.srcdoc=j.html;
      curLoc={lat:lat,lon:lon};
      issuedAt=summary&&summary.issued_at?Date.parse(summary.issued_at):Date.now();
      if(pollTimer)clearInterval(pollTimer);
      pollConditions(); pollTimer=setInterval(pollConditions,8000);
    }).catch(function(e){showErr(String(e));});
}
function setProg(pct,stage){
  document.getElementById("progbar").style.width=pct+"%";
  document.getElementById("progstage").innerHTML=
    "<b>"+pct+"%</b> &nbsp; "+stage;
}
function showErr(msg){
  var e=document.getElementById("err");
  e.textContent="⚠ "+msg+"  —  try another location or check your connection.";
  e.style.display="block";
  document.getElementById("prog").style.display="none";
}

// ---------- presets ----------
fetch(API+"/api/presets").then(function(r){return r.json();})
  .then(function(list){
    var el=document.getElementById("presets");
    list.forEach(function(p){
      var b=document.createElement("button");
      b.textContent=p.title.split("—")[0].trim();
      b.title=p.title;
      b.addEventListener("click",function(){
        search.value=p.title.split("—")[0].trim();
        runLocation(p.lat,p.lon,p.title,p.pop_density);
      });
      el.appendChild(b);
    });
  }).catch(function(){});

search.focus();
</script>
</body>
</html>
"""
SHELL_HTML = SHELL_HTML.replace("__FONTS_CSS__", _fonts())
