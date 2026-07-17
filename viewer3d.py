"""3D flood viewer for HydroTwin.

Generates a fully self-contained flood_3d.html: a rotatable/zoomable three.js
terrain with the simulated water surface animating over it, plus the alert,
evacuation decisions and data-source panel. three.js is inlined from
assets/web_cache so the page opens with no internet.
"""

import base64
import io
import json
import os

import numpy as np
from matplotlib import cm
from matplotlib.colors import LightSource
from PIL import Image, ImageDraw

import config
from decide import zone_name

_HERE = os.path.dirname(os.path.abspath(__file__))
WEB_CACHE = os.path.join(_HERE, "assets", "web_cache")

PRIORITY_TINT = {"immediate": (239, 83, 80), "high": (255, 152, 0),
                 "monitor": (255, 213, 79)}


def make_3d_viewer(times, depths, elevation, cell_size, decisions,
                   rain_series, rain_source, terrain_source, path=None):
    path = path or os.path.join(config.OUTPUT_DIR, "flood_3d.html")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    rows, cols = elevation.shape
    elev_north = np.flipud(elevation)  # viewer works north-row-first
    depths_north = [np.flipud(d) for d in depths]

    elev_b64 = base64.b64encode(
        elev_north.astype("<f4").tobytes()).decode()
    depth_cm = np.stack([np.clip(d * 100.0, 0, 65535) for d in depths_north])
    depths_b64 = base64.b64encode(
        depth_cm.astype("<u2").tobytes()).decode()

    payload = {
        "rows": rows, "cols": cols,
        "cellSize": cell_size,
        "elevMin": float(elev_north.min()),
        "elevMax": float(elev_north.max()),
        "nFrames": len(depths),
        "timeLabels": [f"{t / 3600.0:.2f} h" for t in times],
        "caseTitle": config.CASE_TITLE,
        "lat": config.BASIN_LAT, "lon": config.BASIN_LON,
        "alert": str(decisions.get("public_alert", "")),
        "decisionSource": decisions.get("source", ""),
        "terrainSource": terrain_source,
        "rainSource": rain_source,
        "rainSeries": [round(r, 1) for r in rain_series],
        "evacZones": decisions.get("evacuation_zones", []),
        "safeRoutes": decisions.get("safe_routes", []),
        "pois": [{k: p[k] for k in
                  ("name", "type", "row", "col", "zone", "depth_here_m")}
                 for p in decisions["pois"]],
        "floodDepthM": config.FLOOD_DEPTH_M,
    }

    tex_base = _terrain_texture(elev_north)
    tex_zones = _zones_texture(elev_north, decisions)

    html = _TEMPLATE
    for key, value in (
            ("__PAYLOAD__", json.dumps(payload)),
            ("__ELEV_B64__", elev_b64),
            ("__DEPTHS_B64__", depths_b64),
            ("__TEX_BASE__", tex_base),
            ("__TEX_ZONES__", tex_zones),
            ("__THREE_JS__", _read_cache("three.min.js")),
            ("__ORBIT_JS__", _read_cache("OrbitControls.js"))):
        html = html.replace(key, value)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[viewer3d] 3D viewer saved to {path} "
          f"({os.path.getsize(path) // 1024} KB, opens offline)")
    return path


def _read_cache(name):
    fpath = os.path.join(WEB_CACHE, name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(
            f"{name} missing from assets/web_cache — re-run "
            f"'curl' caching step or restore the repo copy")
    with open(fpath, encoding="utf-8") as f:
        return f.read()


# ------------------------------------------------------------- textures ----

def _shade_rgb(elev_north):
    ls = LightSource(azdeg=315, altdeg=45)
    # vmin below the data range keeps gist_earth's deep-blue band unused, so
    # dry land reads green/brown and never blends with the water surface
    span = max(float(elev_north.max() - elev_north.min()), 1.0)
    rgb = ls.shade(elev_north, cmap=cm.gist_earth, blend_mode="soft",
                   vert_exag=2.5, vmin=float(elev_north.min()) - 0.45 * span,
                   vmax=float(elev_north.max()) + 0.05 * span)
    return (np.clip(rgb[..., :3], 0, 1) * 255).astype(np.uint8)


def _to_data_uri(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _terrain_texture(elev_north, size=512):
    img = Image.fromarray(_shade_rgb(elev_north), "RGB")
    return _to_data_uri(img.resize((size, size), Image.BICUBIC))


def _zones_texture(elev_north, decisions, size=512):
    img = Image.fromarray(_shade_rgb(elev_north), "RGB") \
        .resize((size, size), Image.BICUBIC).convert("RGBA")
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    evac = {e["zone"]: e for e in decisions.get("evacuation_zones", [])}
    band = size // config.ZONE_DIV
    for ib in range(config.ZONE_DIV):        # image band 0 = north = letter A
        for jb in range(config.ZONE_DIV):
            name = f"{chr(ord('A') + ib)}{jb + 1}"
            box = (jb * band, ib * band, (jb + 1) * band, (ib + 1) * band)
            entry = evac.get(name)
            if entry:
                tint = PRIORITY_TINT.get(entry["priority"], (255, 213, 79))
                draw.rectangle(box, fill=tint + (80,),
                               outline=tint + (230,), width=3)
            else:
                draw.rectangle(box, outline=(255, 255, 255, 60), width=1)
            draw.text((box[0] + 8, box[1] + 6), name,
                      fill=(255, 255, 255, 200))
    return _to_data_uri(Image.alpha_composite(img, overlay).convert("RGB"))


# ------------------------------------------------------------- template ----

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin — 3D Flood Simulation</title>
<style>
  :root {
    --bg: #0b0f14; --panel: #11161d; --panel2: #161d26; --line: #232c37;
    --text: #dbe4ee; --dim: #8b98a8; --accent: #4dd0e1; --red: #ef5350;
    --orange: #ffa726; --yellow: #ffd54f;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; background: var(--bg);
    color: var(--text);
    font: 14px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif; }
  #scene { position: absolute; inset: 0; }
  .panel { position: absolute; background: rgba(17,22,29,.92);
    border: 1px solid var(--line); border-radius: 10px; }

  #side { top: 16px; left: 16px; bottom: 88px; width: 320px; padding: 18px;
    overflow-y: auto; }
  #side::-webkit-scrollbar { width: 6px; }
  #side::-webkit-scrollbar-thumb { background: var(--line); border-radius: 3px; }
  h1 { font-size: 19px; letter-spacing: 2.5px; font-weight: 700; }
  h1 span { color: var(--accent); }
  .case { color: var(--dim); font-size: 12.5px; margin: 2px 0 14px; }
  h2 { font-size: 10.5px; letter-spacing: 1.6px; text-transform: uppercase;
    color: var(--dim); margin: 16px 0 8px; }
  .alert { background: rgba(239,83,80,.12); border: 1px solid
    rgba(239,83,80,.45); border-radius: 8px; padding: 10px 12px;
    font-size: 13px; }
  .alert b { color: var(--red); letter-spacing: 1px; font-size: 11px; }
  .zone-row, .poi-row { display: flex; align-items: baseline; gap: 8px;
    padding: 6px 8px; border-radius: 6px; margin-bottom: 4px;
    background: var(--panel2); font-size: 12.5px; }
  .chip { font-size: 10px; font-weight: 700; letter-spacing: .8px;
    padding: 1.5px 7px; border-radius: 20px; text-transform: uppercase;
    flex-shrink: 0; }
  .chip.immediate { background: rgba(239,83,80,.2); color: var(--red); }
  .chip.high { background: rgba(255,167,38,.18); color: var(--orange); }
  .chip.monitor { background: rgba(255,213,79,.15); color: var(--yellow); }
  .zone-id { font-weight: 700; color: var(--accent); flex-shrink: 0; }
  .reason { color: var(--dim); font-size: 11.5px; }
  .poi-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
    align-self: center; }
  .poi-depth { margin-left: auto; color: var(--dim); font-size: 11.5px;
    flex-shrink: 0; }
  .poi-depth.wet { color: var(--red); font-weight: 600; }
  #rain { display: flex; align-items: flex-end; gap: 3px; height: 52px;
    padding: 4px 2px 0; }
  #rain div { flex: 1; background: linear-gradient(180deg, var(--accent),
    #1a7f8f); border-radius: 2px 2px 0 0; min-height: 2px; position: relative; }
  #rain div i { position: absolute; top: -15px; left: 50%;
    transform: translateX(-50%); font-style: normal; font-size: 9.5px;
    color: var(--dim); }
  .src { font-size: 11.5px; color: var(--dim); padding: 2px 0; }
  .src b { color: var(--text); font-weight: 600; }

  #bar { left: 50%; transform: translateX(-50%); bottom: 16px;
    width: min(680px, calc(100% - 380px)); padding: 12px 18px;
    display: flex; align-items: center; gap: 14px; }
  button { background: var(--panel2); color: var(--text); border: 1px solid
    var(--line); border-radius: 7px; padding: 7px 14px; font: inherit;
    font-size: 13px; cursor: pointer; }
  button:hover { border-color: var(--accent); color: var(--accent); }
  input[type=range] { flex: 1; accent-color: var(--accent); }
  #tlabel { font-variant-numeric: tabular-nums; min-width: 66px;
    color: var(--accent); font-weight: 600; }

  #view { top: 16px; right: 16px; padding: 10px 14px; font-size: 12.5px; }
  #view label { display: flex; gap: 7px; align-items: center; padding: 4px 0;
    cursor: pointer; color: var(--dim); }
  #view input { accent-color: var(--accent); }

  #tip { position: absolute; display: none; pointer-events: none;
    background: #06090d; border: 1px solid var(--accent); border-radius: 7px;
    padding: 7px 11px; font-size: 12px; z-index: 10; max-width: 240px; }
  #tip b { color: var(--accent); }
  @media (max-width: 900px) { #side { display: none; }
    #bar { width: calc(100% - 32px); } }
</style>
</head>
<body>
<div id="scene"></div>

<div id="side" class="panel">
  <h1>HYDRO<span>TWIN</span></h1>
  <div class="case" id="caseTitle"></div>
  <div class="alert"><b>FLOOD ALERT</b><br><span id="alertText"></span></div>
  <h2>Evacuation zones</h2><div id="zones"></div>
  <h2>Points of interest</h2><div id="pois"></div>
  <h2>Rainfall forcing (mm/hr)</h2><div id="rain"></div>
  <h2>Data sources</h2><div id="sources"></div>
</div>

<div id="bar" class="panel">
  <button id="play">&#9654; Play</button>
  <input id="slider" type="range" min="0" value="0">
  <span id="tlabel"></span>
</div>

<div id="view" class="panel">
  <label><input type="checkbox" id="cbZones"> Evacuation zones</label>
  <label><input type="checkbox" id="cbSpin" checked> Auto-rotate</label>
</div>

<div id="tip"></div>

<script>__THREE_JS__</script>
<script>__ORBIT_JS__</script>
<script>
"use strict";
var P = __PAYLOAD__;

function b64Bytes(b64) {
  var bin = atob(b64), out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
var ELEV = new Float32Array(b64Bytes("__ELEV_B64__").buffer);   // m, north-first
var DEPTH = new Uint16Array(b64Bytes("__DEPTHS_B64__").buffer); // cm, per frame

// ------- scene scale: plane is SIZE units wide; auto vertical exaggeration
var SIZE = 120;
var mtu = SIZE / (P.cols * P.cellSize);                 // metres -> scene units
var relief = Math.max(P.elevMax - P.elevMin, 1e-6);
var VEX = Math.min(Math.max(16 / (relief * mtu), 1.5), 40);
var yOf = function (metres) { return metres * mtu * VEX; };

var renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.getElementById("scene").appendChild(renderer.domElement);

var scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0f14);
scene.fog = new THREE.Fog(0x0b0f14, SIZE * 1.6, SIZE * 4.5);

var camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, .1, 2000);
camera.position.set(SIZE * .75, SIZE * .55, SIZE * .95);

var controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = .06;
controls.maxPolarAngle = Math.PI * .49;
controls.minDistance = SIZE * .25; controls.maxDistance = SIZE * 3;
controls.autoRotate = true; controls.autoRotateSpeed = .6;
controls.addEventListener("start", function () {
  controls.autoRotate = false;
  document.getElementById("cbSpin").checked = false;
});

scene.add(new THREE.HemisphereLight(0xbcd4e6, 0x1a2129, .75));
var sun = new THREE.DirectionalLight(0xfff2df, .9);
sun.position.set(-SIZE, SIZE * 1.2, SIZE * .5);
scene.add(sun);

// ------- terrain mesh
var texLoader = new THREE.TextureLoader();
var texBase = texLoader.load("__TEX_BASE__");
var texZones = texLoader.load("__TEX_ZONES__");

var terrainGeo = new THREE.PlaneGeometry(SIZE, SIZE, P.cols - 1, P.rows - 1);
var tpos = terrainGeo.attributes.position;
for (var i = 0; i < tpos.count; i++)
  tpos.setZ(i, yOf(ELEV[i] - P.elevMin));
terrainGeo.computeVertexNormals();
var terrainMat = new THREE.MeshLambertMaterial({ map: texBase });
var terrain = new THREE.Mesh(terrainGeo, terrainMat);
terrain.rotation.x = -Math.PI / 2;
scene.add(terrain);

// thin dark skirt so the terrain reads as a solid block
var skirt = new THREE.Mesh(
  new THREE.BoxGeometry(SIZE, yOf(relief) + 6, SIZE),
  new THREE.MeshLambertMaterial({ color: 0x141a21 }));
skirt.position.y = -(yOf(relief) + 6) / 2 - .01;
scene.add(skirt);

// ------- water mesh (positions + vertex colors updated per frame)
var waterGeo = new THREE.PlaneGeometry(SIZE, SIZE, P.cols - 1, P.rows - 1);
var wpos = waterGeo.attributes.position;
var wcol = new THREE.BufferAttribute(new Float32Array(wpos.count * 3), 3);
waterGeo.setAttribute("color", wcol);
var water = new THREE.Mesh(waterGeo, new THREE.MeshPhongMaterial({
  vertexColors: true, transparent: true, opacity: .82, shininess: 90,
  specular: 0x223344 }));
water.rotation.x = -Math.PI / 2;
scene.add(water);

var N = P.rows * P.cols;
var maxDepthCm = 1;
for (var d = 0; d < DEPTH.length; d++)
  if (DEPTH[d] > maxDepthCm) maxDepthCm = DEPTH[d];

function setFrame(f) {
  var off = f * N;
  for (var i = 0; i < N; i++) {
    var dm = DEPTH[off + i] / 100;
    var ty = yOf(ELEV[i] - P.elevMin);
    if (dm >= .03) {
      wpos.setZ(i, ty + yOf(dm) + .04);
      var t = Math.min(dm / (maxDepthCm / 100) * 1.4, 1);
      wcol.setXYZ(i, .28 - .2 * t, .62 - .42 * t, .95 - .35 * t);
    } else {
      wpos.setZ(i, ty - 2.5);
      wcol.setXYZ(i, .2, .45, .8);
    }
  }
  wpos.needsUpdate = true; wcol.needsUpdate = true;
  waterGeo.computeVertexNormals();
  slider.value = f;
  tlabel.textContent = "t = " + P.timeLabels[f];
}

// ------- POI markers
var poiColors = { hospital: 0xef5350, school: 0xab47bc, road: 0x90a4ae };
var poiMeshes = [];
function gridToWorld(row, col, lift) {
  // payload rows are south-first; vertex rows are north-first
  var r = P.rows - 1 - row;
  var x = (col / (P.cols - 1) - .5) * SIZE;
  var z = (r / (P.rows - 1) - .5) * SIZE;
  var y = yOf(ELEV[r * P.cols + col] - P.elevMin);
  return new THREE.Vector3(x, y + (lift || 0), z);
}
P.pois.forEach(function (p) {
  var pos = gridToWorld(p.row, p.col, 0);
  var h = 7;
  var stem = new THREE.Mesh(
    new THREE.CylinderGeometry(.14, .14, h, 6),
    new THREE.MeshBasicMaterial({ color: 0xd0d8e0 }));
  stem.position.copy(pos); stem.position.y += h / 2;
  scene.add(stem);
  var head = new THREE.Mesh(new THREE.SphereGeometry(1.15, 18, 14),
    new THREE.MeshLambertMaterial({ color: poiColors[p.type] || 0x4dd0e1,
      emissive: poiColors[p.type] || 0x4dd0e1, emissiveIntensity: .35 }));
  head.position.copy(pos); head.position.y += h;
  head.userData = p;
  scene.add(head);
  poiMeshes.push(head);
});

// tooltip on hover
var ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
var tip = document.getElementById("tip");
renderer.domElement.addEventListener("mousemove", function (e) {
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  var hit = ray.intersectObjects(poiMeshes)[0];
  if (hit) {
    var p = hit.object.userData;
    tip.innerHTML = "<b>" + p.name + "</b><br>" + p.type + " — zone " +
      p.zone + "<br>water depth here: " + p.depth_here_m + " m";
    tip.style.display = "block";
    tip.style.left = (e.clientX + 14) + "px";
    tip.style.top = (e.clientY + 10) + "px";
  } else tip.style.display = "none";
});

// ------- UI
var slider = document.getElementById("slider");
var tlabel = document.getElementById("tlabel");
var playBtn = document.getElementById("play");
slider.max = P.nFrames - 1;
var timer = null;
slider.addEventListener("input", function () { setFrame(+slider.value); });
playBtn.addEventListener("click", function () {
  if (timer) { clearInterval(timer); timer = null;
    playBtn.innerHTML = "&#9654; Play"; return; }
  playBtn.innerHTML = "&#10074;&#10074; Pause";
  timer = setInterval(function () {
    setFrame((+slider.value + 1) % P.nFrames);
  }, 320);
});
document.getElementById("cbZones").addEventListener("change", function (e) {
  terrainMat.map = e.target.checked ? texZones : texBase;
  terrainMat.needsUpdate = true;
});
document.getElementById("cbSpin").addEventListener("change", function (e) {
  controls.autoRotate = e.target.checked;
});

// ------- side panel content
document.getElementById("caseTitle").textContent =
  P.caseTitle + "  ·  " + P.lat.toFixed(2) + ", " + P.lon.toFixed(2);
document.getElementById("alertText").textContent = P.alert;
var zonesEl = document.getElementById("zones");
if (!P.evacZones.length)
  zonesEl.innerHTML = "<div class='src'>No evacuation needed.</div>";
P.evacZones.slice(0, 8).forEach(function (z) {
  var div = document.createElement("div");
  div.className = "zone-row";
  div.innerHTML = "<span class='zone-id'>" + z.zone + "</span>" +
    "<span class='chip " + z.priority + "'>" + z.priority + "</span>" +
    "<span class='reason'>" + z.reason + "</span>";
  zonesEl.appendChild(div);
});
var poisEl = document.getElementById("pois");
P.pois.forEach(function (p) {
  var div = document.createElement("div");
  div.className = "poi-row";
  var c = { hospital: "#ef5350", school: "#ab47bc", road: "#90a4ae" }[p.type];
  div.innerHTML = "<span class='poi-dot' style='background:" + c + "'></span>" +
    "<span>" + p.name + "</span><span class='poi-depth" +
    (p.depth_here_m >= P.floodDepthM ? " wet" : "") + "'>" +
    p.depth_here_m + " m</span>";
  poisEl.appendChild(div);
});
var rainEl = document.getElementById("rain");
var rainMax = Math.max.apply(null, P.rainSeries.concat([1]));
P.rainSeries.forEach(function (r) {
  var bar = document.createElement("div");
  bar.style.height = Math.max(r / rainMax * 100, 4) + "%";
  bar.innerHTML = "<i>" + r + "</i>";
  rainEl.appendChild(bar);
});
document.getElementById("sources").innerHTML =
  "<div class='src'>Terrain: <b>" + P.terrainSource + "</b></div>" +
  "<div class='src'>Rainfall: <b>" + P.rainSource + "</b></div>" +
  "<div class='src'>Physics: <b>Landlab OverlandFlow (2D shallow water)</b></div>" +
  "<div class='src'>Decisions: <b>" + P.decisionSource + "</b></div>";

// ------- go
setFrame(P.nFrames - 1);
addEventListener("resize", function () {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop() {
  requestAnimationFrame(loop);
  controls.update();
  renderer.render(scene, camera);
})();
</script>
</body>
</html>
"""
