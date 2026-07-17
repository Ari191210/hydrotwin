# HydroTwin — physics-informed flood prediction

Simulates a flood over real terrain with 2D shallow-water physics
(Landlab `OverlandFlow`), driven by live rainfall and live river-discharge
data, turns the result into evacuation decisions with Claude, and renders it
in an interactive 3D viewer — for **any location on Earth**.

## Run — live server (any location)

```bash
.venv/Scripts/python server.py     # then open http://localhost:8000
```

Type any city or `lat,lon`. The server geocodes it, fetches global terrain +
live rainfall + live GloFAS river discharge, runs the physics, and returns
the 3D flood forecast for that exact place — with a live-conditions strip
(UTC clock, current rainfall, river discharge, forecast age) updating to the
second. First run of a location takes ~20-25 s (staged progress shown);
results are cached by coordinate.

Needs internet (for the live data + global terrain). The only optional key is
`ANTHROPIC_API_KEY`; geocoding, terrain, rainfall, and discharge are keyless.

## Run — static build (offline, the 3 curated cases)

```bash
.venv/Scripts/python run.py            # runs all 3 demo cases (~30 s each)
.venv/Scripts/python run.py delhi      # one case: rishikesh | delhi | hue
```

Produces self-contained `outputs/<case>/flood_3d.html` files that open with
no internet and no server — the guaranteed-to-work fallback for the demo.

The three cases (defined in `config.py` CASES):

| Case | Basin | Character |
|---|---|---|
| `rishikesh` | Ganga exiting the Himalaya (30.11, 78.29) | steep mountain valley |
| `delhi` | Yamuna floodplain (28.66, 77.23) | flat urban floodplain |
| `hue` | Perfume River, Vietnam (16.46, 107.59) | coastal monsoon basin |

Optional env vars:

```bash
ANTHROPIC_API_KEY=sk-ant-...   # enables the Claude decision layer
                               # (without it: rule-based fallback, still works)
OPENTOPO_API_KEY=...           # optional extra DEM source (OpenTopography)
```

## Outputs (written to `outputs/<case>/`)

| File | What |
|---|---|
| `flood_3d.html` | **The demo centerpiece** — rotatable/zoomable 3D terrain (three.js) with the flood animating over it, evacuation-zone texture toggle, POI pins with hover tooltips, rainfall chart, alert + decisions panel. Fully self-contained, opens offline. |
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
3. **Live flood data** — Open-Meteo Flood API (Copernicus **GloFAS** river
   discharge forecast, no key). Samples a 3×3 cell neighbourhood and keeps
   the strongest cell (the river channel). Last good response is cached per
   case in `assets/glofas_cache.json`, so the discharge panel shows
   last-known live data (timestamped) with no internet. Omitted only if no
   river cell is near the basin and nothing is cached.
4. **Physics** — Landlab `OverlandFlow` (de Almeida et al. explicit
   shallow-water scheme), adaptive timestep. No ML, no training.
5. **Decisions** — `claude-sonnet-5` returns strict JSON (evacuation zones,
   safe routes, public alert); on missing key / API error / bad JSON:
   rule-based planner.
6. **Viz** — Folium map with all Leaflet assets inlined (cached in
   `assets/web_cache/`) so the HTML opens offline; matplotlib GIF always
   works, MP4 via bundled ffmpeg.

**API keys:** the only key the project ever uses is `ANTHROPIC_API_KEY`
(optional — enables the Claude decision layer). Terrain, rainfall, and live
river discharge are all keyless.

## Configuration

Everything is in `config.py`: basin lat/lon, grid size, storm duration,
depth thresholds, POIs, and `RAIN_MULTIPLIER` if you want a bigger show.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install landlab numpy scipy matplotlib requests folium anthropic imageio imageio-ffmpeg pillow
```

## Module map

`config.py` (all knobs + case presets) → `terrain.py` → `rainfall.py` →
`simulate.py` → `decide.py` → `viewer3d.py` + `visualize.py`,
orchestrated by `run.py`.
