# HydroTwin — physics-informed flood prediction demo

Simulates a flood over real terrain with 2D shallow-water physics
(Landlab `OverlandFlow`), drives it with a live rainfall forecast, turns the
result into evacuation decisions with Claude, and renders an interactive map
plus an animation.

## Run

```bash
.venv/Scripts/python run.py        # Windows
# or: python run.py  (with the deps below installed)
```

Optional env vars:

```bash
ANTHROPIC_API_KEY=sk-ant-...   # enables the Claude decision layer
                               # (without it: rule-based fallback, still works)
OPENTOPO_API_KEY=...           # optional extra DEM source (OpenTopography)
```

## Outputs (written to `outputs/`)

| File | What |
|---|---|
| `flood_map.html` | Interactive Leaflet map with a time slider of flood spread, evacuation zones, POIs, and the public alert. Opens offline. |
| `flood.gif` / `flood.mp4` | Animation of flood depth over a terrain hillshade (the GIF is the guaranteed fallback). |
| `decisions.json` | Evacuation zones, safe routes, public alert + zone stats. |
| `depths.npz` | Raw water-depth grids per timestep. |

## Pipeline & fallbacks

Every external dependency degrades gracefully — the demo completes end-to-end
with **no internet and no API keys**:

1. **Terrain** — AWS Terrain Tiles (SRTM, no key) or OpenTopography (with key);
   on any failure: synthetic river valley.
2. **Rainfall** — Open-Meteo hourly forecast (no key), wettest window in the
   next 48 h; on failure *or* a too-dry forecast (< `MIN_DEMO_RAIN_MM`):
   built-in design storm (printed clearly either way).
3. **Physics** — Landlab `OverlandFlow` (de Almeida et al. explicit
   shallow-water scheme), adaptive timestep. No ML, no training.
4. **Decisions** — `claude-sonnet-5` returns strict JSON (evacuation zones,
   safe routes, public alert); on missing key / API error / bad JSON:
   rule-based planner.
5. **Viz** — Folium map with all Leaflet assets inlined (cached in
   `assets/web_cache/`) so the HTML opens offline; matplotlib GIF always
   works, MP4 via bundled ffmpeg.

## Configuration

Everything is in `config.py`: basin lat/lon, grid size, storm duration,
depth thresholds, POIs, and `RAIN_MULTIPLIER` if you want a bigger show.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install landlab numpy scipy matplotlib requests folium anthropic imageio imageio-ffmpeg pillow
```

## Module map

`config.py` (all knobs) → `terrain.py` → `rainfall.py` → `simulate.py` →
`decide.py` → `visualize.py`, orchestrated by `run.py`.
