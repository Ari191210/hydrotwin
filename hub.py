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
    fonts_css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "assets", "web_cache", "fonts_inline.css")
    with open(fonts_css_path, encoding="utf-8") as f:
        fonts_css = f.read()
    rows = "\n".join(_case_row(r) for r in results)
    html = _TEMPLATE.replace("__FONTS_CSS__", fonts_css) \
                    .replace("__ROWS__", rows)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[hub] Landing page saved to {path}")
    return path


def _sat_thumbnail(imagery, grid, px=520):
    """Satellite image with the water grid (row 0 = south) drawn over it."""
    from PIL import Image

    base = imagery.convert("RGB").resize((px, px), Image.LANCZOS)
    g = np.flipud(np.asarray(grid, dtype=float))
    a = np.clip(g / max(float(g.max()), 1.0), 0, 1)
    rgba = np.zeros(g.shape + (4,), np.uint8)
    rgba[..., 0] = (40 - 30 * a).astype(np.uint8)
    rgba[..., 1] = (150 - 100 * a).astype(np.uint8)
    rgba[..., 2] = (255 - 70 * a).astype(np.uint8)
    rgba[..., 3] = np.where(g >= 0.05, 215, 0).astype(np.uint8)
    over = Image.fromarray(rgba, "RGBA").resize((px, px), Image.BILINEAR)
    out = Image.alpha_composite(base.convert("RGBA"), over).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=84)
    return ("data:image/jpeg;base64,"
            + base64.b64encode(buf.getvalue()).decode())


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
    replay = r.get("replay_grid") is not None
    grid = r["replay_grid"] if replay else r["peak_grid"]
    if r.get("imagery") is not None:
        thumb = _sat_thumbnail(r["imagery"], grid)
    else:
        thumb = _thumbnail(r["elevation"], grid, r["cell_size"])
    pills = ('<span class="pill calm">No flood expected today</span>'
             if r.get("calm") else
             '<span class="pill hot">Flood alert in today\'s forecast</span>')
    if replay:
        pills += '<span class="pill">July 2023 flood replay inside</span>'
    cap = ("Map: the July 2023 replay at its widest" if replay
           else "Map: today's forecast at its peak")
    return f"""
<a class="case" href="{r['case']}/flood_3d.html">
  <figure><img src="{thumb}" alt="Water extent over {r['title']}">
    <figcaption>{cap}</figcaption></figure>
  <div class="body">
    <div class="pills">{pills}</div>
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
__FONTS_CSS__
  :root {
    --bg0: #04070c; --bg1: #0b111b;
    --line: rgba(148, 178, 215, .10); --line2: rgba(148, 178, 215, .22);
    --text: #e6edf6; --dim: #8494a9; --dimmer: #71829a;
    --accent: #45cfe9; --red: #ff5c57;
    --fd: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
    --fm: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { min-height: 100vh; color: var(--text);
    font: 15px/1.55 var(--fd);
    background: radial-gradient(120% 90% at 70% 0%, var(--bg1), var(--bg0));
    padding: 56px 24px 72px; }
  main { max-width: 980px; margin: 0 auto; }
  h1 { font-size: 34px; font-weight: 700; letter-spacing: 4px; }
  h1 em { font-style: normal; color: var(--accent); }
  .tag { color: var(--dim); margin: 6px 0 0; max-width: 62ch;
    text-wrap: pretty; }
  .tag b { color: var(--text); }
  .how { display: flex; gap: 10px; margin: 26px 0 40px; flex-wrap: wrap;
    color: var(--dimmer); font-family: var(--fm); font-size: 11px;
    align-items: center; }
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
  .case figure { position: relative; width: 300px; flex-shrink: 0;
    margin: 0; }
  .case img { width: 300px; height: 100%; min-height: 240px;
    object-fit: cover; display: block; }
  figcaption { position: absolute; left: 0; right: 0; bottom: 0;
    padding: 18px 12px 8px; font-family: var(--fm); font-size: 9.5px;
    letter-spacing: .6px; color: #dbe6f2;
    background: linear-gradient(180deg, transparent, rgba(4,7,12,.85)); }
  .case.door .body { padding: 20px 24px 18px; }
  .pills { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 9px; }
  .pill { font-family: var(--fm); font-size: 9.5px; letter-spacing: .8px;
    text-transform: uppercase; padding: 3px 9px; border-radius: 20px;
    color: var(--accent); border: 1px solid rgba(69,207,233,.4);
    background: rgba(69,207,233,.08); }
  .pill.calm { color: #4cd97b; border-color: rgba(76,217,123,.4);
    background: rgba(76,217,123,.09); }
  .pill.hot { color: var(--red); border-color: rgba(255,92,87,.45);
    background: rgba(255,92,87,.1); }
  .body { padding: 20px 24px 18px 0; min-width: 0; }
  .case h2 { font-size: 19px; font-weight: 700; letter-spacing: -.2px; }
  .alert { color: var(--dim); font-size: 13px; margin: 6px 0 12px;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; text-wrap: pretty; }
  dl { display: flex; gap: 26px; flex-wrap: wrap; }
  dt { font-family: var(--fm); font-size: 9px; letter-spacing: 1.6px;
    text-transform: uppercase; color: var(--dimmer); }
  dd { font-family: var(--fm); font-size: 16px; font-weight: 600;
    font-variant-numeric: tabular-nums; }
  .open { display: inline-block; margin-top: 14px; color: var(--accent);
    font-size: 13px; font-weight: 700; }

  footer { color: var(--dimmer); font-size: 12px; margin-top: 44px;
    max-width: 72ch; text-wrap: pretty; }
  footer b { color: var(--dim); }
  @media (max-width: 640px) {
    .case { flex-direction: column; }
    .case figure { width: 100%; }
    .case img { width: 100%; height: 200px; min-height: 0; }
    .body { padding: 0 20px 18px; }
  }
</style>
</head>
<body>
<main>
  <h1>HYDRO<em>TWIN</em></h1>
  <p class="tag"><b>Physics-informed flood intelligence.</b> Give it a
    river's flow and the rain, and it shows where the water goes: a 2D
    shallow-water simulation over real terrain and satellite imagery, with
    advisory evacuation zones. Checked against the July 2023 Yamuna flood,
    with the misses shown.</p>
  <div class="how">
    <span>real terrain + satellite imagery</span><i>&rarr;</i>
    <span>live rain + river flow</span><i>&rarr;</i>
    <span>shallow-water physics</span><i>&rarr;</i>
    <span>advisory zones</span><i>&rarr;</i>
    <span>3D viewer, works offline</span>
  </div>
__ROWS__
  <a class="case door" href="doorstep.html">
    <div class="body">
      <div class="pills"><span class="pill">New</span></div>
      <h2>Doorstep forecast: from a river level to your neighbourhood</h2>
      <p class="alert">Official warnings give one number, the Yamuna's
        level at the Old Railway Bridge. Set that level and see which
        Delhi neighbourhoods get water, how deep, with a message in Hindi
        you can send. Tested against places recorded as flooded in 2023.</p>
      <span class="open">Open the doorstep forecast &rarr;</span>
    </div>
  </a>
  <footer>Depths, areas and volumes are computed by the simulation.
    <b>People-affected figures are estimates</b> from stated per-basin
    population densities. The default view is always today's forecast as
    issued; what-if storms and the July 2023 replay are labelled as such
    inside each viewer, and every number lists its source.</footer>
</main>
</body>
</html>
"""
