"""3D flood viewer for HydroTwin.

Generates a fully self-contained flood_3d.html: a rotatable/zoomable three.js
terrain with the simulated water surface animating over it, live flood stats,
a rainfall-synced timeline, evacuation decisions and data sources. three.js
is inlined from assets/web_cache so the page opens with no internet.
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
        "timesS": [float(t) for t in times],
        "durationHr": config.SIM_DURATION_HR,
        "caseName": config.ACTIVE_CASE,
        "caseTitle": config.CASE_TITLE,
        "cases": [{"name": n, "title": c["title"].split("—")[0].strip()}
                  for n, c in config.CASES.items()],
        "lat": config.BASIN_LAT, "lon": config.BASIN_LON,
        "alert": str(decisions.get("public_alert", "")),
        "decisionSource": decisions.get("source", ""),
        "terrainSource": terrain_source,
        "rainSource": rain_source,
        "rainSeries": [round(r, 1) for r in rain_series],
        "evacZones": decisions.get("evacuation_zones", []),
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
    --bg0: #060a10; --bg1: #0d1420; --panel: rgba(13, 19, 28, .88);
    --line: #1d2836; --line2: #2a3a4e;
    --text: #e4ecf5; --dim: #7e8ea1; --dimmer: #55657a;
    --accent: #38d6f5; --accent2: #7c9cf5;
    --red: #ff5c57; --orange: #ffab40; --yellow: #ffd54f;
    --safe: #4cd97b;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; color: var(--text);
    font: 13.5px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif;
    background: radial-gradient(120% 90% at 70% 10%, var(--bg1), var(--bg0));
  }
  #scene { position: absolute; inset: 0; }

  .panel { position: absolute; background: var(--panel);
    border: 1px solid var(--line); border-radius: 14px;
    backdrop-filter: blur(10px); box-shadow: 0 8px 32px rgba(0,0,0,.45); }

  /* ---------- header ---------- */
  #top { top: 14px; left: 14px; right: auto; padding: 14px 20px 12px;
    width: 344px; }
  #brand { font-size: 21px; font-weight: 800; letter-spacing: 3px; }
  #brand em { font-style: normal;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; background-clip: text; color: transparent; }
  #brand small { display: block; font-size: 10px; font-weight: 500;
    letter-spacing: 1.8px; text-transform: uppercase; color: var(--dimmer);
    margin-top: 1px; }
  #tabs { display: flex; gap: 6px; margin-top: 12px; }
  #tabs a { flex: 1; text-align: center; text-decoration: none;
    font-size: 11.5px; font-weight: 600; color: var(--dim);
    padding: 6px 4px; border-radius: 8px; border: 1px solid var(--line);
    background: rgba(255,255,255,.02); transition: all .15s; }
  #tabs a:hover { color: var(--text); border-color: var(--line2); }
  #tabs a.on { color: #04151c; border-color: transparent;
    background: linear-gradient(90deg, var(--accent), var(--accent2)); }
  .case { color: var(--dim); font-size: 11.5px; margin-top: 10px; }

  /* ---------- side ---------- */
  #side { top: 148px; left: 14px; bottom: 96px; width: 344px;
    padding: 16px 18px; overflow-y: auto; overscroll-behavior: contain; }
  #side::-webkit-scrollbar { width: 5px; }
  #side::-webkit-scrollbar-thumb { background: var(--line2);
    border-radius: 3px; }
  h2 { font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
    color: var(--dimmer); margin: 18px 0 9px; display: flex;
    align-items: center; gap: 8px; }
  h2::after { content: ""; flex: 1; height: 1px; background: var(--line); }
  h2:first-child { margin-top: 0; }

  .alert { background: linear-gradient(135deg, rgba(255,92,87,.16),
    rgba(255,92,87,.06)); border: 1px solid rgba(255,92,87,.4);
    border-radius: 10px; padding: 11px 13px; font-size: 12.5px; }
  .alert-head { display: flex; align-items: center; gap: 7px;
    font-size: 10.5px; font-weight: 800; letter-spacing: 1.6px;
    color: var(--red); margin-bottom: 5px; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background:
    var(--red); animation: pulse 1.4s ease-out infinite; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(255,92,87,.6); }
    100% { box-shadow: 0 0 0 9px rgba(255,92,87,0); } }

  #stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .stat { background: rgba(255,255,255,.03); border: 1px solid var(--line);
    border-radius: 10px; padding: 9px 12px 8px; }
  .stat b { display: block; font-size: 20px; font-weight: 700;
    font-variant-numeric: tabular-nums; letter-spacing: -.3px; }
  .stat b i { font-style: normal; font-size: 11px; font-weight: 600;
    color: var(--dim); margin-left: 3px; }
  .stat span { font-size: 10px; letter-spacing: 1.2px;
    text-transform: uppercase; color: var(--dimmer); }
  .stat.hot b { color: var(--accent); }

  .zrow { display: flex; align-items: baseline; gap: 9px; padding: 7px 10px;
    border-radius: 8px; margin-bottom: 5px; background: rgba(255,255,255,.025);
    border-left: 3px solid var(--line2); font-size: 12px; }
  .zrow.immediate { border-left-color: var(--red); }
  .zrow.high { border-left-color: var(--orange); }
  .zrow.monitor { border-left-color: var(--yellow); }
  .zid { font-weight: 800; font-size: 13px; color: var(--text); width: 24px;
    flex-shrink: 0; }
  .chip { font-size: 9px; font-weight: 800; letter-spacing: 1px;
    padding: 2px 7px; border-radius: 20px; text-transform: uppercase;
    flex-shrink: 0; }
  .chip.immediate { background: rgba(255,92,87,.18); color: var(--red); }
  .chip.high { background: rgba(255,171,64,.16); color: var(--orange); }
  .chip.monitor { background: rgba(255,213,79,.12); color: var(--yellow); }
  .zreason { color: var(--dim); font-size: 11px; line-height: 1.35; }

  .prow { display: flex; align-items: center; gap: 9px; padding: 7px 10px;
    border-radius: 8px; margin-bottom: 5px;
    background: rgba(255,255,255,.025); font-size: 12px; }
  .pdot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
    box-shadow: 0 0 8px currentColor; }
  .pname { line-height: 1.25; }
  .pname small { display: block; color: var(--dimmer); font-size: 10px;
    text-transform: uppercase; letter-spacing: 1px; }
  .pstat { margin-left: auto; flex-shrink: 0; font-size: 10.5px;
    font-weight: 800; letter-spacing: .6px; padding: 2.5px 8px;
    border-radius: 20px; }
  .pstat.safe { color: var(--safe); background: rgba(76,217,123,.12); }
  .pstat.wet { color: var(--red); background: rgba(255,92,87,.15); }

  .src { font-size: 11px; color: var(--dim); padding: 2.5px 0;
    display: flex; gap: 8px; }
  .src em { font-style: normal; color: var(--dimmer); width: 62px;
    flex-shrink: 0; text-transform: uppercase; font-size: 9.5px;
    letter-spacing: 1px; padding-top: 2px; }
  .src b { font-weight: 600; color: var(--text); }

  /* ---------- bottom bar ---------- */
  #bar { left: 50%; transform: translateX(-50%); bottom: 14px;
    width: min(720px, calc(100% - 400px)); padding: 10px 18px 13px; }
  #rainrow { display: flex; align-items: flex-end; gap: 3px; height: 34px;
    margin: 0 2px 7px; }
  #rainrow div { flex: 1; border-radius: 2px 2px 0 0; min-height: 3px;
    background: var(--line2); transition: background .2s; position: relative; }
  #rainrow div.wet { background: linear-gradient(180deg, var(--accent),
    #145e70); }
  #rainrow div i { position: absolute; top: -14px; width: 100%;
    text-align: center; font-style: normal; font-size: 9px;
    color: var(--dimmer); }
  #controls { display: flex; align-items: center; gap: 13px; }
  #playbtn { width: 40px; height: 40px; border-radius: 50%; border: none;
    cursor: pointer; font-size: 15px; color: #04151c; flex-shrink: 0;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    box-shadow: 0 3px 14px rgba(56,214,245,.35); }
  #playbtn:hover { filter: brightness(1.15); }
  input[type=range] { flex: 1; accent-color: var(--accent); height: 4px; }
  #tlabel { font-variant-numeric: tabular-nums; min-width: 74px;
    text-align: right; font-weight: 700; font-size: 15px;
    color: var(--accent); }
  #speed { background: rgba(255,255,255,.04); color: var(--dim);
    border: 1px solid var(--line); border-radius: 7px; padding: 5px 7px;
    font: inherit; font-size: 11.5px; }
  #hint { text-align: center; color: var(--dimmer); font-size: 10px;
    letter-spacing: .6px; margin-top: 7px; }

  /* ---------- view options ---------- */
  #view { top: 14px; right: 14px; padding: 13px 16px; width: 208px;
    font-size: 12px; }
  #view label { display: flex; gap: 8px; align-items: center;
    padding: 4.5px 0; cursor: pointer; color: var(--dim); }
  #view label:hover { color: var(--text); }
  #view input[type=checkbox] { accent-color: var(--accent); }
  #view input[type=range] { width: 100%; margin-top: 2px; }
  #legend { margin-top: 10px; }
  #legendbar { height: 9px; border-radius: 5px; background:
    linear-gradient(90deg, #9fd4ff, #2f7fd4, #103a80); }
  #legendlab { display: flex; justify-content: space-between;
    color: var(--dimmer); font-size: 10px; margin-top: 3px; }

  #compass { position: absolute; right: 22px; bottom: 22px; width: 52px;
    height: 52px; border-radius: 50%; background: var(--panel);
    border: 1px solid var(--line); display: flex; align-items: center;
    justify-content: center; }
  #needle { font-size: 15px; font-weight: 800; color: var(--red);
    transition: transform .1s linear; }

  #tip { position: absolute; display: none; pointer-events: none;
    background: #05080c; border: 1px solid var(--accent); border-radius: 9px;
    padding: 8px 12px; font-size: 12px; z-index: 10; max-width: 250px;
    box-shadow: 0 6px 24px rgba(0,0,0,.6); }
  #tip b { color: var(--accent); }
  @media (max-width: 980px) { #side, #top { display: none; }
    #bar { width: calc(100% - 28px); } }
</style>
</head>
<body>
<div id="scene"></div>

<div id="top" class="panel">
  <div id="brand">HYDRO<em>TWIN</em>
    <small>physics-informed flood intelligence</small></div>
  <nav id="tabs"></nav>
  <div class="case" id="caseTitle"></div>
</div>

<div id="side" class="panel">
  <div class="alert">
    <div class="alert-head"><span class="pulse"></span>FLOOD ALERT</div>
    <span id="alertText"></span>
  </div>
  <h2>Live flood state</h2>
  <div id="stats">
    <div class="stat hot"><b id="stMax">–<i>m</i></b>
      <span>peak depth</span></div>
    <div class="stat"><b id="stArea">–<i>km²</i></b>
      <span>flooded area</span></div>
    <div class="stat"><b id="stVol">–<i>Mm³</i></b>
      <span>water volume</span></div>
    <div class="stat"><b id="stZones">–</b>
      <span>zones flagged</span></div>
  </div>
  <h2>Evacuation priorities</h2><div id="zones"></div>
  <h2>Points of interest</h2><div id="pois"></div>
  <h2>Data sources</h2><div id="sources"></div>
</div>

<div id="view" class="panel">
  <label><input type="checkbox" id="cbZones"> Evacuation zones</label>
  <label><input type="checkbox" id="cbSpin" checked> Auto-rotate</label>
  <label style="display:block; margin-top:6px;">Water opacity
    <input type="range" id="rgOpacity" min="30" max="100" value="84"></label>
  <div id="legend">
    <div id="legendbar"></div>
    <div id="legendlab"><span>0 m</span><span id="legendMax"></span></div>
  </div>
</div>

<div id="bar" class="panel">
  <div id="rainrow"></div>
  <div id="controls">
    <button id="playbtn" title="Play / pause (space)">&#9654;</button>
    <input id="slider" type="range" min="0" value="0">
    <span id="tlabel"></span>
    <select id="speed"><option value="1">1&times;</option>
      <option value="2" selected>2&times;</option>
      <option value="4">4&times;</option></select>
  </div>
  <div id="hint">drag to rotate · scroll to zoom · space to play ·
    &larr;&rarr; to step · hover pins for detail</div>
</div>

<div id="compass" class="panel" title="North"><span id="needle">N</span></div>
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
var N = P.rows * P.cols;

// ---- per-frame stats (precomputed once)
var cellKm2 = P.cellSize * P.cellSize / 1e6;
var STATS = [];
var maxDepthCm = 1;
for (var f = 0; f < P.nFrames; f++) {
  var mx = 0, wet = 0, sum = 0;
  for (var i = 0; i < N; i++) {
    var cm = DEPTH[f * N + i];
    if (cm > mx) mx = cm;
    if (cm >= P.floodDepthM * 100) wet++;
    sum += cm;
  }
  if (mx > maxDepthCm) maxDepthCm = mx;
  STATS.push({ max: mx / 100, areaKm2: wet * cellKm2,
    volMm3: sum / 100 * P.cellSize * P.cellSize / 1e6 });
}

// ---- scene scale: plane SIZE units wide; auto vertical exaggeration
var SIZE = 120;
var mtu = SIZE / (P.cols * P.cellSize);
var relief = Math.max(P.elevMax - P.elevMin, 1e-6);
var VEX = Math.min(Math.max(16 / (relief * mtu), 1.5), 40);
function yOf(m) { return m * mtu * VEX; }

var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
document.getElementById("scene").appendChild(renderer.domElement);

var scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x0a1018, SIZE * 1.8, SIZE * 5);

var camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, .1, 2000);
camera.position.set(SIZE * .72, SIZE * .5, SIZE * .92);

var controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = .06;
controls.maxPolarAngle = Math.PI * .49;
controls.minDistance = SIZE * .22; controls.maxDistance = SIZE * 3;
controls.autoRotate = true; controls.autoRotateSpeed = .55;
controls.addEventListener("start", function () {
  controls.autoRotate = false;
  document.getElementById("cbSpin").checked = false;
});

scene.add(new THREE.HemisphereLight(0xbcd4e6, 0x161d26, .8));
var sun = new THREE.DirectionalLight(0xffe9cf, .95);
sun.position.set(-SIZE, SIZE * 1.2, SIZE * .5);
scene.add(sun);

// ---- terrain
var texLoader = new THREE.TextureLoader();
var texBase = texLoader.load("__TEX_BASE__");
var texZones = texLoader.load("__TEX_ZONES__");
texBase.anisotropy = renderer.capabilities.getMaxAnisotropy();
texZones.anisotropy = texBase.anisotropy;

var terrainGeo = new THREE.PlaneGeometry(SIZE, SIZE, P.cols - 1, P.rows - 1);
var tpos = terrainGeo.attributes.position;
for (var i = 0; i < tpos.count; i++) tpos.setZ(i, yOf(ELEV[i] - P.elevMin));
terrainGeo.computeVertexNormals();
var terrainMat = new THREE.MeshLambertMaterial({ map: texBase });
var terrain = new THREE.Mesh(terrainGeo, terrainMat);
terrain.rotation.x = -Math.PI / 2;
scene.add(terrain);

var skirt = new THREE.Mesh(
  new THREE.BoxGeometry(SIZE, yOf(relief) + 6, SIZE),
  new THREE.MeshLambertMaterial({ color: 0x10161e }));
skirt.position.y = -(yOf(relief) + 6) / 2 - .01;
scene.add(skirt);

// ---- water
var waterGeo = new THREE.PlaneGeometry(SIZE, SIZE, P.cols - 1, P.rows - 1);
var wpos = waterGeo.attributes.position;
var wcol = new THREE.BufferAttribute(new Float32Array(wpos.count * 3), 3);
waterGeo.setAttribute("color", wcol);
var waterMat = new THREE.MeshPhongMaterial({ vertexColors: true,
  transparent: true, opacity: .84, shininess: 110, specular: 0x334a66 });
var water = new THREE.Mesh(waterGeo, waterMat);
water.rotation.x = -Math.PI / 2;
scene.add(water);

var vmaxM = maxDepthCm / 100;
document.getElementById("legendMax").textContent =
  vmaxM.toFixed(1) + " m";

function setFrame(f) {
  f = Math.max(0, Math.min(P.nFrames - 1, f));
  var off = f * N;
  for (var i = 0; i < N; i++) {
    var dm = DEPTH[off + i] / 100;
    var ty = yOf(ELEV[i] - P.elevMin);
    if (dm >= .02) {
      wpos.setZ(i, ty + yOf(dm) + .04);
      var t = Math.min(dm / vmaxM * 1.5, 1);
      wcol.setXYZ(i, .62 - .55 * t, .83 - .58 * t, 1 - .5 * t);
    } else {
      wpos.setZ(i, ty - 2.5);
      wcol.setXYZ(i, .3, .55, .9);
    }
  }
  wpos.needsUpdate = true; wcol.needsUpdate = true;
  waterGeo.computeVertexNormals();

  slider.value = f;
  var hrs = P.timesS[f] / 3600;
  tlabel.textContent = "T+" + Math.floor(hrs) + ":" +
    ("0" + Math.round(hrs % 1 * 60)).slice(-2) + " h";
  var s = STATS[f];
  stMax.firstChild.textContent = s.max.toFixed(2);
  stArea.firstChild.textContent = s.areaKm2.toFixed(2);
  stVol.firstChild.textContent = s.volMm3.toFixed(2);
  var doneHours = hrs;
  rainBars.forEach(function (b, h) {
    b.className = h < doneHours ? "wet" : "";
  });
}

// ---- POI pins
var poiColors = { hospital: 0xff5c57, school: 0xba68f0, road: 0x9fb2c4 };
var poiMeshes = [];
function gridToWorld(row, col, lift) {
  var r = P.rows - 1 - row;   // payload rows are south-first
  var x = (col / (P.cols - 1) - .5) * SIZE;
  var z = (r / (P.rows - 1) - .5) * SIZE;
  var y = yOf(ELEV[r * P.cols + col] - P.elevMin);
  return new THREE.Vector3(x, y + (lift || 0), z);
}
P.pois.forEach(function (p) {
  var pos = gridToWorld(p.row, p.col, 0), h = 7.5;
  var stem = new THREE.Mesh(new THREE.CylinderGeometry(.13, .13, h, 6),
    new THREE.MeshBasicMaterial({ color: 0xc7d3df }));
  stem.position.copy(pos); stem.position.y += h / 2;
  scene.add(stem);
  var head = new THREE.Mesh(new THREE.SphereGeometry(1.2, 18, 14),
    new THREE.MeshLambertMaterial({ color: poiColors[p.type] || 0x38d6f5,
      emissive: poiColors[p.type] || 0x38d6f5, emissiveIntensity: .4 }));
  head.position.copy(pos); head.position.y += h;
  head.userData = p;
  scene.add(head);
  poiMeshes.push(head);
});

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

// ---- UI wiring
var slider = document.getElementById("slider");
var tlabel = document.getElementById("tlabel");
var playBtn = document.getElementById("playbtn");
var speedSel = document.getElementById("speed");
var stMax = document.getElementById("stMax");
var stArea = document.getElementById("stArea");
var stVol = document.getElementById("stVol");
slider.max = P.nFrames - 1;
document.getElementById("stZones").textContent = P.evacZones.length;

var timer = null;
function stopPlay() { clearInterval(timer); timer = null;
  playBtn.innerHTML = "&#9654;"; }
function togglePlay() {
  if (timer) { stopPlay(); return; }
  playBtn.innerHTML = "&#10074;&#10074;";
  timer = setInterval(function () {
    setFrame((+slider.value + 1) % P.nFrames);
  }, 420 / +speedSel.value);
}
playBtn.addEventListener("click", togglePlay);
speedSel.addEventListener("change", function () {
  if (timer) { stopPlay(); togglePlay(); }
});
slider.addEventListener("input", function () { setFrame(+slider.value); });
addEventListener("keydown", function (e) {
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  if (e.code === "ArrowRight") setFrame(+slider.value + 1);
  if (e.code === "ArrowLeft") setFrame(+slider.value - 1);
});
document.getElementById("cbZones").addEventListener("change", function (e) {
  terrainMat.map = e.target.checked ? texZones : texBase;
  terrainMat.needsUpdate = true;
});
document.getElementById("cbSpin").addEventListener("change", function (e) {
  controls.autoRotate = e.target.checked;
});
document.getElementById("rgOpacity").addEventListener("input", function (e) {
  waterMat.opacity = +e.target.value / 100;
});

// ---- panels
document.title = "HydroTwin — " + P.caseTitle;
document.getElementById("caseTitle").textContent =
  P.caseTitle + " · " + P.lat.toFixed(2) + ", " + P.lon.toFixed(2);
document.getElementById("alertText").textContent = P.alert;

var tabs = document.getElementById("tabs");
P.cases.forEach(function (c) {
  var a = document.createElement("a");
  a.textContent = c.title;
  a.href = "../" + c.name + "/flood_3d.html";
  if (c.name === P.caseName) { a.className = "on"; a.href = "#"; }
  tabs.appendChild(a);
});

var zonesEl = document.getElementById("zones");
if (!P.evacZones.length)
  zonesEl.innerHTML = "<div class='src'>No evacuation needed.</div>";
P.evacZones.slice(0, 6).forEach(function (z) {
  var div = document.createElement("div");
  div.className = "zrow " + z.priority;
  div.innerHTML = "<span class='zid'>" + z.zone + "</span>" +
    "<span class='chip " + z.priority + "'>" + z.priority + "</span>" +
    "<span class='zreason'>" + z.reason + "</span>";
  zonesEl.appendChild(div);
});
if (P.evacZones.length > 6) {
  var more = document.createElement("div");
  more.className = "src";
  more.textContent = "+ " + (P.evacZones.length - 6) +
    " more zones in decisions.json";
  zonesEl.appendChild(more);
}

var poisEl = document.getElementById("pois");
var poiCss = { hospital: "#ff5c57", school: "#ba68f0", road: "#9fb2c4" };
P.pois.forEach(function (p) {
  var wet = p.depth_here_m >= P.floodDepthM;
  var div = document.createElement("div");
  div.className = "prow";
  div.innerHTML =
    "<span class='pdot' style='color:" + poiCss[p.type] + "; background:" +
    poiCss[p.type] + "'></span>" +
    "<span class='pname'>" + p.name + "<small>" + p.type + " · zone " +
    p.zone + "</small></span>" +
    "<span class='pstat " + (wet ? "wet" : "safe") + "'>" +
    (wet ? p.depth_here_m + " m" : "SAFE") + "</span>";
  poisEl.appendChild(div);
});

document.getElementById("sources").innerHTML =
  "<div class='src'><em>terrain</em><b>" + P.terrainSource + "</b></div>" +
  "<div class='src'><em>rainfall</em><b>" + P.rainSource + "</b></div>" +
  "<div class='src'><em>physics</em><b>Landlab OverlandFlow — 2D shallow " +
  "water</b></div>" +
  "<div class='src'><em>decisions</em><b>" + P.decisionSource + "</b></div>";

var rainrow = document.getElementById("rainrow");
var rainMax = Math.max.apply(null, P.rainSeries.concat([1]));
var rainBars = P.rainSeries.map(function (r) {
  var bar = document.createElement("div");
  bar.style.height = Math.max(r / rainMax * 100, 6) + "%";
  bar.innerHTML = "<i>" + r + "</i>";
  rainrow.appendChild(bar);
  return bar;
});

// ---- go
setFrame(P.nFrames - 1);
var needle = document.getElementById("needle");
addEventListener("resize", function () {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop() {
  requestAnimationFrame(loop);
  controls.update();
  var az = Math.atan2(camera.position.x - controls.target.x,
                      camera.position.z - controls.target.z);
  needle.style.transform = "rotate(" + (az * 180 / Math.PI) + "deg)";
  renderer.render(scene, camera);
})();
</script>
</body>
</html>
"""
