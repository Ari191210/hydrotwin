"""Doorstep forecast: one offline page that turns a forecast river level at
the Old Railway Bridge into "which neighbourhoods, how deep", with a
plain-language message in Hindi and English.

    python doorstep.py            # writes outputs/doorstep.html

Built from the stage library (stagelib.py). The page does no simulation:
it interpolates between the library's steady, river-only depth fields.
"""

import base64
import io
import json
import math
import os

import numpy as np

import config
import imagery
import localities
import score_localities
import stagelib
import terrain

HERE = os.path.dirname(os.path.abspath(__file__))
# levels at the Old Railway Bridge, metres (Delhi Flood Control Order marks
# and the two record floods)
MARKS = [
    (206.00, "Evacuation mark"),
    (207.49, "1978 record"),
    (208.66, "2023 record"),
]
MIN_STAGE = 206.0     # below this the model's level scale is not trusted


def build(dem="srtm", path="outputs/doorstep.html"):
    lib = stagelib.Library(dem)
    config.set_case("delhi")
    rows, cols = lib.elevation.shape
    keep = lib.stage >= MIN_STAGE - 0.6
    stages = lib.stage[keep]
    depths = lib.depths[keep]
    north = np.stack([np.flipud(d) for d in depths])
    depth_b64 = base64.b64encode(
        np.clip(north * 100, 0, 65535).astype("<u2").tobytes()).decode()
    mask_b64 = base64.b64encode(
        np.flipud(lib.mask).astype(np.uint8).tobytes()).decode()

    sat = imagery.get_imagery(rows, cols)
    if sat is None:
        raise RuntimeError("no satellite imagery cached for Delhi")
    from PIL import Image
    buf = io.BytesIO()
    sat.convert("RGB").resize((1080, 1080), Image.LANCZOS).save(
        buf, format="JPEG", quality=82)
    sat_uri = "data:image/jpeg;base64," + base64.b64encode(
        buf.getvalue()).decode()

    places = []
    for name, lat, lon, label, src in localities.LOCALITIES:
        r, c = terrain.latlon_to_rc(lat, lon, rows, cols)
        places.append({"name": name, "row": rows - 1 - r, "col": c,
                       "label": label, "source": src})

    test = score_localities.score(dem, quiet=True)
    fonts = open(os.path.join(HERE, "assets", "web_cache",
                              "fonts_inline.css"), encoding="utf-8").read()
    payload = {
        "rows": rows, "cols": cols, "cell": lib.cell,
        "radiusCells": max(1, math.ceil(250.0 / lib.cell)),
        "stages": [round(float(s), 3) for s in stages],
        "minStage": MIN_STAGE,
        "maxStage": round(float(stages[-1]) - 0.01, 2),
        "marks": [{"m": m, "label": l} for m, l in MARKS],
        "places": places, "source": lib.source,
        "test": {"hits": test["model"]["hits"],
                 "falseAlarms": test["model"]["false_alarms"],
                 "tubHits": test["bathtub"]["hits"],
                 "tubFalse": test["bathtub"]["false_alarms"]},
    }
    html = (_TEMPLATE.replace("__FONTS__", fonts)
            .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
            .replace("__DEPTHS__", depth_b64).replace("__MASK__", mask_b64)
            .replace("__SAT__", sat_uri))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[doorstep] saved {path} ({len(html) // 1024} KB, "
          f"{len(stages)} levels {stages[0]:.2f}-{stages[-1]:.2f} m, "
          f"{len(places)} localities)")
    return path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin Doorstep: Yamuna level to neighbourhoods</title>
<style>
__FONTS__
:root { --bg:#070b12; --panel:#0d131d; --line:rgba(148,178,215,.14);
  --text:#e9eff7; --dim:#93a2b7; --dimmer:#6f8098; --accent:#45cfe9;
  --water:#2f8cff; --red:#ff6a63; --amber:#ffb454; --safe:#4cd97b;
  --fd:"Space Grotesk","Segoe UI",system-ui,sans-serif;
  --fm:"IBM Plex Mono",ui-monospace,Consolas,monospace; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font:15px/1.5 var(--fd);
  min-height:100vh; }
a { color:var(--accent); }
header { padding:22px 28px 0; display:flex; align-items:baseline; gap:16px;
  flex-wrap:wrap; }
header h1 { font-size:20px; letter-spacing:3px; font-weight:700; }
header h1 em { font-style:normal; color:var(--accent); }
header span { color:var(--dim); font-size:13px; }
header a { margin-left:auto; font-size:13px; text-decoration:none; }
main { display:grid; grid-template-columns:minmax(0,1fr) 400px; gap:22px;
  padding:18px 28px 28px; max-width:1500px; margin:0 auto; }
.ask { grid-column:1 / -1; background:var(--panel); border:1px solid var(--line);
  border-radius:16px; padding:22px 26px 20px; }
.ask h2 { font-size:clamp(22px,3vw,34px); font-weight:600; line-height:1.2;
  letter-spacing:-.4px; }
.ask h2 b { color:var(--accent); font-variant-numeric:tabular-nums;
  font-weight:700; white-space:nowrap; }
.ask p { color:var(--dim); margin-top:6px; max-width:78ch; font-size:14px; }
.slider { margin-top:18px; position:relative; padding-bottom:30px; }
input[type=range] { width:100%; accent-color:var(--accent); height:28px;
  cursor:pointer; }
.ticks { position:absolute; left:0; right:0; top:30px; height:26px; }
.ticks button { position:absolute; transform:translateX(-50%);
  background:none; border:0; color:var(--dim); font:11px var(--fm);
  cursor:pointer; white-space:nowrap; padding:4px 6px; border-radius:6px; }
.ticks button:hover { color:var(--text); background:rgba(255,255,255,.06); }
.ticks button::before { content:""; position:absolute; left:50%; top:-6px;
  width:1px; height:7px; background:var(--dimmer); }
.sum { display:flex; gap:26px; margin-top:8px; flex-wrap:wrap; }
.sum div b { display:block; font:600 24px var(--fm);
  font-variant-numeric:tabular-nums; }
.sum div span { font:10px var(--fm); letter-spacing:1.4px;
  text-transform:uppercase; color:var(--dimmer); }
.sum .hot b { color:var(--red); }
.map { position:relative; border-radius:16px; overflow:hidden;
  border:1px solid var(--line); background:#000; align-self:start; }
.map canvas { width:100%; height:auto; display:block; }
.map .cap { position:absolute; left:12px; bottom:10px; font:10.5px var(--fm);
  color:#dbe6f2; background:rgba(4,7,12,.72); padding:4px 9px;
  border-radius:6px; }
.map .north { position:absolute; right:12px; top:10px; font:11px var(--fm);
  color:#dbe6f2; background:rgba(4,7,12,.72); padding:3px 8px;
  border-radius:6px; }
aside { display:flex; flex-direction:column; gap:14px; min-width:0; }
.card { background:var(--panel); border:1px solid var(--line);
  border-radius:16px; padding:16px 18px; }
.card h3 { font:600 10.5px var(--fm); letter-spacing:1.8px;
  text-transform:uppercase; color:var(--dimmer); margin-bottom:10px; }
.place { display:flex; align-items:center; gap:10px; width:100%;
  background:none; border:0; border-top:1px solid var(--line);
  color:inherit; font:inherit; text-align:left; padding:9px 4px;
  cursor:pointer; border-radius:0; }
.place:first-of-type { border-top:0; }
.place:hover, .place.on { background:rgba(69,207,233,.07); }
.place i { width:9px; height:9px; border-radius:50%; flex-shrink:0;
  background:var(--dimmer); }
.place.wet i { background:var(--red); box-shadow:0 0 0 4px rgba(255,106,99,.18); }
.place .n { flex:1; min-width:0; font-weight:500; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.place .d { font:12px var(--fm); color:var(--dim); white-space:nowrap; }
.place.wet .d { color:var(--red); font-weight:600; }
.msg { border-color:rgba(69,207,233,.35); }
.msg p { font-size:15px; }
.msg .hi { font-size:17px; line-height:1.6; margin-bottom:10px; }
.msg .en { color:var(--dim); font-size:13.5px; }
.msg button { margin-top:12px; background:rgba(69,207,233,.12);
  border:1px solid var(--accent); color:var(--accent); font:600 11px var(--fm);
  letter-spacing:.8px; padding:8px 12px; border-radius:8px; cursor:pointer; }
.msg button:hover { background:rgba(69,207,233,.22); }
.note { font-size:12.5px; color:var(--dim); }
.note b { color:var(--text); }
.note li { margin:5px 0 5px 16px; }
@media (max-width:980px) { main { grid-template-columns:1fr; padding:14px; }
  header { padding:16px 14px 0; } }
</style>
</head>
<body>
<header>
  <h1>HYDRO<em>TWIN</em> DOORSTEP</h1>
  <span>From a river level to your neighbourhood. Delhi, Yamuna.</span>
  <a href="index.html">&larr; all simulations</a>
</header>
<main>
  <section class="ask">
    <h2>If the Yamuna reaches <b id="lvl"></b> at the Old Railway Bridge</h2>
    <p>Official flood warnings give one number: the river level at this
      bridge. Drag the level and see what it means street by street.</p>
    <div class="slider">
      <input type="range" id="stage" step="0.01"
        aria-label="Forecast river level at the Old Railway Bridge, metres">
      <div class="ticks" id="ticks"></div>
    </div>
    <div class="sum">
      <div class="hot"><b id="nwet">0</b><span>places with water</span></div>
      <div><b id="area">0</b><span>km&sup2; under water beyond the river</span></div>
      <div><b id="deep">0</b><span>deepest near a listed place</span></div>
    </div>
  </section>
  <div class="map">
    <canvas id="cv" width="1080" height="1080"></canvas>
    <div class="north">N &uarr;</div>
    <div class="cap" id="cap"></div>
  </div>
  <aside>
    <div class="card msg" id="msg" hidden>
      <h3 id="msgHead">Message</h3>
      <p class="hi" id="msgHi" lang="hi"></p>
      <p class="en" id="msgEn"></p>
      <button id="copy">COPY THE HINDI MESSAGE</button>
    </div>
    <div class="card">
      <h3>Neighbourhoods (tap one for a message)</h3>
      <div id="list"></div>
    </div>
    <div class="card note">
      <h3>How far to trust this</h3>
      <ul>
        <li><b>Tested at one level only.</b> Lower levels are untested,
          and the model's level scale is least reliable near the bottom of
          the slider. At the 2023 record level it flags
          <span id="tHits"></span> of 7 places recorded as submerged, with
          <span id="tFalse"></span> false alarms among 10 places with no
          flood report. A rule of "everything below the water level floods"
          gets <span id="bHits"></span> of 7 with <span id="bFalse"></span>
          false alarms.</li>
        <li><b>River only.</b> No drains and no rain. Places flooded through
          drains in 2023 (ITO, Raj Ghat) stay dry here.</li>
        <li><b>Embankments are too thin for this map.</b> East-bank
          colonies behind them may show water they would not get.</li>
        <li><b>Not an official warning.</b> Follow the district
          administration. Depths are "up to", within 250 m.</li>
      </ul>
    </div>
  </aside>
</main>
<script>
var P = __PAYLOAD__;
function b64(s) { var b = atob(s), a = new Uint8Array(b.length);
  for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a; }
var N = P.rows * P.cols;
var D = new Uint16Array(b64("__DEPTHS__").buffer);
var MASK = b64("__MASK__");
var sat = new Image(); sat.src = "__SAT__";
var cv = document.getElementById("cv"), g = cv.getContext("2d");
var small = document.createElement("canvas");
small.width = P.cols; small.height = P.rows;
var sg = small.getContext("2d"), img = sg.createImageData(P.cols, P.rows);
var depth = new Float32Array(N), sel = -1;
var slider = document.getElementById("stage");
slider.min = P.minStage; slider.max = P.maxStage; slider.value = 208.66;

var WORDS = [
  [1.5, "over head height", "सिर से ऊपर"],
  [1.0, "chest-deep", "सीने तक"],
  [0.6, "waist-deep", "कमर तक"],
  [0.3, "knee-deep", "घुटनों तक"]];
function word(d) { for (var i = 0; i < WORDS.length; i++)
  if (d >= WORDS[i][0]) return WORDS[i]; return null; }

function interp(stage) {
  var s = P.stages, i = 1;
  while (i < s.length - 1 && s[i] < stage) i++;
  var w = Math.max(0, Math.min(1, (stage - s[i - 1]) / (s[i] - s[i - 1])));
  var a = (i - 1) * N, b = i * N;
  for (var k = 0; k < N; k++)
    depth[k] = (D[a + k] * (1 - w) + D[b + k] * w) / 100;
}
function placeDepth(p) {
  var m = 0, R = P.radiusCells;
  for (var r = Math.max(0, p.row - R); r <= Math.min(P.rows - 1, p.row + R); r++)
    for (var c = Math.max(0, p.col - R); c <= Math.min(P.cols - 1, p.col + R); c++) {
      var k = r * P.cols + c;
      if (!MASK[k] && depth[k] > m) m = depth[k];
    }
  return m;
}
function draw() {
  var stage = +slider.value;
  interp(stage);
  var wetCells = 0;
  for (var k = 0; k < N; k++) {
    var d = depth[k], o = k * 4;
    if (d >= 0.05) {
      var t = Math.min(d / 5, 1);
      img.data[o] = 60 - 45 * t; img.data[o + 1] = 160 - 100 * t;
      img.data[o + 2] = 255 - 60 * t;
      img.data[o + 3] = MASK[k] ? 110 : 205;
      if (d >= 0.3 && !MASK[k]) wetCells++;
    } else img.data[o + 3] = 0;
  }
  sg.putImageData(img, 0, 0);
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
  g.drawImage(sat, 0, 0, cv.width, cv.height);
  g.fillStyle = "rgba(4,8,14,.28)"; g.fillRect(0, 0, cv.width, cv.height);
  g.drawImage(small, 0, 0, cv.width, cv.height);

  var sx = cv.width / P.cols, sy = cv.height / P.rows, deepest = 0, nwet = 0;
  var rowsHtml = [];
  P.places.forEach(function (p, i) {
    p.d = placeDepth(p); p.wet = p.d >= 0.3;
    if (p.wet) nwet++; if (p.d > deepest) deepest = p.d;
  });
  var order = P.places.map(function (p, i) { return i; })
    .sort(function (a, b) { return P.places[b].d - P.places[a].d; });
  order.forEach(function (i) {
    var p = P.places[i], w = word(p.d);
    rowsHtml.push("<button class='place" + (p.wet ? " wet" : "") +
      (i === sel ? " on" : "") + "' data-i='" + i + "'><i></i><span class='n'>" +
      p.name + "</span><span class='d'>" +
      (p.wet ? w[1] + " &middot; up to " + p.d.toFixed(1) + " m" : "dry") +
      "</span></button>");
  });
  document.getElementById("list").innerHTML = rowsHtml.join("");
  P.places.forEach(function (p, i) {
    var x = (p.col + .5) * sx, y = (p.row + .5) * sy;
    g.beginPath(); g.arc(x, y, i === sel ? 13 : 8, 0, 6.3);
    g.fillStyle = p.wet ? "#ff6a63" : "rgba(233,239,247,.9)"; g.fill();
    g.lineWidth = 3; g.strokeStyle = "rgba(4,8,14,.85)"; g.stroke();
    if (i === sel || p.wet) {
      g.font = "600 21px 'Space Grotesk', sans-serif";
      var tw = g.measureText(p.name).width, lx = x + 16;
      if (lx + tw + 12 > cv.width) lx = x - 16 - tw - 12;
      g.fillStyle = "rgba(4,8,14,.78)";
      g.fillRect(lx, y - 15, tw + 12, 30);
      g.fillStyle = "#fff"; g.fillText(p.name, lx + 6, y + 7);
    }
  });
  document.getElementById("lvl").textContent = stage.toFixed(2) + " m";
  document.getElementById("nwet").textContent = nwet + " of " + P.places.length;
  document.getElementById("area").textContent =
    (wetCells * P.cell * P.cell / 1e6).toFixed(1);
  document.getElementById("deep").textContent = deepest.toFixed(1) + " m";
  var near = "";
  P.marks.forEach(function (m) {
    if (Math.abs(m.m - stage) < 0.02) near = " (" + m.label + ")"; });
  document.getElementById("cap").textContent =
    "Model water at " + stage.toFixed(2) + " m" + near +
    " · river only · " + P.source;
  message();
}
function message() {
  var box = document.getElementById("msg");
  if (sel < 0) { box.hidden = true; return; }
  var p = P.places[sel], stage = (+slider.value).toFixed(2), w = word(p.d);
  box.hidden = false;
  document.getElementById("msgHead").textContent = "Message for " + p.name;
  var hi, en;
  if (p.wet) {
    hi = "यमुना का जलस्तर पुराने रेलवे पुल पर " + stage +
      " मीटर तक पहुँच सकता है। " + p.name + " के आसपास पानी " + w[2] +
      " (लगभग " + p.d.toFixed(1) + " मीटर तक) आ सकता है। " +
      "ज़रूरी सामान और कागज़ात लेकर समय रहते सुरक्षित जगह पर जाएँ। " +
      "यह आधिकारिक चेतावनी नहीं है, प्रशासन की सूचना का पालन करें।";
    en = "The Yamuna may reach " + stage + " m at the Old Railway Bridge. " +
      "Around " + p.name + " water could be " + w[1] + " (up to about " +
      p.d.toFixed(1) + " m). Take essentials and documents and move to a " +
      "safe place in good time. This is not an official warning; follow " +
      "the administration.";
  } else {
    hi = "यमुना का जलस्तर पुराने रेलवे पुल पर " + stage +
      " मीटर तक पहुँच सकता है। इस मॉडल के अनुसार " + p.name +
      " के आसपास नदी का पानी आने की संभावना नहीं दिखती। " +
      "फिर भी प्रशासन की सूचना पर ध्यान रखें। यह आधिकारिक चेतावनी नहीं है।";
    en = "The Yamuna may reach " + stage + " m at the Old Railway Bridge. " +
      "This model does not show river water reaching the area around " +
      p.name + ". Keep following official updates. This is not an " +
      "official warning.";
  }
  document.getElementById("msgHi").textContent = hi;
  document.getElementById("msgEn").textContent = en;
}
var ticks = document.getElementById("ticks");
P.marks.forEach(function (m) {
  if (m.m < P.minStage || m.m > P.maxStage) return;
  var b = document.createElement("button");
  b.textContent = m.label + " " + m.m.toFixed(2);
  var f = (m.m - P.minStage) / (P.maxStage - P.minStage);
  b.style.left = (f * 100) + "%";
  if (f < 0.06) b.style.transform = "translateX(-6px)";
  b.addEventListener("click", function () { slider.value = m.m; draw(); });
  ticks.appendChild(b);
});
slider.addEventListener("input", draw);
document.getElementById("list").addEventListener("click", function (e) {
  var b = e.target.closest(".place"); if (!b) return;
  sel = +b.dataset.i === sel ? -1 : +b.dataset.i; draw();
});
cv.addEventListener("click", function (e) {
  var r = cv.getBoundingClientRect();
  var c = (e.clientX - r.left) / r.width * P.cols;
  var rw = (e.clientY - r.top) / r.height * P.rows, best = -1, bd = 36;
  P.places.forEach(function (p, i) {
    var dd = (p.col - c) * (p.col - c) + (p.row - rw) * (p.row - rw);
    if (dd < bd) { bd = dd; best = i; } });
  sel = best; draw();
});
document.getElementById("copy").addEventListener("click", function () {
  var t = document.getElementById("msgHi").textContent, btn = this;
  function done() { btn.textContent = "COPIED";
    setTimeout(function () { btn.textContent = "COPY THE HINDI MESSAGE"; }, 1500); }
  if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, done);
  else done();
});
document.getElementById("tHits").textContent = P.test.hits;
document.getElementById("tFalse").textContent = P.test.falseAlarms;
document.getElementById("bHits").textContent = P.test.tubHits;
document.getElementById("bFalse").textContent = P.test.tubFalse;
sat.onload = draw;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
