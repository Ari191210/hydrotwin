"""3D flood viewer for HydroTwin.

Generates a fully self-contained flood_3d.html: rotatable three.js terrain,
animated water with shimmer, 3D rainfall scaled by the actual forcing,
what-if storm scenarios (one physics run each), evacuation route arrows,
timeline event markers, a scripted presentation mode, live flood stats
(including a clearly-labeled people-affected estimate), and data sources.
three.js is inlined from assets/web_cache so the page opens with no internet.
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
from decide import _zone_rc

_HERE = os.path.dirname(os.path.abspath(__file__))
WEB_CACHE = os.path.join(_HERE, "assets", "web_cache")

PRIORITY_TINT = {"immediate": (239, 83, 80), "high": (255, 152, 0),
                 "monitor": (255, 213, 79)}


def make_3d_viewer(scenarios, elevation, cell_size, rain_source,
                   terrain_source, path=None):
    """scenarios: list of dicts from run.py (mult, times, depths,
    rain_series, decisions, decision_source, is_default)."""
    path = path or os.path.join(config.OUTPUT_DIR, "flood_3d.html")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    rows, cols = elevation.shape
    elev_north = np.flipud(elevation)  # viewer works north-row-first
    elev_b64 = base64.b64encode(elev_north.astype("<f4").tobytes()).decode()

    default_index = next(i for i, s in enumerate(scenarios) if s["is_default"])
    scen_payload = []
    for s in scenarios:
        depths_north = [np.flipud(d) for d in s["depths"]]
        depth_cm = np.stack(
            [np.clip(d * 100.0, 0, 65535) for d in depths_north])
        dec = s["decisions"]
        scen_payload.append({
            "mult": s["mult"],
            "timesS": [float(t) for t in s["times"]],
            "rain": [round(r, 1) for r in s["rain_series"]],
            "alert": str(dec.get("public_alert", "")),
            "source": s["decision_source"],
            "evacZones": dec.get("evacuation_zones", []),
            "pois": [{k: p[k] for k in
                      ("name", "type", "row", "col", "zone", "depth_here_m")}
                     for p in dec["pois"]],
            "routes": dec.get("route_vectors", []),
            "focusRc": _focus_rc(dec, rows, cols),
            "depthsB64": base64.b64encode(
                depth_cm.astype("<u2").tobytes()).decode(),
            "texZones": _zones_texture(elev_north, dec),
        })

    payload = {
        "rows": rows, "cols": cols, "cellSize": cell_size,
        "elevMin": float(elev_north.min()),
        "elevMax": float(elev_north.max()),
        "defaultIndex": default_index,
        "caseName": config.ACTIVE_CASE,
        "caseTitle": config.CASE_TITLE,
        "cases": [{"name": n, "title": c["title"].split("—")[0].strip()}
                  for n, c in config.CASES.items()],
        "lat": config.BASIN_LAT, "lon": config.BASIN_LON,
        "terrainSource": terrain_source,
        "rainSource": rain_source,
        "popDensity": config.POP_DENSITY_KM2,
        "floodDepthM": config.FLOOD_DEPTH_M,
        "scenarios": scen_payload,
    }

    html = _TEMPLATE
    for key, value in (
            ("__PAYLOAD__", json.dumps(payload)),
            ("__ELEV_B64__", elev_b64),
            ("__TEX_BASE__", _terrain_texture(elev_north)),
            ("__THREE_JS__", _read_cache("three.min.js")),
            ("__ORBIT_JS__", _read_cache("OrbitControls.js"))):
        html = html.replace(key, value)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[viewer3d] 3D viewer saved to {path} "
          f"({os.path.getsize(path) // 1024} KB, "
          f"{len(scenarios)} storm scenarios, opens offline)")
    return path


def _focus_rc(decisions, rows, cols):
    """Grid centre (south-first rc) of the worst evacuation zone, for the
    presentation-mode final shot. Falls back to the grid centre."""
    evac = decisions.get("evacuation_zones") or []
    rband, cband = rows // config.ZONE_DIV, cols // config.ZONE_DIV
    for e in evac:
        try:
            zr, zc = _zone_rc(e["zone"])
            return [int((zr + 0.5) * rband), int((zc + 0.5) * cband)]
        except (KeyError, ValueError, IndexError):
            continue
    return [rows // 2, cols // 2]


def _read_cache(name):
    fpath = os.path.join(WEB_CACHE, name)
    if not os.path.exists(fpath):
        raise FileNotFoundError(
            f"{name} missing from assets/web_cache — restore the repo copy")
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
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128167;</text></svg>">
<style>
  :root {
    --bg0: #060a10; --bg1: #0d1420; --panel: rgba(13, 19, 28, .88);
    --line: #1d2836; --line2: #2a3a4e;
    --text: #e4ecf5; --dim: #7e8ea1; --dimmer: #71829a;
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

  a:focus-visible, button:focus-visible, input:focus-visible,
  select:focus-visible { outline: 2px solid var(--accent);
    outline-offset: 2px; }

  /* ---------- header + sidebar column ---------- */
  #left { position: absolute; top: 14px; left: 14px; bottom: 138px;
    width: 344px; display: flex; flex-direction: column; gap: 10px; }
  #top { position: static; padding: 14px 20px 14px; }
  #brand { font-size: 21px; font-weight: 800; letter-spacing: 3px; }
  #brand em { font-style: normal; color: var(--accent); }
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
    background: var(--accent); }
  .case { color: var(--dim); font-size: 11.5px; margin-top: 10px; }
  #present { width: 100%; margin-top: 10px; padding: 8px 0;
    border-radius: 8px; border: 1px solid var(--accent); background: none;
    color: var(--accent); font: inherit; font-size: 12.5px; font-weight: 700;
    letter-spacing: .8px; cursor: pointer; transition: all .15s; }
  #present:hover { background: rgba(56,214,245,.12); }
  #present.running { border-color: var(--red); color: var(--red); }

  /* ---------- side ---------- */
  #side { position: static; flex: 1; min-height: 0;
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
  .stat.wide { grid-column: 1 / -1; }
  .stat.wide b { color: var(--orange); }

  .zrow { display: flex; align-items: baseline; gap: 9px; padding: 7px 10px;
    border-radius: 8px; margin-bottom: 5px; background: rgba(255,255,255,.025);
    border: 1px solid var(--line); font-size: 12px; }
  .zrow.immediate { border-color: rgba(255,92,87,.35);
    background: rgba(255,92,87,.06); }
  .zrow.high { border-color: rgba(255,171,64,.3);
    background: rgba(255,171,64,.05); }
  .zrow.monitor { border-color: rgba(255,213,79,.25);
    background: rgba(255,213,79,.04); }
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
  #playbtn { width: 44px; height: 44px; border-radius: 50%; border: none;
    cursor: pointer; font-size: 15px; color: #04151c; flex-shrink: 0;
    background: var(--accent); transition: background .15s; }
  #playbtn:hover { background: #64e2fa; }
  #playbtn:active { background: #23c3e4; }
  #sliderwrap { flex: 1; position: relative; }
  #sliderwrap input { width: 100%; accent-color: var(--accent); height: 4px;
    display: block; }
  #marks { position: absolute; left: 8px; right: 8px; top: -9px; height: 8px;
    pointer-events: none; }
  .mark { position: absolute; width: 7px; height: 7px; border-radius: 50%;
    transform: translateX(-50%); background: var(--yellow);
    border: 1.5px solid #06090d; pointer-events: auto; cursor: pointer; }
  .mark.poi { background: var(--red); }
  #tlabel { font-variant-numeric: tabular-nums; min-width: 74px;
    text-align: right; font-weight: 700; font-size: 15px;
    color: var(--accent); }
  #speed { background: rgba(255,255,255,.04); color: var(--dim);
    border: 1px solid var(--line); border-radius: 7px; padding: 5px 7px;
    font: inherit; font-size: 11.5px; }
  #hint { text-align: center; color: var(--dimmer); font-size: 10px;
    letter-spacing: .6px; margin-top: 7px; }

  /* ---------- view options ---------- */
  #view { top: 14px; right: 14px; padding: 13px 16px; width: 218px;
    font-size: 12px; }
  #vh { font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
    color: var(--dimmer); margin-bottom: 7px; }
  #storm { display: flex; gap: 5px; margin-bottom: 11px; }
  #storm button { flex: 1; padding: 6px 0; border-radius: 8px;
    border: 1px solid var(--line); background: rgba(255,255,255,.02);
    color: var(--dim); font: inherit; font-size: 12px; font-weight: 700;
    cursor: pointer; transition: all .15s; }
  #storm button:hover { color: var(--text); border-color: var(--line2); }
  #storm button.on { color: #04151c; background: var(--accent);
    border-color: transparent; }
  #view label { display: flex; gap: 8px; align-items: center;
    padding: 4.5px 0; cursor: pointer; color: var(--dim); }
  #view label:hover { color: var(--text); }
  #view input[type=checkbox] { accent-color: var(--accent); }
  #view input[type=range] { width: 100%; margin-top: 2px;
    accent-color: var(--accent); }
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
  @media (max-width: 980px) { #left { display: none; }
    #bar { width: calc(100% - 28px); } }
  @media (prefers-reduced-motion: reduce) {
    .pulse { animation: none; }
    #tabs a, #rainrow div, #playbtn, #needle, #storm button,
    #present { transition: none; }
  }
</style>
</head>
<body>
<div id="scene" role="img"
  aria-label="Rotatable 3D terrain with simulated flood water"></div>

<div id="left">
<div id="top" class="panel">
  <div id="brand">HYDRO<em>TWIN</em>
    <small>physics-informed flood intelligence</small></div>
  <nav id="tabs" aria-label="Demo case"></nav>
  <div class="case" id="caseTitle"></div>
  <button id="present">&#9654;&nbsp; RUN PRESENTATION</button>
</div>

<div id="side" class="panel">
  <div class="alert">
    <div class="alert-head"><span class="pulse"></span>FLOOD ALERT</div>
    <span id="alertText"></span>
  </div>
  <h2>Live flood state</h2>
  <div id="stats">
    <div class="stat hot"><b id="stMax">&ndash;<i>m</i></b>
      <span>peak depth</span></div>
    <div class="stat"><b id="stArea">&ndash;<i>km&sup2;</i></b>
      <span>flooded area</span></div>
    <div class="stat"><b id="stVol">&ndash;<i>Mm&sup3;</i></b>
      <span>water volume</span></div>
    <div class="stat"><b id="stZones">&ndash;</b>
      <span>zones flagged</span></div>
    <div class="stat wide"><b id="stPeople">&ndash;</b>
      <span id="stPeopleLab">people in flooded area (est.)</span></div>
  </div>
  <h2>Evacuation priorities</h2><div id="zones"></div>
  <h2>Points of interest</h2><div id="pois"></div>
  <h2>Data sources</h2><div id="sources"></div>
</div>
</div>

<div id="view" class="panel">
  <div id="vh">Storm scenario</div>
  <div id="storm" role="group" aria-label="Storm intensity"></div>
  <label><input type="checkbox" id="cbZones"> Zones &amp; escape routes</label>
  <label><input type="checkbox" id="cbRain" checked> Rainfall particles</label>
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
    <button id="playbtn" title="Play / pause (space)"
      aria-label="Play or pause the flood animation">&#9654;</button>
    <div id="sliderwrap">
      <div id="marks"></div>
      <input id="slider" type="range" min="0" value="0"
        aria-label="Simulation time">
    </div>
    <span id="tlabel"></span>
    <select id="speed" aria-label="Playback speed">
      <option value="1">1&times;</option>
      <option value="2" selected>2&times;</option>
      <option value="4">4&times;</option></select>
  </div>
  <div id="hint">drag to rotate &middot; scroll to zoom &middot; space to play
    &middot; &larr;&rarr; to step &middot; hover pins &amp; dots for detail</div>
</div>

<div id="compass" class="panel" title="North" aria-hidden="true">
  <span id="needle">N</span></div>
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
var ELEV = new Float32Array(b64Bytes("__ELEV_B64__").buffer);
var N = P.rows * P.cols;
var cellKm2 = P.cellSize * P.cellSize / 1e6;
var reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- scene scale
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
controls.autoRotate = !reduceMotion; controls.autoRotateSpeed = .55;
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
texBase.anisotropy = renderer.capabilities.getMaxAnisotropy();

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
var wBase = new Float32Array(N);      // water z before shimmer
var wWet = new Uint8Array(N);         // 1 = visible water at this vertex

// ---- rainfall particles
var RAIN_N = 2600, RAIN_H = 70;
var rainGeo = new THREE.BufferGeometry();
var rainPos = new Float32Array(RAIN_N * 3);
var rainSpd = new Float32Array(RAIN_N);
for (var r = 0; r < RAIN_N; r++) {
  rainPos[r * 3] = (Math.random() - .5) * SIZE;
  rainPos[r * 3 + 1] = Math.random() * RAIN_H;
  rainPos[r * 3 + 2] = (Math.random() - .5) * SIZE;
  rainSpd[r] = .8 + Math.random() * .5;
}
rainGeo.setAttribute("position", new THREE.BufferAttribute(rainPos, 3));
var rain = new THREE.Points(rainGeo, new THREE.PointsMaterial({
  color: 0x9fcbe8, size: 1.4, transparent: true, opacity: .38,
  sizeAttenuation: true, depthWrite: false }));
rain.visible = false;
scene.add(rain);
var rainLevel = 0;   // 0..1 intensity for the current frame

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
P.scenarios[P.defaultIndex].pois.forEach(function (p) {
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

// ---- evacuation route arrows (rebuilt per scenario)
var routeGroup = new THREE.Group();
routeGroup.visible = false;
scene.add(routeGroup);
function buildRoutes(sc) {
  while (routeGroup.children.length) {
    var c = routeGroup.children.pop();
    c.geometry.dispose(); c.material.dispose();
  }
  sc.routes.forEach(function (rt) {
    var a = gridToWorld(rt.from_rc[0], rt.from_rc[1], 4);
    var b = gridToWorld(rt.to_rc[0], rt.to_rc[1], 4);
    var mid = a.clone().lerp(b, .5); mid.y += 11;
    var curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    var col = rt.priority === "immediate" ? 0xff5c57 : 0xffab40;
    var mat = new THREE.MeshBasicMaterial({ color: col, transparent: true,
      opacity: .85 });
    var tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 24, .32, 6, false), mat);
    routeGroup.add(tube);
    var cone = new THREE.Mesh(new THREE.ConeGeometry(1.1, 2.6, 10),
      mat.clone());
    cone.position.copy(b);
    var tangent = curve.getTangent(1);
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent);
    routeGroup.add(cone);
  });
}

// ---- tooltip
var ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
var tip = document.getElementById("tip");
renderer.domElement.addEventListener("mousemove", function (e) {
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  var hit = ray.intersectObjects(poiMeshes)[0];
  if (hit) {
    var p = hit.object.userData;
    tip.innerHTML = "<b>" + p.name + "</b><br>" + p.type + " &mdash; zone " +
      p.zone + "<br>water depth here: " + p.depth_here_m + " m";
    tip.style.display = "block";
    tip.style.left = (e.clientX + 14) + "px";
    tip.style.top = (e.clientY + 10) + "px";
  } else tip.style.display = "none";
});

// ---- UI element refs
var slider = document.getElementById("slider");
var tlabel = document.getElementById("tlabel");
var playBtn = document.getElementById("playbtn");
var speedSel = document.getElementById("speed");
var stMax = document.getElementById("stMax");
var stArea = document.getElementById("stArea");
var stVol = document.getElementById("stVol");
var stPeople = document.getElementById("stPeople");
var marksEl = document.getElementById("marks");
var rainrow = document.getElementById("rainrow");
var rainBars = [];

// ---- scenario state
var cur = -1, SC = null, DEPTH = null, vmaxM = 1;

function decodeScenario(sc) {
  if (!sc._depth) sc._depth = new Uint16Array(b64Bytes(sc.depthsB64).buffer);
  if (!sc._stats) {
    sc._stats = []; sc._vmax = 1;
    var n = sc.timesS.length;
    for (var f = 0; f < n; f++) {
      var mx = 0, wet = 0, sum = 0;
      for (var i = 0; i < N; i++) {
        var d = sc._depth[f * N + i];
        if (d > mx) mx = d;
        if (d >= P.floodDepthM * 100) wet++;
        sum += d;
      }
      if (mx > sc._vmax) sc._vmax = mx;
      sc._stats.push({ max: mx / 100, areaKm2: wet * cellKm2,
        volMm3: sum / 100 * P.cellSize * P.cellSize / 1e6 });
    }
    sc._events = computeEvents(sc);
  }
  if (!sc._tex) {
    sc._tex = texLoader.load(sc.texZones);
    sc._tex.anisotropy = texBase.anisotropy;
  }
}

function computeEvents(sc) {
  var ev = [], n = sc.timesS.length, f, i;
  for (f = 0; f < n; f++)
    if (sc._stats[f].areaKm2 > 0) { ev.push({ f: f, label: "First flooding",
      poi: false }); break; }
  sc.pois.forEach(function (p) {
    var idx = (P.rows - 1 - p.row) * P.cols + p.col;
    for (f = 0; f < n; f++)
      if (sc._depth[f * N + idx] >= P.floodDepthM * 100) {
        ev.push({ f: f, label: p.name + " at risk", poi: true }); break;
      }
  });
  var best = 0;
  for (f = 1; f < n; f++)
    if (sc._stats[f].volMm3 > sc._stats[best].volMm3) best = f;
  ev.push({ f: best, label: "Peak flood", poi: false });
  return ev;
}

function setScenario(i) {
  if (i === cur) return;
  cur = i; SC = P.scenarios[i];
  decodeScenario(SC);
  DEPTH = SC._depth; vmaxM = SC._vmax / 100;
  document.getElementById("legendMax").textContent = vmaxM.toFixed(1) + " m";
  document.getElementById("stZones").textContent = SC.evacZones.length;
  document.getElementById("alertText").textContent = SC.alert;
  slider.max = SC.timesS.length - 1;

  // storm segmented control
  var btns = document.getElementById("storm").children;
  for (var k = 0; k < btns.length; k++)
    btns[k].className = k === i ? "on" : "";

  // panels that depend on the scenario
  renderZones(); renderPois(); renderSources(); renderRainBars();
  renderMarks(); buildRoutes(SC);
  poiMeshes.forEach(function (m, j) { m.userData = SC.pois[j]; });
  if (document.getElementById("cbZones").checked) {
    terrainMat.map = SC._tex; terrainMat.needsUpdate = true;
  }
  setFrame(SC.timesS.length - 1);
}

function setFrame(f) {
  f = Math.max(0, Math.min(SC.timesS.length - 1, f));
  var off = f * N;
  for (var i = 0; i < N; i++) {
    var dm = DEPTH[off + i] / 100;
    var ty = yOf(ELEV[i] - P.elevMin);
    if (dm >= .02) {
      wBase[i] = ty + yOf(dm) + .04; wWet[i] = 1;
      var t = Math.min(dm / vmaxM * 1.5, 1);
      wcol.setXYZ(i, .62 - .55 * t, .83 - .58 * t, 1 - .5 * t);
    } else {
      wBase[i] = ty - 2.5; wWet[i] = 0;
      wcol.setXYZ(i, .3, .55, .9);
    }
    wpos.setZ(i, wBase[i]);
  }
  wpos.needsUpdate = true; wcol.needsUpdate = true;
  waterGeo.computeVertexNormals();

  slider.value = f;
  var hrs = SC.timesS[f] / 3600;
  tlabel.textContent = "T+" + Math.floor(hrs) + ":" +
    ("0" + Math.round(hrs % 1 * 60)).slice(-2);
  var s = SC._stats[f];
  stMax.firstChild.textContent = s.max.toFixed(2);
  stArea.firstChild.textContent = s.areaKm2.toFixed(2);
  stVol.firstChild.textContent = s.volMm3.toFixed(2);
  stPeople.textContent = "~" +
    Math.round(s.areaKm2 * P.popDensity).toLocaleString("en");
  rainBars.forEach(function (b, h) { b.className = h < hrs ? "wet" : ""; });
  var hourIdx = Math.min(Math.floor(hrs), SC.rain.length - 1);
  var rainMax = Math.max.apply(null, SC.rain.concat([1]));
  rainLevel = hrs >= SC.rain.length ? 0 : SC.rain[hourIdx] / rainMax;
}

// ---- panel renderers
function renderZones() {
  var el = document.getElementById("zones");
  el.innerHTML = "";
  if (!SC.evacZones.length)
    el.innerHTML = "<div class='src'>No evacuation needed.</div>";
  SC.evacZones.slice(0, 6).forEach(function (z) {
    var div = document.createElement("div");
    div.className = "zrow " + z.priority;
    div.innerHTML = "<span class='zid'>" + z.zone + "</span>" +
      "<span class='chip " + z.priority + "'>" + z.priority + "</span>" +
      "<span class='zreason'>" + z.reason + "</span>";
    el.appendChild(div);
  });
  if (SC.evacZones.length > 6) {
    var more = document.createElement("div");
    more.className = "src";
    more.textContent = "+ " + (SC.evacZones.length - 6) +
      " more zones in decisions.json";
    el.appendChild(more);
  }
}

function renderPois() {
  var el = document.getElementById("pois");
  el.innerHTML = "";
  var css = { hospital: "#ff5c57", school: "#ba68f0", road: "#9fb2c4" };
  SC.pois.forEach(function (p) {
    var wet = p.depth_here_m >= P.floodDepthM;
    var div = document.createElement("div");
    div.className = "prow";
    div.innerHTML =
      "<span class='pdot' style='color:" + css[p.type] + "; background:" +
      css[p.type] + "'></span>" +
      "<span class='pname'>" + p.name + "<small>" + p.type +
      " &middot; zone " + p.zone + "</small></span>" +
      "<span class='pstat " + (wet ? "wet" : "safe") + "'>" +
      (wet ? p.depth_here_m + " m" : "SAFE") + "</span>";
    el.appendChild(div);
  });
}

function renderSources() {
  document.getElementById("sources").innerHTML =
    "<div class='src'><em>terrain</em><b>" + P.terrainSource + "</b></div>" +
    "<div class='src'><em>rainfall</em><b>" + P.rainSource + " &times; " +
    SC.mult + " scenario</b></div>" +
    "<div class='src'><em>physics</em><b>Landlab OverlandFlow &mdash; 2D " +
    "shallow water</b></div>" +
    "<div class='src'><em>decisions</em><b>" + SC.source + "</b></div>" +
    "<div class='src'><em>people</em><b>assumed " +
    P.popDensity.toLocaleString("en") + " / km&sup2; density</b></div>";
}

function renderRainBars() {
  rainrow.innerHTML = ""; rainBars = [];
  var rainMax = Math.max.apply(null, SC.rain.concat([1]));
  SC.rain.forEach(function (r) {
    var bar = document.createElement("div");
    bar.style.height = Math.max(r / rainMax * 100, 6) + "%";
    bar.innerHTML = "<i>" + r + "</i>";
    rainrow.appendChild(bar);
    rainBars.push(bar);
  });
}

function renderMarks() {
  marksEl.innerHTML = "";
  var n = SC.timesS.length - 1;
  SC._events.forEach(function (e) {
    var d = document.createElement("div");
    d.className = "mark" + (e.poi ? " poi" : "");
    d.style.left = (e.f / n * 100) + "%";
    d.title = e.label + " (T+" + (SC.timesS[e.f] / 3600).toFixed(1) + "h)";
    d.addEventListener("click", function () { setFrame(e.f); });
    marksEl.appendChild(d);
  });
}

// ---- playback
var timer = null;
function stopPlay() { clearInterval(timer); timer = null;
  playBtn.innerHTML = "&#9654;"; }
function togglePlay() {
  if (timer) { stopPlay(); return; }
  playBtn.innerHTML = "&#10074;&#10074;";
  timer = setInterval(function () {
    setFrame((+slider.value + 1) % SC.timesS.length);
  }, 420 / +speedSel.value);
}
playBtn.addEventListener("click", togglePlay);
speedSel.addEventListener("change", function () {
  if (timer) { stopPlay(); togglePlay(); }
});
slider.addEventListener("input", function () { setFrame(+slider.value); });
addEventListener("keydown", function (e) {
  if (present.running) { endPresentation(); return; }
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  if (e.code === "ArrowRight") setFrame(+slider.value + 1);
  if (e.code === "ArrowLeft") setFrame(+slider.value - 1);
});

// ---- view options
document.getElementById("cbZones").addEventListener("change", function (e) {
  terrainMat.map = e.target.checked ? SC._tex : texBase;
  terrainMat.needsUpdate = true;
  routeGroup.visible = e.target.checked;
});
document.getElementById("cbRain").addEventListener("change", function (e) {
  if (!e.target.checked) rain.visible = false;
});
document.getElementById("cbSpin").checked = !reduceMotion;
document.getElementById("cbSpin").addEventListener("change", function (e) {
  controls.autoRotate = e.target.checked;
});
document.getElementById("rgOpacity").addEventListener("input", function (e) {
  waterMat.opacity = +e.target.value / 100;
});

// ---- storm scenario control
var stormEl = document.getElementById("storm");
P.scenarios.forEach(function (sc, i) {
  var b = document.createElement("button");
  b.textContent = sc.mult + "×";
  b.title = "Storm at " + sc.mult + "× the base rainfall (" +
    Math.round(sc.rain.reduce(function (a, v) { return a + v; }, 0)) +
    " mm total)";
  b.addEventListener("click", function () { setScenario(i); });
  stormEl.appendChild(b);
});

// ---- static header
document.title = "HydroTwin — " + P.caseTitle;
document.getElementById("caseTitle").textContent =
  P.caseTitle + " · " + P.lat.toFixed(2) + ", " + P.lon.toFixed(2);
var tabs = document.getElementById("tabs");
P.cases.forEach(function (c) {
  var a = document.createElement("a");
  a.textContent = c.title;
  a.href = "../" + c.name + "/flood_3d.html";
  if (c.name === P.caseName) { a.className = "on"; a.href = "#"; }
  tabs.appendChild(a);
});

// ---- presentation mode
var present = document.getElementById("present");
present.running = false;
var pres = null;
function easeInOut(t) { return t < .5 ? 4 * t * t * t
  : 1 - Math.pow(-2 * t + 2, 3) / 2; }
function startPresentation() {
  stopPlay();
  controls.autoRotate = false; controls.enabled = false;
  var focus = gridToWorld(SC.focusRc[0], SC.focusRc[1], 0);
  pres = { t0: performance.now(), focus: focus,
    cam0: camera.position.clone(), tgt0: controls.target.clone() };
  present.running = true;
  present.innerHTML = "&#9632;&nbsp; STOP (any key)";
  present.className = "running";
  setFrame(0);
}
function endPresentation() {
  pres = null; present.running = false;
  present.innerHTML = "&#9654;&nbsp; RUN PRESENTATION";
  present.className = "";
  controls.enabled = true;
}
present.addEventListener("click", function () {
  if (present.running) endPresentation(); else startPresentation();
});
renderer.domElement.addEventListener("pointerdown", function () {
  if (present.running) endPresentation();
});
function tickPresentation(now) {
  var T = (now - pres.t0) / 1000;
  var nF = SC.timesS.length - 1;
  var center = new THREE.Vector3(0, yOf(relief) * .3, 0);
  if (T < 4) {                      // intro sweep into position
    var q = easeInOut(T / 4);
    camera.position.lerpVectors(pres.cam0,
      sph(0, SIZE * 1.15, SIZE * .6), q);
    controls.target.lerpVectors(pres.tgt0, center, q);
  } else if (T < 32) {              // storm plays while camera orbits
    var q2 = (T - 4) / 28;
    setFrame(Math.round(q2 * nF));
    var az = q2 * Math.PI * 1.5;
    camera.position.copy(sph(az, SIZE * (1.15 - .45 * q2),
      SIZE * (.6 - .22 * q2)));
    controls.target.copy(center);
  } else if (T < 38) {              // descend on the worst zone
    var q3 = easeInOut((T - 32) / 6);
    setFrame(nF);
    var end = pres.focus.clone().add(
      new THREE.Vector3(SIZE * .22, SIZE * .18, SIZE * .22));
    camera.position.lerpVectors(sph(Math.PI * 1.5, SIZE * .7, SIZE * .38),
      end, q3);
    controls.target.lerpVectors(center, pres.focus, q3);
  } else if (T < 44) {              // slow hold on the worst zone
    var az2 = (T - 38) * .1 + Math.PI * .25;
    var d = SIZE * .32;
    camera.position.set(pres.focus.x + Math.sin(az2) * d,
      pres.focus.y + SIZE * .16, pres.focus.z + Math.cos(az2) * d);
    controls.target.copy(pres.focus);
  } else endPresentation();
}
function sph(az, radius, height) {
  return new THREE.Vector3(Math.sin(az) * radius, height,
    Math.cos(az) * radius);
}

// ---- boot
setScenario(P.defaultIndex);

var needle = document.getElementById("needle");
addEventListener("resize", function () {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

var clock = new THREE.Clock();
var shimmerTick = 0;
(function loop() {
  requestAnimationFrame(loop);
  var dt = Math.min(clock.getDelta(), .1);
  var now = performance.now();

  if (pres) tickPresentation(now); else controls.update();

  // rainfall particles, scaled by the current frame's forcing
  var wantRain = rainLevel > .02 && !reduceMotion &&
    document.getElementById("cbRain").checked;
  rain.visible = wantRain;
  if (wantRain) {
    var count = Math.floor(RAIN_N * Math.pow(rainLevel, .7));
    rainGeo.setDrawRange(0, count);
    var fall = (34 + 46 * rainLevel) * dt;
    for (var r = 0; r < count; r++) {
      var y = rainPos[r * 3 + 1] - fall * rainSpd[r];
      if (y < 0) y += RAIN_H;
      rainPos[r * 3 + 1] = y;
    }
    rainGeo.attributes.position.needsUpdate = true;
  }

  // water shimmer on wet vertices
  if (!reduceMotion && SC) {
    var t = now * .0022;
    for (var i = 0; i < N; i++)
      if (wWet[i]) wpos.setZ(i, wBase[i] + Math.sin(t + i * .53) * .05);
    wpos.needsUpdate = true;
    if (++shimmerTick % 4 === 0) waterGeo.computeVertexNormals();
  }

  var az = Math.atan2(camera.position.x - controls.target.x,
                      camera.position.z - controls.target.z);
  needle.style.transform = "rotate(" + (az * 180 / Math.PI) + "deg)";
  renderer.render(scene, camera);
})();
</script>
</body>
</html>
"""
