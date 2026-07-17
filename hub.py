"""Landing hub for HydroTwin: outputs/index.html.

One offline page that opens the demo — mission line, the three cases with
peak-flood thumbnails and headline numbers, links to each 3D viewer.
"""

import base64
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource


def make_hub(results, path="outputs/index.html"):
    rows = "\n".join(_case_row(r) for r in results)
    html = _TEMPLATE.replace("__ROWS__", rows)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[hub] Landing page saved to {path}")
    return path


def _thumbnail(elevation, peak_grid, cell_size, px=340):
    """Peak-flood mini-render as a data URI (hillshade + water overlay)."""
    ls = LightSource(azdeg=315, altdeg=45)
    fig, ax = plt.subplots(figsize=(3.4, 3.4), dpi=100)
    ax.imshow(ls.hillshade(elevation, vert_exag=2), origin="lower",
              cmap="gray")
    ax.imshow(np.ma.masked_less(peak_grid, 0.05), origin="lower",
              cmap="Blues", vmin=0, vmax=max(float(peak_grid.max()), 0.5),
              alpha=0.85)
    ax.set_axis_off()
    fig.subplots_adjust(0, 0, 1, 1)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return ("data:image/png;base64,"
            + base64.b64encode(buf.getvalue()).decode())


def _case_row(r):
    thumb = _thumbnail(r["elevation"], r["peak_grid"], r["cell_size"])
    return f"""
<a class="case" href="{r['case']}/flood_3d.html">
  <img src="{thumb}" alt="Peak flood extent over {r['title']} terrain">
  <div class="body">
    <h2>{r['title']}</h2>
    <p class="alert">{r['alert']}</p>
    <dl>
      <div><dt>peak depth</dt><dd>{r['peak_depth_m']:.1f} m</dd></div>
      <div><dt>flooded</dt><dd>{r['flooded_km2']:.2f} km&sup2;</dd></div>
      <div><dt>people (est.)</dt><dd>~{r['people_est']:,}</dd></div>
      <div><dt>zones flagged</dt><dd>{r['n_zones']}</dd></div>
    </dl>
    <span class="open">Open 3D simulation &rarr;</span>
  </div>
</a>"""


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HydroTwin — physics-informed flood intelligence</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128167;</text></svg>">
<style>
  :root {
    --bg0: #060a10; --bg1: #0d1420; --line: #1d2836; --line2: #2a3a4e;
    --text: #e4ecf5; --dim: #7e8ea1; --dimmer: #71829a;
    --accent: #38d6f5; --red: #ff5c57;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { min-height: 100vh; color: var(--text);
    font: 15px/1.55 "Segoe UI", system-ui, -apple-system, sans-serif;
    background: radial-gradient(120% 90% at 70% 0%, var(--bg1), var(--bg0));
    padding: 56px 24px 72px; }
  main { max-width: 880px; margin: 0 auto; }
  h1 { font-size: 34px; font-weight: 800; letter-spacing: 4px; }
  h1 em { font-style: normal; color: var(--accent); }
  .tag { color: var(--dim); margin: 6px 0 0; max-width: 62ch;
    text-wrap: pretty; }
  .tag b { color: var(--text); }
  .how { display: flex; gap: 10px; margin: 26px 0 40px; flex-wrap: wrap;
    color: var(--dimmer); font-size: 12.5px; align-items: center; }
  .how span { border: 1px solid var(--line); border-radius: 20px;
    padding: 4px 13px; color: var(--dim); white-space: nowrap; }
  .how i { font-style: normal; }

  .case { display: flex; gap: 22px; text-decoration: none; color: inherit;
    border: 1px solid var(--line); border-radius: 16px; overflow: hidden;
    margin-bottom: 18px; background: rgba(255,255,255,.02);
    transition: border-color .15s, transform .15s; }
  .case:hover { border-color: var(--accent); transform: translateY(-2px); }
  .case:focus-visible { outline: 2px solid var(--accent);
    outline-offset: 2px; }
  .case img { width: 218px; height: 218px; object-fit: cover; flex-shrink: 0;
    display: block; }
  .body { padding: 20px 24px 18px 0; min-width: 0; }
  .case h2 { font-size: 19px; font-weight: 700; letter-spacing: -.2px; }
  .alert { color: var(--dim); font-size: 13px; margin: 6px 0 12px;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; text-wrap: pretty; }
  dl { display: flex; gap: 26px; flex-wrap: wrap; }
  dt { font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase;
    color: var(--dimmer); }
  dd { font-size: 17px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .open { display: inline-block; margin-top: 14px; color: var(--accent);
    font-size: 13px; font-weight: 700; }

  footer { color: var(--dimmer); font-size: 12px; margin-top: 44px;
    max-width: 72ch; text-wrap: pretty; }
  footer b { color: var(--dim); }
  @media (max-width: 640px) {
    .case { flex-direction: column; }
    .case img { width: 100%; height: 170px; }
    .body { padding: 0 20px 18px; }
  }
</style>
</head>
<body>
<main>
  <h1>HYDRO<em>TWIN</em></h1>
  <p class="tag"><b>Physics-informed flood intelligence.</b> A 2D
    shallow-water simulation over real satellite terrain, driven by live
    rainfall, turned into evacuation decisions — end to end, offline-capable,
    in about thirty seconds per basin.</p>
  <div class="how">
    <span>real SRTM terrain</span><i>&rarr;</i>
    <span>Landlab shallow-water physics</span><i>&rarr;</i>
    <span>storm scenarios &times;1 &times;2 &times;3</span><i>&rarr;</i>
    <span>evacuation decisions</span><i>&rarr;</i>
    <span>3D simulation viewer</span>
  </div>
__ROWS__
  <footer>Depths, areas and volumes are computed by the simulation.
    <b>People-affected figures are estimates</b> from stated per-basin
    population densities, and the storm scenarios scale the observed or
    design rainfall — every assumption is shown inside each viewer's data
    sources panel.</footer>
</main>
</body>
</html>
"""
