# Design

Visual system of the HydroTwin 3D viewer (`viewer3d.py` → `flood_3d.html`).
The page is generated from a Python template; tokens live in the `:root`
block of `_TEMPLATE`. Edit tokens there, re-run `run.py` to regenerate.

## Theme

Dark mission-control. Single dark theme (no light mode): the viewer is a
projected demo/ops surface and the 3D scene needs a dark surround to read.
Background is a radial gradient `#0d1420 → #060a10`; panels are translucent
dark layers over the WebGL canvas.

## Colors

| Token | Value | Role |
|---|---|---|
| `--bg0` / `--bg1` | `#060a10` / `#0d1420` | page gradient ends |
| `--panel` | `rgba(13,19,28,.88)` | floating panel surface |
| `--line` / `--line2` | `#1d2836` / `#2a3a4e` | borders, dividers |
| `--text` | `#e4ecf5` | primary text |
| `--dim` | `#7e8ea1` | secondary text |
| `--dimmer` | `#55657a` | section labels, hints |
| `--accent` | `#38d6f5` | cyan — time, water, interactive accents |
| `--accent2` | `#7c9cf5` | blue — gradient partner of accent |
| `--red` | `#ff5c57` | alert + immediate priority ONLY |
| `--orange` | `#ffab40` | high priority |
| `--yellow` | `#ffd54f` | monitor priority |
| `--safe` | `#4cd97b` | SAFE status chips |

Priority vocabulary (immediate/high/monitor → red/orange/yellow) is used
identically in the side panel, the zone texture overlay, and decisions.json.
Red is reserved for urgency (see PRODUCT.md principle 3).

## Typography

- Single family: `"Segoe UI", system-ui, -apple-system, sans-serif` (offline
  constraint: no webfonts, every byte ships in the file).
- Base 13.5px/1.5. Stat values 20px/700 with `tabular-nums`; time readout
  15px/700 tabular. Section headers 10px uppercase, letter-spacing 2px.
- Brand mark: 21px/800, letter-spacing 3px, "TWIN" in accent gradient.

## Components

- **Floating panel**: `--panel` bg, 1px `--line` border, radius 14px,
  `backdrop-filter: blur(10px)`, soft 32px shadow. Used for header, sidebar,
  timeline bar, view options, compass.
- **Stat tile**: 2×2 grid; large tabular number + unit + uppercase label.
- **Zone row**: 3px left priority border + zone id + priority chip + reason.
- **POI row**: glowing type dot + name/sublabel + SAFE/depth status chip.
- **Chips**: 20px-radius pills, 9–10.5px/800 uppercase, tinted bg at ~15%.
- **Timeline**: hourly rain bars (lit cyan up to current time) above a range
  slider; circular gradient play button; speed select.
- **3D scene**: gist_earth-shaded terrain (blue band suppressed), Phong water
  with depth-ramped vertex colors, POI pin = stem + emissive sphere.

## Layout

- Left column 344px: header panel (brand, case tabs, case line) above a
  scrollable sidebar (alert → live stats → priorities → POIs → sources).
- Bottom center: timeline bar, `min(720px, 100% − 400px)`.
- Top right: view options (208px). Bottom right: compass.
- ≤980px: side/header hide, timeline goes full-width (3D stays primary).

## Motion

- Auto-rotate 0.55°/frame until first drag; damped orbit controls.
- Alert dot 1.4s pulse; rain bars 0.2s background transition; tab hover 0.15s.
- Playback default 2× (210ms/frame). Keyboard: space play, ←→ step.
- TODO: `prefers-reduced-motion` pass (disable auto-rotate + pulse) — flagged
  in PRODUCT.md accessibility.
