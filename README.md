# HydroTwin — physics-informed flood prediction

Team project. Physics-informed flood digital twin: live terrain, rainfall and
river-discharge data drive a 2D shallow-water sim (Landlab `OverlandFlow`),
which turns into evacuation decisions with Claude, and renders it
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
   next 48 h. The default scenario is always that forecast as issued, even
   when it is dry ("no flood expected" is a valid answer). The built-in
   design storm is only ever a labelled what-if; it is the default only
   when the forecast cannot be fetched at all, and the viewer says so.
3. **River discharge** — Open-Meteo Flood API (Copernicus **GloFAS**
   forecast, no key). Samples a 3×3 cell neighbourhood and keeps the
   strongest cell. Compared against a 1997-2024 climatology built from the
   same API (`assets/glofas_clim.json`). Last good response is cached in
   `assets/glofas_cache.json`.
   For the Delhi preset the river is routed through the model, not just
   displayed (see "River model" below). Other locations are rain only and
   the viewer says so.
4. **Physics** — Landlab `OverlandFlow` (de Almeida et al. explicit
   shallow-water scheme), adaptive timestep. `check_inflow.py` checks the
   river source term against Manning's normal depth (0.709 m vs 0.710 m).
5. **Decisions** — `claude-sonnet-5` returns strict JSON (evacuation zones,
   safe routes, public alert); on missing key / API error / bad JSON:
   rule-based planner.
6. **Viz** — Folium map with all Leaflet assets inlined (cached in
   `assets/web_cache/`) so the HTML opens offline; matplotlib GIF always
   works, MP4 via bundled ffmpeg.

**API keys:** the only key the project ever uses is `ANTHROPIC_API_KEY`
(optional — enables the Claude decision layer). Terrain, rainfall, and live
river discharge are all keyless.

## River model (Delhi preset)

- **Continuous river bed** (`river.condition_channel`): the raw elevation
  data does not give the Yamuna a continuous downhill bed, so a small flow
  ponded in the channel. The bed is carved along a least-climb path from
  the inflow to the mapped outlet.
- **What is routed**: discharge above the dry-season baseline the elevation
  data was captured at (February median).
- **What counts as the river**: the mapped water (OpenStreetMap), plus the
  area wet at the median annual maximum flow ("bankfull footprint",
  `riverstate.py`). Flooding means water outside that.
- **Warm start**: forecast runs begin from the steady state at today's
  flow, not from a dry channel.

## Honesty rules

- Anything on screen that is not the real forecast over real terrain is
  labelled: what-if scenarios, the July 2023 replay, synthetic terrain.
- Evacuation zones and alerts are advisory. A person decides.
- `BACKTEST_PREREG.md` records the July 2023 Delhi backtest: rules fixed
  before the first run, results, a rain-only control, and a post-hoc rerun
  on the conditioned river bed. Short version: the inflow is calibrated to
  the recorded river level; one of three main sites is flooded by the
  river in the model, one is missed, and other wet sites are rain pooling
  in terrain dips (no drains are modelled).
  `BACKTEST_FABDEM.md` repeats it on bare-earth elevation data as a
  separate result.
- GloFAS alone would not have flagged July 2023 at Delhi (907 m3/s on the
  peak day, below its own median annual maximum). The model needs a real
  river flow, such as the upstream barrage release.

## ML instant preview (Delhi page)

A small model fitted to 234 runs of this physics (`surrogate.py`,
`surrogate_baselines.py`), scored on 50 held-out runs: 0.96 wet-area
overlap outside the river, against 0.61 for predicting the average map.
It is an approximation for instant what-if sliders. The physics result is
the reference.

## Configuration

Everything is in `config.py`: basin lat/lon, grid size, storm duration,
depth thresholds, POIs, the what-if multipliers, and the river settings.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install landlab numpy scipy matplotlib requests folium anthropic imageio imageio-ffmpeg pillow flask flask-cors
# field reports (Laya), CPU-only torch keeps the install small
.venv/Scripts/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -e ../laya
```

## Field reports (Laya), live server only

The physics can't read what people on the ground are saying, so the live console
has a **Field reports** drawer. Paste a message in any language and
[Laya](https://github.com/NandhaKishorM/laya) (`laya_layer.py`) triages it in one
forward pass: need (rescue / medical / supplies / infrastructure / observation /
irrelevant), urgency, trapped / rising / vulnerable flags, and the mapped place it
names. Its Router sends English to the English checkpoint and other scripts or
languages to the multilingual one.

- **Escalate only:** a report can raise a zone's priority and never lower what the
  physics says. Only an exact POI-name match (or the officer's zone pick) places a
  report; Laya's own place guess is shown as a suggestion.
- The model loads in the background at server start (~65 s on CPU) with
  `HF_HUB_OFFLINE=1`, so the checkpoints must already be in the Hugging Face cache.
  Until then the drawer says so and everything else works.
- Reports update the zone list in the viewer, but not the baked 3D zone tint or
  route arrows.
- `eval_laya.py` runs 12 hand-labelled reports (English, Hindi, Hinglish,
  Vietnamese). The severity thresholds were tuned on these same cases, so treat
  its score as a sanity check, not a held-out accuracy.

## Module map

`config.py` (all knobs + case presets) → `terrain.py` + `imagery.py` →
`rainfall.py` + `flooddata.py` → `river.py` + `riverstate.py` →
`scenarios.py` → `simulate.py` → `decide.py` → `viewer3d.py` +
`visualize.py`, orchestrated by `run.py` (static) and `engine.py` +
`server.py` (live). Backtest: `backtest_delhi.py`, `score_backtest.py`,
`backtest_conditioned.py`. Demo script: `DEMO_SCRIPT.md`.
