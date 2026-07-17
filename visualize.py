"""Visualization for HydroTwin.

Produces:
  outputs/flood_map.html — Folium/Leaflet map with a time slider of flood
      spread, zone overlays, POIs and the public alert. Leaflet assets are
      inlined (cached in assets/web_cache) so the file opens offline.
  outputs/flood.gif — matplotlib animation over a hillshade (guaranteed).
  outputs/flood.mp4 — same animation via bundled ffmpeg (best effort).
"""

import base64
import io
import math
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation, cm
from matplotlib.colors import LightSource

import config
from decide import zone_name

WEB_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "web_cache")

PRIORITY_COLORS = {"immediate": "#d32f2f", "high": "#f57c00",
                   "monitor": "#fbc02d"}
POI_COLORS = {"hospital": "#c62828", "school": "#6a1b9a", "road": "#37474f"}


# ------------------------------------------------------------ shared bits ---

def _depth_vmax(depths):
    peak = max(float(d.max()) for d in depths)
    return max(peak * 0.8, 0.5)


def _hillshade_rgb(elevation):
    ls = LightSource(azdeg=315, altdeg=45)
    return ls.shade(elevation, cmap=cm.gray, blend_mode="overlay",
                    vert_exag=2.0)


def _basin_bounds(shape, cell_size):
    rows, cols = shape
    dlat = rows * cell_size / 2.0 / 111_320.0
    dlon = cols * cell_size / 2.0 / (
        111_320.0 * math.cos(math.radians(config.BASIN_LAT)))
    south, north = config.BASIN_LAT - dlat, config.BASIN_LAT + dlat
    west, east = config.BASIN_LON - dlon, config.BASIN_LON + dlon
    return south, west, north, east


def _rc_to_latlon(row, col, shape, cell_size):
    south, west, north, east = _basin_bounds(shape, cell_size)
    lat = south + (row + 0.5) / shape[0] * (north - south)
    lon = west + (col + 0.5) / shape[1] * (east - west)
    return lat, lon


# ---------------------------------------------------------------- folium ----

def make_folium_map(times, depths, elevation, cell_size, decisions,
                    path=None):
    import folium

    path = path or os.path.join(config.OUTPUT_DIR, "flood_map.html")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    shape = elevation.shape
    south, west, north, east = _basin_bounds(shape, cell_size)
    bounds = [[south, west], [north, east]]
    vmax = _depth_vmax(depths)

    m = folium.Map(location=[config.BASIN_LAT, config.BASIN_LON],
                   zoom_start=13, tiles="OpenStreetMap")

    # Hillshade base — visible even with no internet (no map tiles).
    folium.raster_layers.ImageOverlay(
        image=_to_data_uri(np.flipud(_hillshade_rgb(elevation))),
        bounds=bounds, opacity=0.9, name="terrain").add_to(m)

    # One overlay per snapshot; the slider toggles their opacity.
    frame_names = []
    blues = matplotlib.colormaps["Blues"]
    for d in depths:
        rgba = blues(np.clip(d / vmax, 0, 1))
        rgba[..., 3] = np.clip(d / 0.5, 0.0, 0.85) * (d > 0.02)
        ov = folium.raster_layers.ImageOverlay(
            image=_to_data_uri(np.flipud(rgba)), bounds=bounds, opacity=0.0)
        ov.add_to(m)
        frame_names.append(ov.get_name())

    _add_zones(m, decisions, shape, cell_size)
    _add_pois(m, decisions["pois"], shape, cell_size)
    _add_ui(m, times, frame_names, decisions)

    m.save(path)
    _inline_web_assets(path)
    print(f"[visualize] Interactive map saved to {path}")
    return path


def _to_data_uri(rgba):
    from PIL import Image

    arr = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    if arr.shape[-1] == 3:
        arr = np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)])
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, format="PNG")
    return ("data:image/png;base64,"
            + base64.b64encode(buf.getvalue()).decode())


def _add_zones(m, decisions, shape, cell_size):
    import folium

    rband = shape[0] // config.ZONE_DIV
    cband = shape[1] // config.ZONE_DIV
    evac = {e["zone"]: e for e in decisions.get("evacuation_zones", [])}
    for zr in range(config.ZONE_DIV):
        for zc in range(config.ZONE_DIV):
            name = zone_name(zr, zc)
            s, w = _rc_to_latlon(zr * rband - 0.5, zc * cband - 0.5,
                                 shape, cell_size)
            n, e = _rc_to_latlon((zr + 1) * rband - 0.5,
                                 (zc + 1) * cband - 0.5, shape, cell_size)
            entry = evac.get(name)
            color = PRIORITY_COLORS.get(entry["priority"]) if entry else None
            tooltip = (f"Zone {name}: {entry['priority'].upper()} — "
                       f"{entry['reason']}" if entry else f"Zone {name}: no action")
            folium.Rectangle(
                bounds=[[s, w], [n, e]],
                color=color or "#9e9e9e", weight=2 if entry else 1,
                fill=bool(entry), fill_color=color or "#9e9e9e",
                fill_opacity=0.18 if entry else 0.0,
                tooltip=tooltip).add_to(m)


def _add_pois(m, pois, shape, cell_size):
    import folium

    for p in pois:
        lat, lon = _rc_to_latlon(p["row"], p["col"], shape, cell_size)
        folium.CircleMarker(
            location=[lat, lon], radius=7,
            color="#ffffff", weight=2, fill=True,
            fill_color=POI_COLORS.get(p["type"], "#1565c0"), fill_opacity=1.0,
            tooltip=(f"{p['name']} ({p['type']}, zone {p['zone']}) — "
                     f"water depth {p['depth_here_m']} m")).add_to(m)


def _add_ui(m, times, frame_names, decisions):
    import folium
    import json as _json

    labels = [f"t = {t / 3600.0:.2f} h" for t in times]
    alert = str(decisions.get("public_alert", "")).replace("<", "&lt;")
    html = f"""
<div style="position:fixed; top:10px; left:50px; right:50px; z-index:9999;
     background:#b71c1c; color:#fff; padding:10px 16px; border-radius:6px;
     font:14px/1.4 sans-serif; box-shadow:0 2px 8px rgba(0,0,0,.4);">
  <b>FLOOD ALERT</b> ({decisions.get('source', '')}): {alert}
</div>
<div style="position:fixed; bottom:20px; left:50px; right:50px; z-index:9999;
     background:rgba(255,255,255,.95); padding:10px 16px; border-radius:6px;
     font:13px sans-serif; box-shadow:0 2px 8px rgba(0,0,0,.4);">
  <button id="ht-play" style="width:60px;">Play</button>
  <input id="ht-slider" type="range" min="0" max="{len(frame_names) - 1}"
         value="0" style="width:60%; vertical-align:middle;">
  <span id="ht-label" style="margin-left:10px; font-weight:bold;"></span>
  <span style="float:right; color:#555;">HydroTwin — flood depth over time</span>
</div>
<script>
document.addEventListener("DOMContentLoaded", function() {{
  var frames = {_json.dumps(frame_names)};
  var labels = {_json.dumps(labels)};
  var slider = document.getElementById("ht-slider");
  var label = document.getElementById("ht-label");
  var play = document.getElementById("ht-play");
  var timer = null;
  function overlay(i) {{ return window[frames[i]]; }}
  function show(i) {{
    i = Math.max(0, Math.min(frames.length - 1, i));
    for (var k = 0; k < frames.length; k++)
      if (overlay(k)) overlay(k).setOpacity(k == i ? 0.85 : 0.0);
    slider.value = i; label.textContent = labels[i];
  }}
  slider.addEventListener("input", function() {{ show(+slider.value); }});
  play.addEventListener("click", function() {{
    if (timer) {{ clearInterval(timer); timer = null; play.textContent = "Play"; return; }}
    play.textContent = "Pause";
    timer = setInterval(function() {{
      var next = (+slider.value + 1) % frames.length;
      show(next);
    }}, 400);
  }});
  setTimeout(function() {{ show(frames.length - 1); }}, 400);
}});
</script>"""
    m.get_root().html.add_child(folium.Element(html))


def _inline_web_assets(path):
    """Replace CDN <script src>/<link href> with inline content so the map
    opens with no internet. Assets are cached in assets/web_cache; if an
    asset was never cached and we're offline, the tag is left as-is."""
    os.makedirs(WEB_CACHE, exist_ok=True)
    with open(path, encoding="utf-8") as f:
        html = f.read()

    def fetch(url):
        fname = os.path.join(WEB_CACHE,
                             re.sub(r"[^A-Za-z0-9._-]", "_", url)[-120:])
        if os.path.exists(fname):
            with open(fname, encoding="utf-8") as f:
                return f.read()
        try:
            import requests
            r = requests.get(url, timeout=(5, 20))
            r.raise_for_status()
            with open(fname, "w", encoding="utf-8") as f:
                f.write(r.text)
            return r.text
        except Exception as exc:
            print(f"[visualize] could not inline {url} "
                  f"({type(exc).__name__}) — leaving CDN link")
            return None

    def repl_script(match):
        content = fetch(match.group(1))
        return match.group(0) if content is None else \
            "<script>\n" + content + "\n</script>"

    def repl_link(match):
        content = fetch(match.group(1))
        if content is None:
            return match.group(0)
        # drop remote url() refs (icons) that would 404 offline anyway
        content = re.sub(r"url\((?!data:)[^)]*\)", "none", content)
        return "<style>\n" + content + "\n</style>"

    html = re.sub(r'<script src="(https?://[^"]+)"></script>', repl_script, html)
    html = re.sub(r'<link rel="stylesheet" href="(https?://[^"]+)"\s*/?>',
                  repl_link, html)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ------------------------------------------------------------ matplotlib ----

def make_animation(times, depths, elevation, cell_size, decisions,
                   gif_path=None, mp4_path=None):
    """Guaranteed-fallback animation. Returns (gif_path, mp4_path_or_None)."""
    gif_path = gif_path or os.path.join(config.OUTPUT_DIR, "flood.gif")
    mp4_path = mp4_path or os.path.join(config.OUTPUT_DIR, "flood.mp4")
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    vmax = _depth_vmax(depths)
    hillshade = _hillshade_rgb(elevation)

    fig, ax = plt.subplots(figsize=(8, 8.6), dpi=90)
    extent = [0, elevation.shape[1] * cell_size / 1000.0,
              0, elevation.shape[0] * cell_size / 1000.0]
    ax.imshow(hillshade, origin="lower", extent=extent)
    masked = np.ma.masked_less(depths[0], 0.02)
    im = ax.imshow(masked, origin="lower", extent=extent, cmap="Blues",
                   vmin=0, vmax=vmax, alpha=0.8)
    fig.colorbar(im, ax=ax, shrink=0.7, label="water depth (m)")

    for p in decisions["pois"]:
        x = (p["col"] + 0.5) * cell_size / 1000.0
        y = (p["row"] + 0.5) * cell_size / 1000.0
        ax.plot(x, y, "o", ms=9, mec="white", mew=1.5,
                color=POI_COLORS.get(p["type"], "#1565c0"))
        ax.annotate(p["name"], (x, y), xytext=(6, 6),
                    textcoords="offset points", fontsize=7, color="white",
                    path_effects=None,
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.55))

    title = ax.set_title("")
    alert = str(decisions.get("public_alert", ""))
    fig.text(0.5, 0.015, "ALERT: " + alert, ha="center", fontsize=8,
             wrap=True, color="#b71c1c")
    ax.set_xlabel("km east")
    ax.set_ylabel("km north")

    def update(i):
        im.set_array(np.ma.masked_less(depths[i], 0.02))
        title.set_text(f"HydroTwin flood simulation — t = "
                       f"{times[i] / 3600.0:.2f} h")
        return im, title

    anim = animation.FuncAnimation(fig, update, frames=len(depths),
                                   interval=350)

    anim.save(gif_path, writer=animation.PillowWriter(fps=3))
    print(f"[visualize] GIF saved to {gif_path}")

    mp4_saved = None
    try:
        import imageio_ffmpeg
        matplotlib.rcParams["animation.ffmpeg_path"] = \
            imageio_ffmpeg.get_ffmpeg_exe()
        anim.save(mp4_path, writer=animation.FFMpegWriter(fps=3, bitrate=1800))
        mp4_saved = mp4_path
        print(f"[visualize] MP4 saved to {mp4_path}")
    except Exception as exc:
        print(f"[visualize] MP4 export failed ({type(exc).__name__}: {exc}) "
              f"— GIF is the fallback")
    plt.close(fig)
    return gif_path, mp4_saved
