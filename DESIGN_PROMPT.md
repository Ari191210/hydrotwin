# Claude Design prompt: HydroTwin operations console

Paste everything below the line into Claude Design.

---

Design the interface for **HydroTwin**, a live flood-forecasting operations console. Deliver high-fidelity screens, not a moodboard. Where these instructions conflict with your defaults, follow the instructions.

## 1. What the product does (so the layout tells this story)

A duty officer types any city or `lat,lon`. The server fetches real terrain (SRTM), live rainfall (Open-Meteo) and live river discharge (Copernicus GloFAS). It then runs a 2D shallow-water physics simulation (Landlab) three times, at 1×, 2× and 3× storm intensity, which takes about 25 s. It turns the result into a 4×4 grid of evacuation zones (A1 to D4, A = north row, 1 = west column), each rated **immediate / high / monitor**. The centerpiece is a rotatable **3D terrain with animated flood water** (three.js, full-bleed WebGL canvas).

New layer: **field reports triaged by Laya.** The officer pastes a message from the ground in any language (English, Hindi, Hinglish, Vietnamese…). A local classifier reads it in about 1 to 3 s and returns: need type, urgency, flags, the place it mentions, and which model read it. A report can **raise** a zone's priority, never lower it. Physics is the baseline and people on the ground add to it.

The story a first-time viewer must get in 30 seconds: **rain fell → water flowed over real ground → these zones evacuate, and here's why (physics + people on the ground).**

## 2. Brand and register

Mission-control precision: dark, exact, calm authority. The terrain is the hero and the panels annotate it. Urgency is carried by one color only.

**Anti-references (do not produce):** a generic AI-SaaS dashboard (gradient text, purple-blue glow, identical card grids, decorative glassmorphism), a video-game HUD (neon, bevels, scanlines, minimap chrome), or emoji as icons.

## 3. Tokens (keep these exact values; you may add tokens but not change these)

| token | value | role |
|---|---|---|
| bg0 / bg1 | `#04070c` / `#0b111b` | page radial gradient |
| panel | `rgba(9,13,20,.92)` | floating panel surface |
| line / line2 | `rgba(148,178,215,.10)` / `.22` | dividers / borders |
| text | `#e6edf6` | primary text |
| dim / dimmer | `#8494a9` / `#71829a` | secondary / labels |
| accent | `#45cfe9` | water, time, interactive |
| red | `#ff5c57` | **ONLY** the flood alert and `immediate` priority |
| orange | `#ffab40` | `high` priority |
| yellow | `#ffd54f` | `monitor` priority |
| safe | `#4cd97b` | SAFE / live / model-ready status |

Type: **Space Grotesk** (display and UI) and **IBM Plex Mono** (all numbers, units, timestamps, model/routing metadata). Use tabular numerals everywhere a value updates live.

## 4. Hard constraints

1. **Implementable as one self-contained HTML string generated from Python.** Vanilla HTML, CSS and JS only: no React, no Tailwind, no build step, no CDN, no web-font service. The two fonts are embedded as base64 `@font-face`, and icons must be inline SVG.
2. **Red is sacred.** It appears only on the alert and on `immediate` chips and zones. Hover states, errors, the "high" live-risk badge and brand accents must not use red.
3. **Contrast:** all text ≥ 4.5:1 against its actual panel background. Check `dimmer` on `panel` in particular.
4. **Motion:** everything respects `prefers-reduced-motion`, which disables auto-rotate and pulses and turns transitions into instant state changes. Default easing is `cubic-bezier(.22,1,.36,1)`, and panels take 180 to 240 ms.
5. **No invented data.** Every number on screen must come from the fields listed in §7. No sparkline, score or metric may exist without a source field.
6. **Keyboard:** space = play/pause, ←/→ = step, `/` = focus search (new), `R` = open field reports (new), Esc closes any drawer. Every control has a visible focus ring (2px accent, 1px offset).
7. **Breakpoints:** desktop 1440×900 is primary, and a laptop at 1280×720 must not scroll the page. At ≤ 980 px the 3D view stays primary and panels become bottom sheets. Mobile is 390×844.

## 5. Current layout problems to fix

- **The brand appears twice and search is split.** The outer shell has a top bar (brand + search + live strip), and the embedded viewer has its own brand panel and case tabs. Merge them into one top bar.
- **Presets appear twice.** There are preset chips bottom-left in the shell and case tabs inside the viewer. Keep one: suggested locations inside the search dropdown when it is empty.
- **The left sidebar is a 344 px column with 8 stacked sections** (alert, 5 stats, hydrograph, river discharge, evacuation priorities, POIs, data sources + sitrep download). It scrolls and competes with the terrain. Restructure it: the alert and key stats are always visible, and the rest sits in tabs or progressive disclosure.
- **The field-reports drawer (top-right, 360 px) covers the view-options panel.** Give field reports a proper home that works alongside the zone list, since reports change zone priorities.
- **The view options panel** (storm scenario, terrain view mode, rain particles, auto-rotate, water opacity, legend) is a loose stack of form controls. Tighten it into a compact segmented control group plus legend.

## 6. Screens to deliver (name frames exactly)

1. `01-empty`: first load, no location yet. Hero: "HYDROTWIN / Physics-informed flood forecasting for any location on Earth." The search is focused, and the suggestions show **Rishikesh (steep Himalayan valley), Delhi (Yamuna floodplain), Huế (coastal monsoon basin)**.
2. `02-computing`: the forecast is running. Show real staged progress with these exact stage strings in order: `locating basin` 5% → `fetching terrain` 12% → `placing points of interest` 30% → `reading live rainfall` 40% → `reading live river discharge` 48% → `running physics 1/3 (storm x1)` 52% → `running physics 2/3 (storm x2)` 64% → `running physics 3/3 (storm x3)` 77% → `rendering 3D scene` 92% → `done`. Typical total is 25 s, and cached locations are instant.
3. `03-forecast`: the main console for Delhi at peak flood (details in §7).
4. `04-reports-open`: the same console with the field-reports surface open and three triaged reports (§8), one of which escalated zone A1.
5. `05-report-states`: a component sheet with every state from §8.
6. `06-degraded`: the console when data sources fell back (§9).
7. `07-mobile`: 390×844 versions of 03 and 04.

## 7. Console contents (03-forecast), with sample data from actual pipeline runs for Delhi (28.66, 77.23)

**Top bar (single row):** wordmark · search (placeholder "Search any city or lat,lon") · live strip with `LIVE CLOCK (UTC) 07:48:46` · `CONDITIONS Partly cloudy 37°` · `RAIN NOW 0.0 mm/h` · `RIVER 577 m³/s` (▲/▼ appears when discharge moves more than 3%) · `LIVE RISK NORMAL` badge ("no active rain, river near seasonal median" on hover; normal = safe, elevated = orange, high = orange with a stronger treatment, **not red**; the reason shows on hover) · live dot (green pulsing; grey when stale) · field-reports button with count.

**Alert (always visible, the only red block):** "Flooding up to 2.68 m is expected in zone D3 and surrounding areas: residents in affected zones should move to higher ground now." Show its source label: `Claude (claude-sonnet-5)` or `rule-based fallback`.

**Stats:** peak depth `2.68 m` · flooded area `0.30 km²` · water volume (Mm³) · zones flagged `7` · people in flooded area (est.) `891`.

**Evacuation priorities:** these are the zones from that run: D3 immediate ("max depth 2.68 m, 18.9% of zone above 0.3 m; contains Kasturba Hospital (hospital)"), C3 immediate, C2 immediate, B3 immediate, A3 high, B2 high, A2 high. Each row shows the zone id, a priority chip and the reason. Zones escalated by a field report carry a small "field report" marker and the report excerpt, and they sort to the top of their priority band. Empty state: "No evacuation needed." When the forecast is minor, the alert reads "Minor ponding only; no evacuation needed, but stay alert for updated forecasts." and uses no red.

**Stress case (also design it, as a variant of 03):** another real Delhi run (SRTM terrain, design storm) flagged **all 16 zones immediate**. The alert read "Flooding up to 6.2 m is expected in zone C1…", with peak depth 6.2 m, 1.77 km² flooded and 5,303 people estimated. The priorities list must stay readable when every row is red. Group or summarize it (for example "16 immediate · sorted by depth") rather than showing 16 identical red rows, and still keep every zone reachable.

**Points of interest:** hospitals, schools and roads/bridges from OpenStreetMap. Each row shows a type glyph, the name, the zone, and either `SAFE` or the depth, e.g. `1.4 m`.

**Hydrograph:** flooded area and volume over time (canvas), clickable to seek.

**River discharge (GloFAS):** today's value `577.1 m³/s`, trend chip, a small bar series, and a footnote with the timestamp. Hidden when no river is near.

**Data sources:** terrain source, rain source, decisions source, issued-at time, and a "download sitrep" action.

**3D scene controls:** storm scenario segmented control `1× / 2× / 3×` (switching melts the water between states) · terrain view mode `terrain / zones / arrival` (zones = priority tint overlay, arrival = "floods first → floods last" ramp) · rainfall particles toggle · auto-rotate toggle · water opacity slider (30–100) · depth legend `0 m → {max} m` · compass · scale bar · hover readout ("hover terrain for readout" → elevation + depth at cursor) · POI pins with hover tooltip · evacuation route arrows from urgent zones toward the driest neighbour.

**Timeline (bottom center):** hourly rain bars that light up to the current time, a play button, a scrubber with event marks, a time label, and speed `1× / 2× / 4×` (default 2×). Keep the "Run presentation" auto-tour, which should be one clearly secondary button.

## 8. Field reports (the new Laya layer): exact fields and states

Input: a multiline text box (max 600 chars, any language), a zone picker (`zone: auto` or A1…D4) and a **Triage** button (label "Reading…" while running, about 1–3 s).

Each triaged report card shows:
- the original text, in its own script
- **need**: rescue / medical / supplies / infrastructure / observation / irrelevant, plus confidence %
- **severity**: immediate / high / monitor / none, using the same chips as zones
- **urgency** `1.5/2`
- **flags**: trapped, rising, vulnerable (only those present)
- **place**: `zone A1` or `zone D3 · Kasturba Hospital` when the text names a mapped place, or `no zone · maybe Yamuna Bridge` when the model only suggests one (the officer must confirm it; design this confirm affordance)
- **escalation** line when it changed something: `A1: no action → immediate`
- **model metadata** (mono, dim): `multilingual checkpoint · 909 ms · non-Latin script (devanagari, 100% of letters)`

Sample reports for 04-reports-open (the classifier outputs are real Laya results; only the place name in #2 is swapped to fit this sample):
1. "पानी तेजी से बढ़ रहा है, हमारे घर में बच्चे फंसे हुए हैं, नाव भेजिए" → rescue 39%, immediate, urgency 1.5/2, trapped + rising, zone A1 (picked by the officer), escalated `A1: no action → immediate`, multilingual checkpoint 909 ms. Note that this card shows **two states at once**: a hedged low-confidence need (39%) *and* a confident escalation. The escalation is driven by the trapped/rising flags, not the need label, so the card must make that reasoning visible rather than look contradictory.
2. "We have had no drinking water or food for two days near Kasturba Hospital" → supplies 79%, high, urgency 1.6/2, zone D3 · Kasturba Hospital (name match), english checkpoint 2515 ms, no escalation because D3 is already immediate.
3. "Light rain, river looks normal here" → observation, severity none, zone D3, no escalation (show that the physics priority stayed in place).

States for 05-report-states: model loading ("loading model… about 60 s after server start"; the input is enabled but Triage is disabled), model ready, model unavailable (error detail, rest of console unaffected), "run a forecast for this location first", low-confidence need (< 50%: visually hedged), a report that suggests a place but has no zone, an empty list ("No reports yet. Reports can raise a zone's priority, never lower what the physics says."), and a long-text overflow case.

## 9. Degraded states (06-degraded)

Show these honestly as named, calm labels, not errors: terrain `synthetic river valley` (SRTM fetch failed), POIs `District Hospital / Community School / River Bridge / Main Road Junction` (the OpenStreetMap lookup failed, so these are synthetic placeholders; label them as such), rain `built-in design storm` (forecast too dry or offline), decisions `rule-based fallback` (no API key), river section hidden (no river cell nearby), live dot grey + `n/a` values (live feed stale).

## 10. Output format

For every frame, give me:
1. the screen at the stated size
2. a component inventory with states (default, hover, focus, active, disabled)
3. spacing and type scale tokens (px), radius, shadow and blur values
4. a short note per section explaining why it sits where it does

The implementation will be hand-ported into vanilla CSS, so name every component and state explicitly.
