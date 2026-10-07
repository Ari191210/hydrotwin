"""3D flood viewer for HydroTwin.

Generates a fully self-contained flood_3d.html: tone-mapped three.js terrain,
animated water with shimmer, rainfall particles tied to the forcing, what-if
storm scenarios, flood arrival-time view, live hydrograph, terrain hover
readout, dynamic scale bar, evacuation route arrows, timeline event markers,
scripted presentation mode, situation-report export, and a boot sequence.
Fonts (Space Grotesk + IBM Plex Mono) and three.js are inlined from
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
from decide import _zone_rc

_HERE = os.path.dirname(os.path.abspath(__file__))
WEB_CACHE = os.path.join(_HERE, "assets", "web_cache")

PRIORITY_TINT = {"immediate": (239, 83, 80), "high": (255, 152, 0),
                 "monitor": (255, 213, 79)}


def make_3d_viewer(scenarios, elevation, cell_size, terrain_source,
                   discharge=None, river=None, path=None, live=False,
                   issued_at=None, write=True, imagery=None,
                   water_mask=None):
    """scenarios: list of dicts from scenarios.run_all (label, mult, whatif,
    rain_source, times, depths, rain_series, decisions, decision_source,
    is_default). river: one-line river-inflow source label.
    imagery: north-up PIL image draped on the terrain (None = relief).
    water_mask: bool grid (row 0 = south) of permanent river/lake cells,
    excluded from flooded-area figures.

    write=True saves to `path` and returns the path (build mode).
    write=False returns the HTML string (server mode)."""
    html = _render_html(scenarios, elevation, cell_size, terrain_source,
                        discharge, river, live, issued_at, imagery,
                        water_mask)
    if not write:
        return html
    path = path or os.path.join(config.OUTPUT_DIR, "flood_3d.html")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[viewer3d] 3D viewer saved to {path} "
          f"({len(html) // 1024} KB, "
          f"{len(scenarios)} storm scenarios, opens offline)")
    return path


def _render_html(scenarios, elevation, cell_size, terrain_source,
                 discharge, river, live, issued_at, imagery, water_mask):
    rows, cols = elevation.shape
    elev_north = np.flipud(elevation)  # viewer works north-row-first
    base = _base_image(elev_north, imagery)
    mask_north = (np.flipud(water_mask) if water_mask is not None
                  else np.zeros(elevation.shape, bool))
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
            "label": s["label"],
            "whatif": s["whatif"],
            "rainSource": s["rain_source"],
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
            "texZones": _zones_texture(base, dec),
            "texArrival": _arrival_texture(base, depths_north, s["times"],
                                           mask_north),
        })

    payload = {
        "rows": rows, "cols": cols, "cellSize": cell_size,
        "elevMin": float(elev_north.min()),
        "elevMax": float(elev_north.max()),
        "defaultIndex": default_index,
        "caseName": config.ACTIVE_CASE,
        "caseTitle": config.CASE_TITLE,
        "cases": [] if live else
                 [{"name": n, "title": c["title"].split("—")[0].strip()}
                  for n, c in config.CASES.items()],
        "live": live,
        "issuedAt": issued_at,
        "lat": config.BASIN_LAT, "lon": config.BASIN_LON,
        "terrainSource": terrain_source,
        "terrainSynthetic": terrain_source.startswith("synthetic"),
        "riverSource": river or "not modelled at this location (rain only)",
        "imagerySource": imagery_source(imagery),
        "waterMaskB64": base64.b64encode(
            mask_north.astype(np.uint8).tobytes()).decode(),
        "popDensity": config.POP_DENSITY_KM2,
        "floodDepthM": config.FLOOD_DEPTH_M,
        "durationHr": config.SIM_DURATION_HR,
        "discharge": discharge,
        "scenarios": scen_payload,
        "surrogate": _load_surrogate(config.ACTIVE_CASE),
    }

    html = _TEMPLATE
    for key, value in (
            ("__PAYLOAD__", json.dumps(payload)),
            ("__ELEV_B64__", elev_b64),
            ("__TEX_BASE__", _to_data_uri(base, jpeg=imagery is not None)),
            ("__FONTS_CSS__", _read_cache("fonts_inline.css")),
            ("__THREE_JS__", _read_cache("three.min.js")),
            ("__ORBIT_JS__", _read_cache("OrbitControls.js"))):
        html = html.replace(key, value)
    return html


def _load_surrogate(case):
    """Per-pixel polynomial surrogate exported by surrogate_baselines.py, if
    one exists for this case. None otherwise — the viewer must not show the
    ML-preview panel at all when there isn't a fitted, validated one."""
    path = os.path.join("assets", "surrogate", f"{case}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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


def _to_data_uri(img, jpeg=False):
    buf = io.BytesIO()
    if jpeg:
        img.convert("RGB").save(buf, format="JPEG", quality=86)
        mime = "jpeg"
    else:
        img.save(buf, format="PNG")
        mime = "png"
    return f"data:image/{mime};base64," + \
        base64.b64encode(buf.getvalue()).decode()


def imagery_source(imagery):
    import imagery as imagery_mod
    return imagery_mod.ATTRIBUTION if imagery is not None else \
        "shaded relief from the DEM (satellite imagery unavailable)"


def _base_image(elev_north, imagery, max_px=2048):
    """Square-ish north-up RGB base map: satellite if we have it, otherwise
    the shaded-relief rendering of the DEM."""
    if imagery is not None:
        img = imagery.convert("RGB")
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px), Image.LANCZOS)
        return img
    img = Image.fromarray(_shade_rgb(elev_north), "RGB")
    return img.resize((1024, 1024), Image.BICUBIC)


def _zones_texture(base, decisions, size=1024):
    img = base.resize((size, size), Image.BICUBIC).convert("RGBA")
    img = Image.blend(img, Image.new("RGBA", img.size, (6, 10, 16, 255)), .35)
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
    return _to_data_uri(Image.alpha_composite(img, overlay).convert("RGB"),
                        jpeg=True)


def _arrival_texture(base, depths_north, times, water_mask, size=1024):
    """Hours until each cell first floods (>= FLOOD_DEPTH_M), plasma-colored
    over the dimmed base map; permanent water and cells that never flood
    stay dim."""
    rows, cols = depths_north[0].shape
    hours = np.full((rows, cols), np.nan)
    for t, d in zip(times, depths_north):
        newly = (d >= config.FLOOD_DEPTH_M) & np.isnan(hours)
        hours[newly] = t / 3600.0
    hours[water_mask] = np.nan
    rgba = np.zeros((rows, cols, 4), np.uint8)
    flooded = ~np.isnan(hours)
    if flooded.any():
        span = max(times[-1] / 3600.0, 1e-6)
        norm = np.clip(hours / span, 0, 1)
        colors = cm.plasma(1.0 - norm)                    # early = bright
        rgba[flooded, :3] = (colors[flooded, :3] * 255).astype(np.uint8)
        rgba[flooded, 3] = 215
    over = Image.fromarray(rgba, "RGBA").resize((size, size), Image.NEAREST)
    img = base.resize((size, size), Image.BICUBIC).convert("RGBA")
    img = Image.blend(img, Image.new("RGBA", img.size, (6, 10, 16, 255)), .5)
    return _to_data_uri(Image.alpha_composite(img, over).convert("RGB"),
                        jpeg=True)


# ------------------------------------------------------------- template ----

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin — 3D Flood Simulation</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128167;</text></svg>">
<style>
__FONTS_CSS__
  :root {
    --bg0: #04070c; --bg1: #0b111b; --panel: rgba(9, 13, 20, .92);
    --line: rgba(148, 178, 215, .10); --line2: rgba(148, 178, 215, .22);
    --text: #e6edf6; --dim: #8494a9; --dimmer: #71829a;
    --accent: #45cfe9; --red: #ff5c57; --orange: #ffab40;
    --yellow: #ffd54f; --safe: #4cd97b;
    --fd: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
    --fm: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; color: var(--text);
    font: 13.5px/1.5 var(--fd);
    background: radial-gradient(120% 90% at 70% 10%, var(--bg1), var(--bg0));
  }
  #scene { position: absolute; inset: 0; }

  .panel { position: absolute; background: var(--panel);
    border: 1px solid var(--line); border-radius: 12px;
    backdrop-filter: blur(22px) saturate(160%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.055),
      0 10px 36px rgba(0,0,0,.5); }
  .mono { font-family: var(--fm); }
  button { touch-action: manipulation; }
  #tabs a:active, #storm button:active, #vmode button:active,
  #speed:active { transform: scale(.96); }
  #present:active { transform: scale(.985); }
  #playbtn:active { transform: scale(.92); }
  #tabs a, #storm button, #vmode button, #present, #playbtn, #speed {
    transition: transform .1s ease-out, background .15s, color .15s,
      border-color .15s; }
  .zrow, .prow { transition: filter .15s ease-out; }
  .zrow:hover, .prow:hover { filter: brightness(1.35); }
  @media (prefers-reduced-transparency: reduce) {
    .panel { background: #0a0f16; backdrop-filter: none; }
  }
  body.live #brand { display: none; }
  body.live #tabs { display: none; }
  body.live #left { top: 64px; }
  body.live #view { top: 64px; }

  a:focus-visible, button:focus-visible, input:focus-visible,
  select:focus-visible { outline: 2px solid var(--accent);
    outline-offset: 2px; }

  /* ---------- boot ---------- */
  #boot { position: absolute; inset: 0; z-index: 50; background: var(--bg0);
    display: flex; align-items: center; justify-content: center;
    transition: opacity .5s; }
  #boot.hide { opacity: 0; pointer-events: none; }
  #bootbox { width: 380px; }
  #bootbox h1 { font-size: 26px; font-weight: 700; letter-spacing: 4px; }
  #bootbox h1 em { font-style: normal; color: var(--accent); }
  #bootlog { font-family: var(--fm); font-size: 11.5px; color: var(--dim);
    margin-top: 16px; min-height: 96px; }
  #bootlog div { padding: 2px 0; }
  #bootlog b { color: var(--safe); font-weight: 600; }

  /* ---------- header + sidebar column ---------- */
  #left { position: absolute; top: 14px; left: 14px; bottom: 138px;
    width: 344px; display: flex; flex-direction: column; gap: 10px; }
  #top { position: static; padding: 15px 20px 14px; }
  #brand { font-size: 21px; font-weight: 700; letter-spacing: 3.5px; }
  #brand em { font-style: normal; color: var(--accent); }
  #brand small { display: block; font-family: var(--fm); font-size: 9px;
    font-weight: 400; letter-spacing: 2.4px; text-transform: uppercase;
    color: var(--dimmer); margin-top: 3px; }
  #tabs { display: flex; gap: 6px; margin-top: 13px; }
  #tabs a { flex: 1; text-align: center; text-decoration: none;
    font-size: 11.5px; font-weight: 500; color: var(--dim);
    padding: 6px 4px; border-radius: 7px; border: 1px solid var(--line);
    background: rgba(255,255,255,.015); transition: all .15s; }
  #tabs a:hover { color: var(--text); border-color: var(--line2); }
  #tabs a.on { color: #03141b; border-color: transparent; font-weight: 700;
    background: var(--accent); }
  .case { color: var(--dim); font-family: var(--fm); font-size: 10.5px;
    margin-top: 10px; letter-spacing: .3px; }
  #present { width: 100%; margin-top: 11px; padding: 8px 0;
    border-radius: 7px; border: 1px solid var(--accent); background: none;
    color: var(--accent); font-family: var(--fd); font-size: 12.5px;
    font-weight: 700; letter-spacing: 1.2px; cursor: pointer;
    transition: all .15s; }
  #present:hover { background: rgba(69,207,233,.1); }
  #present.running { border-color: var(--red); color: var(--red); }
  #honesty { margin-top: 10px; display: flex; flex-direction: column;
    gap: 5px; }
  #honesty div { font-family: var(--fm); font-size: 10px; line-height: 1.4;
    letter-spacing: .3px; padding: 6px 9px; border-radius: 6px;
    color: var(--yellow); background: rgba(255,213,79,.1);
    border: 1px solid rgba(255,213,79,.35); }
  #honesty b { letter-spacing: 1.2px; }
  .alert.calm .alert-head { color: var(--safe); }
  .alert.calm .pulse { background: var(--safe); animation: none; }

  /* ---------- side ---------- */
  #side { position: static; flex: 1; min-height: 0;
    padding: 16px 18px; overflow-y: auto; overscroll-behavior: contain; }
  #side::-webkit-scrollbar { width: 5px; }
  #side::-webkit-scrollbar-thumb { background: var(--line2);
    border-radius: 3px; }
  h2 { font-family: var(--fm); font-size: 9.5px; letter-spacing: 2.2px;
    text-transform: uppercase; color: var(--dimmer); margin: 18px 0 9px;
    display: flex; align-items: center; gap: 8px; font-weight: 400; }
  h2::after { content: ""; flex: 1; height: 1px; background: var(--line); }
  h2:first-child { margin-top: 0; }
  h2 button { margin-left: auto; font-family: var(--fm); font-size: 9.5px;
    letter-spacing: 1px; color: var(--accent); background: none;
    border: none; cursor: pointer; text-transform: uppercase; }
  h2 button:hover { text-decoration: underline; }

  .alert { background: linear-gradient(135deg, rgba(255,92,87,.15),
    rgba(255,92,87,.05)); border: 1px solid rgba(255,92,87,.38);
    border-radius: 9px; padding: 11px 13px; font-size: 12.5px; }
  .alert-head { display: flex; align-items: center; gap: 7px;
    font-family: var(--fm); font-size: 10px; font-weight: 600;
    letter-spacing: 2px; color: var(--red); margin-bottom: 5px; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background:
    var(--red); animation: pulse 1.4s ease-out infinite; }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(255,92,87,.6); }
    100% { box-shadow: 0 0 0 9px rgba(255,92,87,0); } }

  #stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .stat { background: rgba(255,255,255,.025); border: 1px solid var(--line);
    border-radius: 9px; padding: 9px 12px 8px; }
  .stat b { display: block; font-family: var(--fm); font-size: 19px;
    font-weight: 600; font-variant-numeric: tabular-nums;
    letter-spacing: -.5px; }
  .stat b i { font-style: normal; font-size: 10.5px; font-weight: 400;
    color: var(--dim); margin-left: 3px; }
  .stat span { font-family: var(--fm); font-size: 9px;
    letter-spacing: 1.6px; text-transform: uppercase; color: var(--dimmer); }
  .stat.hot b { color: var(--accent); }
  .stat.wide { grid-column: 1 / -1; }
  .stat.wide b { color: var(--orange); }

  #hydro { margin-top: 2px; }
  #hydrocv { width: 100%; height: 74px; display: block; cursor: crosshair;
    border: 1px solid var(--line); border-radius: 8px;
    background: rgba(255,255,255,.015); }
  #hydrolab { display: flex; justify-content: space-between;
    font-family: var(--fm); font-size: 9px; color: var(--dimmer);
    letter-spacing: 1px; margin-top: 4px; text-transform: uppercase; }

  #rivernow { display: flex; align-items: baseline; gap: 10px;
    margin-bottom: 8px; }
  #rivernow b { font-family: var(--fm); font-size: 21px; font-weight: 600;
    font-variant-numeric: tabular-nums; letter-spacing: -.5px;
    color: var(--accent); }
  #rivernow b i { font-style: normal; font-size: 10.5px; font-weight: 400;
    color: var(--dim); margin-left: 3px; }
  #riverchip { font-family: var(--fm); font-size: 10px; font-weight: 600;
    letter-spacing: .8px; padding: 2.5px 9px; border-radius: 20px; }
  #riverchip.abnormal { color: var(--orange);
    background: rgba(255,171,64,.14); }
  #riverchip.normal { color: var(--safe); background: rgba(76,217,123,.1); }
  #riverbars { display: flex; align-items: flex-end; gap: 4px; height: 42px;
    margin-bottom: 6px; }
  #riverbars div { flex: 1; border-radius: 2.5px 2.5px 0 0; min-height: 4px;
    background: linear-gradient(180deg, var(--accent2), #26325e);
    position: relative; }
  #riverbars div.today { background: linear-gradient(180deg, var(--accent),
    #14586d); }
  #riverbars div i { position: absolute; bottom: -14px; width: 100%;
    text-align: center; font-style: normal; font-family: var(--fm);
    font-size: 8px; color: var(--dimmer); }
  #riverfoot { margin-top: 14px; }

  .zrow { display: flex; align-items: baseline; gap: 9px; padding: 7px 10px;
    border-radius: 8px; margin-bottom: 5px; background: rgba(255,255,255,.02);
    border: 1px solid var(--line); font-size: 12px; }
  .zrow.immediate { border-color: rgba(255,92,87,.35);
    background: rgba(255,92,87,.06); }
  .zrow.high { border-color: rgba(255,171,64,.3);
    background: rgba(255,171,64,.05); }
  .zrow.monitor { border-color: rgba(255,213,79,.25);
    background: rgba(255,213,79,.04); }
  .zid { font-family: var(--fm); font-weight: 600; font-size: 13px;
    color: var(--text); width: 26px; flex-shrink: 0; }
  .chip { font-family: var(--fm); font-size: 8.5px; font-weight: 600;
    letter-spacing: 1.2px; padding: 2px 7px; border-radius: 20px;
    text-transform: uppercase; flex-shrink: 0; }
  .chip.immediate { background: rgba(255,92,87,.16); color: var(--red); }
  .chip.high { background: rgba(255,171,64,.14); color: var(--orange); }
  .chip.monitor { background: rgba(255,213,79,.1); color: var(--yellow); }
  .zreason { color: var(--dim); font-size: 11px; line-height: 1.35; }

  .prow { display: flex; align-items: center; gap: 9px; padding: 7px 10px;
    border-radius: 8px; margin-bottom: 5px;
    background: rgba(255,255,255,.02); font-size: 12px; }
  .pdot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
  .pname { line-height: 1.25; }
  .pname small { display: block; color: var(--dimmer);
    font-family: var(--fm); font-size: 9px; text-transform: uppercase;
    letter-spacing: 1.2px; }
  .pstat { margin-left: auto; flex-shrink: 0; font-family: var(--fm);
    font-size: 10px; font-weight: 600; letter-spacing: .8px;
    padding: 2.5px 8px; border-radius: 20px; }
  .pstat.safe { color: var(--safe); background: rgba(76,217,123,.1); }
  .pstat.wet { color: var(--red); background: rgba(255,92,87,.13); }

  .src { font-family: var(--fm); font-size: 10.5px; color: var(--dim);
    padding: 2.5px 0; display: flex; gap: 8px; }
  .src em { font-style: normal; color: var(--dimmer); width: 64px;
    flex-shrink: 0; text-transform: uppercase; font-size: 9px;
    letter-spacing: 1.2px; padding-top: 1px; }
  .src b { font-weight: 600; color: var(--text); }

  /* ---------- bottom bar ---------- */
  #bar { left: 50%; transform: translateX(-50%); bottom: 14px;
    width: min(720px, calc(100% - 400px)); padding: 8px 18px 13px; }
  #readout { font-family: var(--fm); font-size: 10px; color: var(--dimmer);
    letter-spacing: .6px; text-align: center; margin-bottom: 6px;
    min-height: 15px; }
  #readout b { color: var(--accent); font-weight: 600; }
  #rainrow { display: flex; align-items: flex-end; gap: 3px; height: 32px;
    margin: 0 2px 7px; }
  #rainrow div { flex: 1; border-radius: 2px 2px 0 0; min-height: 3px;
    background: rgba(148,178,215,.14); transition: background .2s;
    position: relative; }
  #rainrow div.wet { background: linear-gradient(180deg, var(--accent),
    #14586d); }
  #rainrow div i { position: absolute; top: -13px; width: 100%;
    text-align: center; font-style: normal; font-family: var(--fm);
    font-size: 8.5px; color: var(--dimmer); }
  #controls { display: flex; align-items: center; gap: 13px; }
  #playbtn { width: 44px; height: 44px; border-radius: 50%; border: none;
    cursor: pointer; font-size: 15px; color: #03141b; flex-shrink: 0;
    background: var(--accent); transition: background .15s; }
  #playbtn:hover { background: #6adcf2; }
  #playbtn:active { background: #2fbcd8; }
  #sliderwrap { flex: 1; position: relative; }
  #sliderwrap input { width: 100%; accent-color: var(--accent); height: 4px;
    display: block; }
  #marks { position: absolute; left: 8px; right: 8px; top: -9px; height: 8px;
    pointer-events: none; }
  .mark { position: absolute; width: 7px; height: 7px; border-radius: 50%;
    transform: translateX(-50%); background: var(--yellow);
    border: 1.5px solid #05080d; pointer-events: auto; cursor: pointer; }
  .mark.poi { background: var(--red); }
  #tlabel { font-family: var(--fm); font-variant-numeric: tabular-nums;
    min-width: 78px; text-align: right; font-weight: 600; font-size: 14px;
    color: var(--accent); }
  #speed { background: rgba(255,255,255,.03); color: var(--dim);
    border: 1px solid var(--line); border-radius: 7px; padding: 5px 7px;
    font-family: var(--fm); font-size: 11px; }
  #hint { text-align: center; color: var(--dimmer); font-family: var(--fm);
    font-size: 9px; letter-spacing: .8px; margin-top: 7px;
    text-transform: uppercase; }

  /* ---------- view options ---------- */
  #view { top: 14px; right: 14px; padding: 13px 16px; width: 224px;
    font-size: 12px; }
  .vh { font-family: var(--fm); font-size: 9px; letter-spacing: 2.2px;
    text-transform: uppercase; color: var(--dimmer); margin: 0 0 7px; }
  .vh + .vh { margin-top: 12px; }
  #storm, #vmode { display: flex; gap: 5px; margin-bottom: 11px; }
  #storm button, #vmode button { flex: 1; padding: 6px 0; border-radius: 7px;
    border: 1px solid var(--line); background: rgba(255,255,255,.015);
    color: var(--dim); font-family: var(--fm); font-size: 10.5px;
    font-weight: 600; cursor: pointer; transition: all .15s;
    letter-spacing: .5px; }
  #storm button { flex: 1 1 auto; padding: 6px 6px; white-space: nowrap; }
  #storm button:hover, #vmode button:hover { color: var(--text);
    border-color: var(--line2); }
  #storm button.on, #vmode button.on { color: #03141b;
    background: var(--accent); border-color: transparent; }
  #view label { display: flex; gap: 8px; align-items: center;
    padding: 4px 0; cursor: pointer; color: var(--dim); }
  #view label:hover { color: var(--text); }
  #view input[type=checkbox] { accent-color: var(--accent); }
  #view input[type=range] { width: 100%; margin-top: 2px;
    accent-color: var(--accent); }
  #legend { margin-top: 10px; }
  .lbar { height: 8px; border-radius: 4px; }
  #legendDepth .lbar { background:
    linear-gradient(90deg, #9fd4ff, #2f7fd4, #103a80); }
  #legendArr .lbar { background:
    linear-gradient(90deg, #f0f921, #f89540, #cc4778, #7e03a8, #0d0887); }
  .llab { display: flex; justify-content: space-between;
    color: var(--dimmer); font-family: var(--fm); font-size: 9px;
    margin-top: 3px; letter-spacing: .5px; }
  #mlpanel .vh { display: flex; justify-content: space-between;
    align-items: center; }
  #mlToggle { font-family: var(--fm); font-size: 9px; letter-spacing: 1px;
    padding: 3px 9px; border-radius: 10px; border: 1px solid var(--line2);
    background: none; color: var(--dim); cursor: pointer; }
  #mlToggle.on { color: #03141b; background: var(--yellow);
    border-color: transparent; }
  #mlbody label { display: block; color: var(--dim); font-size: 11px;
    margin-top: 8px; }
  #mlbody label b { color: var(--text); float: right; font-weight: 600; }
  #mlbody input[type=range] { width: 100%; margin-top: 3px;
    accent-color: var(--yellow); }
  #mlStats { margin-top: 8px; flex-direction: column; gap: 2px; }
  #mlNote { color: var(--dimmer); font-size: 9.5px; line-height: 1.4;
    margin-top: 6px; white-space: normal; }

  /* ---------- HUD bottom right ---------- */
  #scale { position: absolute; right: 22px; bottom: 88px; text-align: right; }
  #scalebar { height: 4px; border: 1px solid var(--dim); border-top: none;
    margin-left: auto; }
  #scalelab { font-family: var(--fm); font-size: 9.5px; color: var(--dim);
    letter-spacing: 1px; margin-bottom: 2px; }
  #compass { position: absolute; right: 22px; bottom: 22px; width: 52px;
    height: 52px; border-radius: 50%; background: var(--panel);
    border: 1px solid var(--line); display: flex; align-items: center;
    justify-content: center; }
  #needle { font-family: var(--fm); font-size: 14px; font-weight: 600;
    color: var(--red); transition: transform .1s linear; }

  #tip { position: absolute; display: none; pointer-events: none;
    background: #04070b; border: 1px solid var(--accent); border-radius: 8px;
    padding: 8px 12px; font-size: 12px; z-index: 10; max-width: 250px;
    box-shadow: 0 6px 24px rgba(0,0,0,.6); }
  #tip b { color: var(--accent); }
  @media (max-width: 980px) { #left { display: none; }
    #bar { width: calc(100% - 28px); } }
  @media (prefers-reduced-motion: reduce) {
    .pulse { animation: none; }
    #boot { transition: none; }
    #tabs a, #rainrow div, #playbtn, #needle, #storm button,
    #vmode button, #present { transition: none; }
  }
</style>
</head>
<body>
<div id="scene" role="img"
  aria-label="Rotatable 3D terrain with simulated flood water"></div>

<div id="boot"><div id="bootbox">
  <h1>HYDRO<em>TWIN</em></h1>
  <div id="bootlog"></div>
</div></div>

<div id="left">
<div id="top" class="panel">
  <div id="brand">HYDRO<em>TWIN</em>
    <small>physics-informed flood intelligence</small></div>
  <nav id="tabs" aria-label="Demo case"></nav>
  <div class="case" id="caseTitle"></div>
  <div id="honesty" role="status"></div>
  <button id="present">&#9654;&nbsp; RUN PRESENTATION</button>
</div>

<div id="side" class="panel">
  <div class="alert">
    <div class="alert-head"><span class="pulse"></span><span
      id="alertHead">FLOOD ALERT</span></div>
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
      <span>people in flooded area (est.)</span></div>
  </div>
  <h2>Hydrograph</h2>
  <div id="hydro"><canvas id="hydrocv"></canvas>
    <div id="hydrolab"><span>flooded area</span><span>volume</span></div>
  </div>
  <div id="riversec" style="display:none">
    <h2 id="riverhead">River discharge</h2>
    <div id="river">
      <div id="rivernow"><b id="riverval"></b><span id="riverchip"></span></div>
      <div id="riverbars"></div>
      <div id="riverfoot" class="src"></div>
    </div>
  </div>
  <h2>Evacuation priorities</h2><div id="zones"></div>
  <h2>Points of interest</h2><div id="pois"></div>
  <h2>Data sources
    <button id="sitrep" title="Download situation report">&#10515;
      sitrep</button></h2>
  <div id="sources"></div>
</div>
</div>

<div id="view" class="panel">
  <div class="vh">Rain scenario</div>
  <div id="storm" role="group" aria-label="Storm intensity"></div>
  <div class="vh">Terrain view</div>
  <div id="vmode" role="group" aria-label="Terrain view mode"></div>
  <label><input type="checkbox" id="cbRain" checked> Rainfall particles</label>
  <label><input type="checkbox" id="cbSpin" checked> Auto-rotate</label>
  <label style="display:block; margin-top:6px;">Water opacity
    <input type="range" id="rgOpacity" min="30" max="100" value="84"></label>
  <div id="legend">
    <div id="legendDepth"><div class="lbar"></div>
      <div class="llab"><span>0 m</span><span id="legendMax"></span></div>
    </div>
    <div id="legendArr" style="display:none"><div class="lbar"></div>
      <div class="llab"><span>floods first</span><span>floods last</span></div>
    </div>
  </div>
  <div id="mlpanel" style="display:none">
    <div class="vh">ML instant preview <button id="mlToggle">OFF</button></div>
    <div id="mlbody" style="display:none">
      <label>Rain total <b id="mlRainLab"></b>
        <input type="range" id="mlRain" min="0" max="100" value="25"></label>
      <label>River excess <b id="mlRiverLab"></b>
        <input type="range" id="mlRiver" min="0" max="100" value="25"></label>
      <div id="mlStats" class="src"></div>
      <div id="mlNote" class="src"></div>
    </div>
  </div>
</div>

<div id="bar" class="panel">
  <div id="readout">hover terrain for readout</div>
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
  <div id="hint">drag rotate &middot; scroll zoom &middot; space play &middot;
    &larr;&rarr; step &middot; hover pins &amp; dots</div>
</div>

<div id="scale"><div id="scalelab"></div><div id="scalebar"></div></div>
<div id="compass" class="panel" title="North" aria-hidden="true">
  <span id="needle">N</span></div>
<div id="tip"></div>

<script>__THREE_JS__</script>
<script>__ORBIT_JS__</script>
<script>
"use strict";
var P = __PAYLOAD__;

// ---- boot log
var bootLog = document.getElementById("bootlog");
var reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
var bootSteps = [];
function bootSay(msg) { bootSteps.push(msg); }
function bootFlush(done) {
  var i = 0;
  function next() {
    if (i < bootSteps.length) {
      var d = document.createElement("div");
      d.innerHTML = "&gt; " + bootSteps[i] + " <b>ok</b>";
      bootLog.appendChild(d); i++;
      setTimeout(next, reduceMotion ? 0 : 130);
    } else done();
  }
  next();
}

function b64Bytes(b64) {
  var bin = atob(b64), out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
var ELEV = new Float32Array(b64Bytes("__ELEV_B64__").buffer);
var N = P.rows * P.cols;
var cellKm2 = P.cellSize * P.cellSize / 1e6;
bootSay("terrain grid " + P.rows + "&times;" + P.cols + " decoded");

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
var rim = new THREE.DirectionalLight(0x3d6a9e, .25);
rim.position.set(SIZE, SIZE * .3, -SIZE);
scene.add(rim);

// ---- terrain
var texLoader = new THREE.TextureLoader();
function loadTex(uri) {
  var t = texLoader.load(uri);
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return t;
}
var texBase = loadTex("__TEX_BASE__");

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
bootSay("terrain mesh built (" + (P.rows * P.cols) + " vertices)");

// ---- water
var waterGeo = new THREE.PlaneGeometry(SIZE, SIZE, P.cols - 1, P.rows - 1);
var wpos = waterGeo.attributes.position;
var wcol = new THREE.BufferAttribute(new Float32Array(wpos.count * 3), 3);
waterGeo.setAttribute("color", wcol);
var waterMat = new THREE.MeshPhongMaterial({ vertexColors: true,
  transparent: true, opacity: .84, shininess: 150, specular: 0x46658a });
var water = new THREE.Mesh(waterGeo, waterMat);
water.rotation.x = -Math.PI / 2;
scene.add(water);
var wBase = new Float32Array(N);
var wWet = new Uint8Array(N);

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
var rainLevel = 0;

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
    new THREE.MeshLambertMaterial({ color: poiColors[p.type] || 0x45cfe9,
      emissive: poiColors[p.type] || 0x45cfe9, emissiveIntensity: .4 }));
  head.position.copy(pos); head.position.y += h;
  head.userData = p;
  scene.add(head);
  poiMeshes.push(head);
});
bootSay(P.scenarios[P.defaultIndex].pois.length +
  " points of interest placed");

// ---- evacuation route arrows
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
    routeGroup.add(new THREE.Mesh(
      new THREE.TubeGeometry(curve, 24, .32, 6, false), mat));
    var cone = new THREE.Mesh(new THREE.ConeGeometry(1.1, 2.6, 10),
      mat.clone());
    cone.position.copy(b);
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0),
      curve.getTangent(1));
    routeGroup.add(cone);
  });
}

// ---- pointer: POI tooltip + terrain readout
var ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
var tip = document.getElementById("tip");
var readout = document.getElementById("readout");
var dLat = P.rows * P.cellSize / 111320;
var dLon = P.cols * P.cellSize /
  (111320 * Math.cos(P.lat * Math.PI / 180));
renderer.domElement.addEventListener("mousemove", function (e) {
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  var hitPoi = ray.intersectObjects(poiMeshes)[0];
  if (hitPoi) {
    var p = hitPoi.object.userData;
    tip.innerHTML = "<b>" + p.name + "</b><br>" + p.type + " &mdash; zone " +
      p.zone + "<br>water depth here: " + p.depth_here_m + " m";
    tip.style.display = "block";
    tip.style.left = (e.clientX + 14) + "px";
    tip.style.top = (e.clientY + 10) + "px";
  } else tip.style.display = "none";

  var hitT = ray.intersectObject(terrain)[0];
  if (hitT && hitT.uv && SC) {
    var col = Math.round(hitT.uv.x * (P.cols - 1));
    var rN = Math.round((1 - hitT.uv.y) * (P.rows - 1));
    var idx = rN * P.cols + col;
    var d = DEPTH[(+slider.value) * N + idx] / 100;
    var zb = Math.min(Math.floor(rN / (P.rows / 4)), 3);
    var cb = Math.min(Math.floor(col / (P.cols / 4)), 3);
    var lat = (P.lat + dLat / 2) - (rN / (P.rows - 1)) * dLat;
    var lon = (P.lon - dLon / 2) + (col / (P.cols - 1)) * dLon;
    readout.innerHTML = "ELEV <b>" + Math.round(ELEV[idx]) + " m</b>" +
      " &nbsp;&middot;&nbsp; WATER <b>" +
      (d >= .01 ? d.toFixed(2) + " m" : "dry") + "</b>" +
      " &nbsp;&middot;&nbsp; ZONE <b>" +
      String.fromCharCode(65 + zb) + (cb + 1) + "</b>" +
      " &nbsp;&middot;&nbsp; " + lat.toFixed(3) + "&deg;, " +
      lon.toFixed(3) + "&deg;";
  }
});
renderer.domElement.addEventListener("mouseleave", function () {
  readout.textContent = "hover terrain for readout";
});

// ---- UI refs
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
var hydroCv = document.getElementById("hydrocv");

// ---- fluid motion: critically damped springs (Apple-style)
function Spring(x) { this.x = x; this.v = 0; this.target = x;
  this.done = true; }
Spring.prototype.step = function (dt, response) {
  if (this.done) return this.x;
  var w = 2 * Math.PI / (response || .4);
  var a = -w * w * (this.x - this.target) - 2 * w * this.v;
  this.v += a * dt; this.x += this.v * dt;
  if (Math.abs(this.x - this.target) < 5e-4 && Math.abs(this.v) < 5e-4) {
    this.x = this.target; this.v = 0; this.done = true;
  }
  return this.x;
};
Spring.prototype.to = function (t) { this.target = t; this.done = false; };
Spring.prototype.jump = function (t) { this.x = t; this.target = t;
  this.v = 0; this.done = true; };

// ---- scenario state
var cur = -1, SC = null, DEPTH = null, vmaxM = 1;
var viewMode = "terrain";   // terrain | zones | arrival
var frameF = 0;             // continuous playhead (fractional frames)
var playing = false;
var PLAY_RATE = 2.2;        // frames per second at 1x speed
var seekSpring = new Spring(0);
var morphS = new Spring(1); // 0..1 blend from previous scenario's water
var morphFrom = new Float32Array(N);
var lastDm = new Float32Array(N);
var vmaxFrom = 1;
var shown = { f: -1, hour: -1, max: 0, areaKm2: 0, volMm3: 0 };
var waterDirty = true;

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
  if (!sc._tex) sc._tex = loadTex(sc.texZones);
  if (!sc._texArr) sc._texArr = loadTex(sc.texArrival);
}

function computeEvents(sc) {
  var ev = [], n = sc.timesS.length, f;
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

function applyViewMode() {
  terrainMat.map = viewMode === "zones" ? SC._tex :
    viewMode === "arrival" ? SC._texArr : texBase;
  terrainMat.needsUpdate = true;
  routeGroup.visible = viewMode === "zones";
  water.visible = viewMode !== "arrival";
  document.getElementById("legendDepth").style.display =
    viewMode === "arrival" ? "none" : "";
  document.getElementById("legendArr").style.display =
    viewMode === "arrival" ? "" : "none";
  var btns = document.getElementById("vmode").children;
  var modes = ["terrain", "zones", "arrival"];
  for (var k = 0; k < btns.length; k++)
    btns[k].className = modes[k] === viewMode ? "on" : "";
}

function setScenario(i) {
  if (i === cur) return;
  var hadPrev = SC !== null;
  if (hadPrev && !reduceMotion) {
    morphFrom.set(lastDm);        // melt from the water you're looking at
    vmaxFrom = vmaxM;
    morphS.x = 0; morphS.v = 0; morphS.to(1);
  }
  cur = i; SC = P.scenarios[i];
  decodeScenario(SC);
  DEPTH = SC._depth; vmaxM = SC._vmax / 100;
  document.getElementById("legendMax").textContent = vmaxM.toFixed(1) + " m";
  document.getElementById("stZones").textContent = SC.evacZones.length;
  document.getElementById("alertText").textContent = SC.alert;
  var calm = !SC.evacZones.some(function (z) {
    return z.priority === "immediate" || z.priority === "high"; });
  document.querySelector(".alert").classList.toggle("calm", calm);
  document.getElementById("alertHead").textContent =
    calm ? "NO FLOOD EXPECTED" : "FLOOD ALERT";
  renderHonesty();
  slider.max = SC.timesS.length - 1;

  var btns = document.getElementById("storm").children;
  for (var k = 0; k < btns.length; k++)
    btns[k].className = k === i ? "on" : "";

  renderZones(); renderPois(); renderSources(); renderRainBars();
  renderMarks(); buildRoutes(SC); applyViewMode();
  poiMeshes.forEach(function (m, j) { m.userData = SC.pois[j]; });
  setFrame(SC.timesS.length - 1);
}

// jump the playhead (scrub, arrows, presentation). Cancels any glide.
function setFrame(f) {
  seekSpring.done = true;
  frameF = Math.max(0, Math.min(SC.timesS.length - 1, f));
  waterDirty = true;
}

// glide the playhead there on a spring (event marks, hydrograph clicks)
function seekTo(f) {
  playing = false; playBtn.innerHTML = "&#9654;";
  if (reduceMotion) { setFrame(f); return; }
  seekSpring.x = frameF; seekSpring.v = 0; seekSpring.to(f);
}

function statAt(f) {  // stats interpolated between sim snapshots
  var i0 = Math.floor(f), i1 = Math.min(i0 + 1, SC._stats.length - 1);
  var t = f - i0, a = SC._stats[i0], b = SC._stats[i1];
  return { max: a.max + (b.max - a.max) * t,
    areaKm2: a.areaKm2 + (b.areaKm2 - a.areaKm2) * t,
    volMm3: a.volMm3 + (b.volMm3 - a.volMm3) * t };
}

// per-rAF UI sync — only touches the DOM when a shown value changed
function syncUI() {
  if (Math.abs(frameF - shown.f) < .005 && morphS.done) return;
  shown.f = frameF;
  var n = SC.timesS.length;
  var i0 = Math.floor(frameF), i1 = Math.min(i0 + 1, n - 1);
  var tf = frameF - i0;
  var tS = SC.timesS[i0] + (SC.timesS[i1] - SC.timesS[i0]) * tf;
  var hrs = tS / 3600;
  tlabel.textContent = "T+" + Math.floor(hrs) + ":" +
    ("0" + Math.floor(hrs % 1 * 60)).slice(-2);
  if (+slider.value !== Math.round(frameF))
    slider.value = Math.round(frameF);

  var mq = morphS.x, s = statAt(frameF);
  if (mq < 1) {
    s = { max: shown.morphMax + (s.max - shown.morphMax) * mq,
      areaKm2: shown.morphArea + (s.areaKm2 - shown.morphArea) * mq,
      volMm3: shown.morphVol + (s.volMm3 - shown.morphVol) * mq };
  } else { shown.morphMax = s.max; shown.morphArea = s.areaKm2;
    shown.morphVol = s.volMm3; }
  stMax.firstChild.textContent = s.max.toFixed(2);
  stArea.firstChild.textContent = s.areaKm2.toFixed(2);
  stVol.firstChild.textContent = s.volMm3.toFixed(2);
  stPeople.textContent = "~" +
    Math.round(s.areaKm2 * P.popDensity).toLocaleString("en");

  var hour = Math.floor(hrs);
  if (hour !== shown.hour) {
    shown.hour = hour;
    rainBars.forEach(function (b, h) { b.className = h < hrs ? "wet" : ""; });
  }
  var rainMax = Math.max.apply(null, SC.rain.concat([1]));
  rainLevel = hrs >= SC.rain.length ? 0
    : SC.rain[Math.min(hour, SC.rain.length - 1)] / rainMax;
  drawHydro(frameF);
}

// compose the water surface: sub-frame interpolation + scenario morph
// + shimmer, in one pass over the grid
function updateWater(nowMs) {
  var n = SC.timesS.length;
  var i0 = Math.floor(frameF), i1 = Math.min(i0 + 1, n - 1);
  var tf = frameF - i0, off0 = i0 * N, off1 = i1 * N;
  var mq = morphS.x;
  var vEff = mq < 1 ? vmaxFrom + (vmaxM - vmaxFrom) * mq : vmaxM;
  var shimmerOn = !reduceMotion && water.visible;
  var st = nowMs * .0022;
  for (var i = 0; i < N; i++) {
    var dm = (DEPTH[off0 + i] * (1 - tf) + DEPTH[off1 + i] * tf) / 100;
    if (mq < 1) dm = morphFrom[i] + (dm - morphFrom[i]) * mq;
    lastDm[i] = dm;
    var ty = yOf(ELEV[i] - P.elevMin);
    if (dm >= .02) {
      wWet[i] = 1;
      var z = ty + yOf(dm) + .04;
      wpos.setZ(i, shimmerOn ? z + Math.sin(st + i * .53) * .05 : z);
      var t = Math.min(dm / vEff * 1.5, 1);
      wcol.setXYZ(i, .62 - .55 * t, .83 - .58 * t, 1 - .5 * t);
    } else {
      wWet[i] = 0;
      wpos.setZ(i, ty - 2.5);
      wcol.setXYZ(i, .3, .55, .9);
    }
  }
  wpos.needsUpdate = true; wcol.needsUpdate = true;
  if (++shimmerTick % 3 === 0 || waterDirty)
    waterGeo.computeVertexNormals();
  waterDirty = false;
}

// ---- hydrograph
function drawHydro(f) {
  var w = hydroCv.clientWidth, h = hydroCv.clientHeight;
  if (hydroCv.width !== w * 2) { hydroCv.width = w * 2;
    hydroCv.height = h * 2; }
  var g = hydroCv.getContext("2d");
  g.setTransform(2, 0, 0, 2, 0, 0);
  g.clearRect(0, 0, w, h);
  var st = SC._stats, n = st.length;
  var maxA = .001, maxV = .001;
  for (var i = 0; i < n; i++) {
    if (st[i].areaKm2 > maxA) maxA = st[i].areaKm2;
    if (st[i].volMm3 > maxV) maxV = st[i].volMm3;
  }
  var pad = 4;
  function X(i) { return pad + i / (n - 1) * (w - 2 * pad); }
  function YA(v) { return h - pad - v / maxA * (h - 2 * pad); }
  function YV(v) { return h - pad - v / maxV * (h - 2 * pad); }
  // flooded area — filled
  g.beginPath(); g.moveTo(X(0), h - pad);
  for (i = 0; i < n; i++) g.lineTo(X(i), YA(st[i].areaKm2));
  g.lineTo(X(n - 1), h - pad); g.closePath();
  g.fillStyle = "rgba(69,207,233,.16)"; g.fill();
  g.beginPath();
  for (i = 0; i < n; i++)
    i ? g.lineTo(X(i), YA(st[i].areaKm2)) : g.moveTo(X(i), YA(st[i].areaKm2));
  g.strokeStyle = "#45cfe9"; g.lineWidth = 1.6; g.stroke();
  // volume — thin line
  g.beginPath();
  for (i = 0; i < n; i++)
    i ? g.lineTo(X(i), YV(st[i].volMm3)) : g.moveTo(X(i), YV(st[i].volMm3));
  g.strokeStyle = "rgba(132,148,169,.8)"; g.lineWidth = 1; g.stroke();
  // cursor
  g.beginPath(); g.moveTo(X(f), pad); g.lineTo(X(f), h - pad);
  g.strokeStyle = "rgba(230,237,246,.55)"; g.lineWidth = 1; g.stroke();
}
function hydroFrame(e) {
  var r = hydroCv.getBoundingClientRect();
  var q = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  return q * (SC.timesS.length - 1);
}
hydroCv.addEventListener("click", function (e) { seekTo(hydroFrame(e)); });
hydroCv.addEventListener("mousemove", function (e) {
  if (e.buttons === 1) setFrame(hydroFrame(e));   // 1:1 while dragging
});

// ---- field reports (live server): the shell posts escalate-only zone
// updates triaged by Laya; they apply to the default storm scenario.
window.addEventListener("message", function (e) {
  var m = e.data;
  if (!m || m.type !== "hydrotwin:zones" || !Array.isArray(m.evacZones)) return;
  P.scenarios[P.defaultIndex].evacZones = m.evacZones;
  if (cur === P.defaultIndex) {
    document.getElementById("stZones").textContent = SC.evacZones.length;
    renderZones();
  }
});

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
  });
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
    div.innerHTML = "<span class='zid'>" + escHtml(z.zone) + "</span>" +
      "<span class='chip " + escHtml(z.priority) + "'>" +
      escHtml(z.priority) + "</span>" +
      "<span class='zreason'>" + escHtml(z.reason) + "</span>";
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
      "<span class='pdot' style='background:" + css[p.type] + "'></span>" +
      "<span class='pname'>" + p.name + "<small>" + p.type +
      " &middot; zone " + p.zone + "</small></span>" +
      "<span class='pstat " + (wet ? "wet" : "safe") + "'>" +
      (wet ? p.depth_here_m + " m" : "SAFE") + "</span>";
    el.appendChild(div);
  });
}

// Anything on screen that is not the real forecast over real ground says so
function renderHonesty() {
  var msgs = [];
  if (P.terrainSynthetic)
    msgs.push("<b>SYNTHETIC TERRAIN</b> &mdash; the elevation download " +
      "failed; this ground shape is invented, not " + P.caseTitle + ".");
  if (SC.whatif)
    msgs.push("<b>WHAT-IF: " + SC.label.toUpperCase() + "</b> &mdash; " +
      (SC.rainSource.indexOf("design storm") === 0
        ? "a synthetic storm, not the forecast."
        : "the forecast rain &times;" + SC.mult + ", not the forecast."));
  document.getElementById("honesty").innerHTML = msgs.map(function (m) {
    return "<div>" + m + "</div>";
  }).join("");
}

function renderSources() {
  document.getElementById("sources").innerHTML =
    "<div class='src'><em>terrain</em><b>" + P.terrainSource + "</b></div>" +
    "<div class='src'><em>imagery</em><b>" + P.imagerySource + "</b></div>" +
    "<div class='src'><em>rainfall</em><b>" + SC.rainSource +
    (SC.mult !== 1 ? " &times; " + SC.mult : "") + "</b></div>" +
    "<div class='src'><em>river</em><b>" + P.riverSource + "</b></div>" +
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
    d.addEventListener("click", function () { seekTo(e.f); });
    marksEl.appendChild(d);
  });
}

// ---- situation report export
document.getElementById("sitrep").addEventListener("click", function () {
  var f = +slider.value, s = SC._stats[f];
  var lines = [
    "HYDROTWIN SITUATION REPORT",
    "==========================",
    "Case      : " + P.caseTitle + " (" + P.lat + ", " + P.lon + ")",
    "Scenario  : " + SC.label + (SC.whatif ? " (WHAT-IF)" : "") + " (" +
      Math.round(SC.rain.reduce(function (a, v) { return a + v; }, 0)) +
      " mm over " + SC.rain.length + " h)",
    "Sim time  : T+" + (SC.timesS[f] / 3600).toFixed(2) + " h",
    "",
    "Peak depth    : " + s.max.toFixed(2) + " m",
    "Flooded area  : " + s.areaKm2.toFixed(2) + " km2",
    "Water volume  : " + s.volMm3.toFixed(2) + " Mm3",
    "People (est.) : ~" + Math.round(s.areaKm2 * P.popDensity) +
      " (assumed " + P.popDensity + "/km2)",
    "",
    "PUBLIC ALERT",
    SC.alert,
    "",
    "EVACUATION ZONES (" + SC.evacZones.length + ")"];
  SC.evacZones.forEach(function (z) {
    lines.push("  [" + z.priority.toUpperCase() + "] " + z.zone + " — " +
      z.reason);
  });
  lines.push("", "POINTS OF INTEREST");
  SC.pois.forEach(function (p) {
    lines.push("  " + p.name + " (" + p.type + ", zone " + p.zone + "): " +
      (p.depth_here_m >= P.floodDepthM ? p.depth_here_m + " m of water"
        : "safe"));
  });
  lines.push("", "SOURCES",
    "  terrain   : " + P.terrainSource,
    "  rainfall  : " + SC.rainSource + " x" + SC.mult,
    "  river     : " + P.riverSource,
    "  physics   : Landlab OverlandFlow (2D shallow water)",
    "  decisions : " + SC.source, "");
  var blob = new Blob([lines.join("\n")], { type: "text/plain" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "hydrotwin_sitrep_" + P.caseName + "_" +
    SC.label.replace(/[^a-z0-9]+/gi, "") + ".txt";
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---- playback (rAF-driven, continuous)
function stopPlay() { playing = false; playBtn.innerHTML = "&#9654;"; }
function togglePlay() {
  seekSpring.done = true;
  if (playing) { stopPlay(); return; }
  if (frameF >= SC.timesS.length - 1.01) frameF = 0;  // replay from start
  playing = true;
  playBtn.innerHTML = "&#10074;&#10074;";
}
playBtn.addEventListener("click", togglePlay);
slider.addEventListener("input", function () { setFrame(+slider.value); });
addEventListener("keydown", function (e) {
  if (present.running) { endPresentation(); return; }
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  if (e.code === "ArrowRight") setFrame(Math.round(frameF) + 1);
  if (e.code === "ArrowLeft") setFrame(Math.round(frameF) - 1);
});

// ---- view options
var vmodeEl = document.getElementById("vmode");
[["terrain", "TERRAIN"], ["zones", "ZONES"], ["arrival", "ARRIVAL"]]
  .forEach(function (m) {
    var b = document.createElement("button");
    b.textContent = m[1];
    b.title = m[0] === "arrival"
      ? "When flood water first reaches each cell" : "";
    b.addEventListener("click", function () {
      viewMode = m[0]; applyViewMode();
    });
    vmodeEl.appendChild(b);
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

// ---- live river discharge (GloFAS)
if (P.discharge) {
  var D = P.discharge;
  document.getElementById("riversec").style.display = "";
  document.getElementById("riverhead").textContent =
    "River discharge — GloFAS " + (D.live ? "live" : "cached");
  document.getElementById("riverval").innerHTML =
    Math.round(D.today).toLocaleString("en") + "<i>m&sup3;/s</i>";
  var chip = document.getElementById("riverchip");
  var pct = D.pct_of_median;
  chip.textContent = (pct >= 0 ? "+" : "") + pct.toFixed(0) +
    "% vs 1995–2024 normal for this date";
  chip.className = Math.abs(pct) > 15 ? "abnormal" : "normal";
  var barsEl = document.getElementById("riverbars");
  var dmax = Math.max.apply(null, D.discharge.concat([1]));
  D.discharge.forEach(function (v, i) {
    var b = document.createElement("div");
    b.style.height = Math.max(v / dmax * 100, 8) + "%";
    if (i === 0) b.className = "today";
    b.title = D.days[i] + ": " + Math.round(v).toLocaleString("en") +
      " m³/s (1995–2024 median " + Math.round(D.median[i]).toLocaleString("en") + ")";
    b.innerHTML = "<i>" + D.days[i].slice(8) + "</i>";
    barsEl.appendChild(b);
  });
  document.getElementById("riverfoot").innerHTML =
    "<em>source</em><b>Copernicus GloFAS via Open-Meteo Flood API" +
    (D.live ? "" : " — cached " + D.fetched_at.slice(0, 10)) +
    ", 7-day forecast</b>";
  bootSay("GloFAS river discharge " + (D.live ? "linked (live)"
    : "loaded (cached)"));
}

// ---- storm scenario control
var stormEl = document.getElementById("storm");
P.scenarios.forEach(function (sc, i) {
  var b = document.createElement("button");
  b.textContent = sc.label;
  b.title = (sc.whatif ? "What-if: " : "As forecast: ") + sc.rainSource +
    (sc.mult !== 1 ? " ×" + sc.mult : "") + " (" +
    Math.round(sc.rain.reduce(function (a, v) { return a + v; }, 0)) +
    " mm total)";
  b.addEventListener("click", function () { setScenario(i); });
  stormEl.appendChild(b);
});
bootSay(P.scenarios.length + " storm scenarios hydrated");

// ---- ML instant preview: a per-pixel cubic polynomial fit to 380 of this
// project's own Landlab physics runs (held-out RMSE/IoU in P.surrogate.
// metrics). It replaces nothing — it's an isolated extra panel so a bad
// slider value can never corrupt the validated scenario/physics state.
var mlActive = false, mlCoef = null;
if (P.surrogate) {
  var S = P.surrogate;
  mlCoef = new Float32Array(b64Bytes(S.coefB64).buffer);  // (10, N)
  document.getElementById("mlpanel").style.display = "";
  var mlRain = document.getElementById("mlRain");
  var mlRiver = document.getElementById("mlRiver");
  var mlRainLab = document.getElementById("mlRainLab");
  var mlRiverLab = document.getElementById("mlRiverLab");
  document.getElementById("mlNote").textContent =
    "Fit to " + S.metrics.method + ". Held-out accuracy: RMSE " +
    S.metrics.rmse_m.toFixed(2) + " m, wet-area IoU " +
    S.metrics.iou.toFixed(2) + ". Not the validated physics result " +
    "shown elsewhere in this viewer — an instant approximation of it.";

  function mlFeat(r, q) {
    return [1, r, q, r * r, q * q, r * q, r ** 3, q ** 3, r * r * q, r * q * q];
  }

  function computeML() {
    var rainFrac = +mlRain.value / 100, riverFrac = +mlRiver.value / 100;
    var rainMm = rainFrac * S.rain_max * 96;  // rain_max=4 units * 96mm/unit
    var riverQ = riverFrac * S.river_qmax;
    mlRainLab.textContent = Math.round(rainMm) + " mm";
    mlRiverLab.textContent = Math.round(riverQ) + " m³/s";
    var r = rainFrac * S.rain_max, q = riverQ / S.q_scale;
    var f = mlFeat(r, q), depth = new Float32Array(N);
    var maxD = 0, wetCells = 0;
    for (var i = 0; i < N; i++) {
      var v = 0;
      for (var k = 0; k < 10; k++) v += f[k] * mlCoef[k * N + i];
      if (v < 0) v = 0;
      depth[i] = v;
      if (v > maxD) maxD = v;
      if (v >= P.floodDepthM) wetCells++;
    }
    document.getElementById("mlStats").innerHTML =
      "<div class='src'><em>peak depth</em><b>" + maxD.toFixed(2) +
      " m</b></div><div class='src'><em>flooded area</em><b>" +
      (wetCells * P.cellSize * P.cellSize / 1e6).toFixed(2) +
      " km²</b></div>";
    return depth;
  }

  function updateWaterML() {
    var depth = computeML();
    for (var i = 0; i < N; i++) {
      var ty = yOf(ELEV[i] - P.elevMin), dm = depth[i];
      if (dm >= .02) {
        wpos.setZ(i, ty + yOf(dm) + .04);
        var t = Math.min(dm / 4 * 1.5, 1);
        wcol.setXYZ(i, .62 - .55 * t, .83 - .58 * t, 1 - .5 * t);
      } else {
        wpos.setZ(i, ty - 2.5);
        wcol.setXYZ(i, .3, .55, .9);
      }
    }
    wpos.needsUpdate = true; wcol.needsUpdate = true;
    waterGeo.computeVertexNormals();
  }

  document.getElementById("mlToggle").addEventListener("click", function () {
    mlActive = !mlActive;
    this.textContent = mlActive ? "ON" : "OFF";
    this.className = mlActive ? "on" : "";
    document.getElementById("mlbody").style.display = mlActive ? "" : "none";
    if (mlActive) { playing = false; stopPlay(); updateWaterML(); }
    else waterDirty = true;                       // snap scenario water back
  });
  mlRain.addEventListener("input", function () { if (mlActive) updateWaterML(); });
  mlRiver.addEventListener("input", function () { if (mlActive) updateWaterML(); });
}

// ---- static header
if (P.live) document.body.classList.add("live");
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
function sph(az, radius, height) {
  return new THREE.Vector3(Math.sin(az) * radius, height,
    Math.cos(az) * radius);
}
function tickPresentation(now) {
  var T = (now - pres.t0) / 1000;
  var nF = SC.timesS.length - 1;
  var center = new THREE.Vector3(0, yOf(relief) * .3, 0);
  if (T < 4) {
    var q = easeInOut(T / 4);
    camera.position.lerpVectors(pres.cam0,
      sph(0, SIZE * 1.15, SIZE * .6), q);
    controls.target.lerpVectors(pres.tgt0, center, q);
  } else if (T < 32) {
    var q2 = (T - 4) / 28;
    setFrame(q2 * nF);   // continuous playhead — no frame stepping
    camera.position.copy(sph(q2 * Math.PI * 1.5, SIZE * (1.15 - .45 * q2),
      SIZE * (.6 - .22 * q2)));
    controls.target.copy(center);
  } else if (T < 38) {
    var q3 = easeInOut((T - 32) / 6);
    setFrame(nF);
    var end = pres.focus.clone().add(
      new THREE.Vector3(SIZE * .22, SIZE * .18, SIZE * .22));
    camera.position.lerpVectors(sph(Math.PI * 1.5, SIZE * .7, SIZE * .38),
      end, q3);
    controls.target.lerpVectors(center, pres.focus, q3);
  } else if (T < 44) {
    var az2 = (T - 38) * .1 + Math.PI * .25;
    var d = SIZE * .32;
    camera.position.set(pres.focus.x + Math.sin(az2) * d,
      pres.focus.y + SIZE * .16, pres.focus.z + Math.cos(az2) * d);
    controls.target.copy(pres.focus);
  } else endPresentation();
}

// ---- scale bar
var scaleLab = document.getElementById("scalelab");
var scaleBar = document.getElementById("scalebar");
var v1 = new THREE.Vector3(), v2 = new THREE.Vector3();
function updateScale() {
  v1.copy(controls.target).project(camera);
  v2.copy(controls.target).add(new THREE.Vector3(1, 0, 0)).project(camera);
  var pxPerUnit = Math.hypot((v2.x - v1.x) * innerWidth / 2,
                             (v2.y - v1.y) * innerHeight / 2);
  if (pxPerUnit <= 0) return;
  var kms = [0.25, 0.5, 1, 2, 5, 10];
  for (var i = 0; i < kms.length; i++) {
    var px = kms[i] * 1000 * mtu * pxPerUnit;
    if (px >= 60 && px <= 180) {
      scaleBar.style.width = px + "px";
      scaleLab.textContent = kms[i] < 1 ? kms[i] * 1000 + " m"
        : kms[i] + " km";
      return;
    }
  }
}

// ---- boot + loop
setScenario(P.defaultIndex);
bootSay("decision layer: " + SC.source);
bootSay("scene ready");

var needle = document.getElementById("needle");
addEventListener("resize", function () {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// double-click terrain: glide the camera's focus there (interruptible)
var focusS = { x: new Spring(0), y: new Spring(0), z: new Spring(0),
  on: false };
renderer.domElement.addEventListener("dblclick", function (e) {
  mouse.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  var hit = ray.intersectObject(terrain)[0];
  if (!hit || pres) return;
  if (reduceMotion) { controls.target.copy(hit.point); return; }
  focusS.x.x = controls.target.x; focusS.x.to(hit.point.x);
  focusS.y.x = controls.target.y; focusS.y.to(hit.point.y);
  focusS.z.x = controls.target.z; focusS.z.to(hit.point.z);
  focusS.on = true;
});
controls.addEventListener("start", function () { focusS.on = false; });

var clock = new THREE.Clock();
var shimmerTick = 0, frameTick = 0;
(function loop() {
  requestAnimationFrame(loop);
  frameTick++;
  var dt = Math.min(clock.getDelta(), .1);
  var now = performance.now();

  if (pres) tickPresentation(now);
  else {
    if (focusS.on) {
      controls.target.set(focusS.x.step(dt, .55), focusS.y.step(dt, .55),
        focusS.z.step(dt, .55));
      if (focusS.x.done && focusS.y.done && focusS.z.done) focusS.on = false;
    }
    controls.update();
  }

  if (mlActive) {
    // static prediction for the current slider values — no timeline,
    // no playback; the slider handlers already redraw on input
  } else if (SC) {
    var n1 = SC.timesS.length - 1;
    if (playing) {
      frameF += PLAY_RATE * +speedSel.value * dt;
      if (frameF >= n1) { frameF = n1; stopPlay(); }  // settle at the end
    } else if (!seekSpring.done) {
      frameF = Math.max(0, Math.min(n1, seekSpring.step(dt, .5)));
    }
    morphS.step(dt, .45);
    syncUI();
    updateWater(now);
  }

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

  var az = Math.atan2(camera.position.x - controls.target.x,
                      camera.position.z - controls.target.z);
  needle.style.transform = "rotate(" + (az * 180 / Math.PI) + "deg)";
  if (frameTick % 6 === 0) updateScale();
  renderer.render(scene, camera);
})();

bootFlush(function () {
  setTimeout(function () {
    document.getElementById("boot").className = "hide";
  }, reduceMotion ? 0 : 350);
});
</script>
</body>
</html>
"""
