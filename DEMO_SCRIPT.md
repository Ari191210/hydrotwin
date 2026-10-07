# HydroTwin demo script — ~3 minutes

Written 2026-10-08, Day 3. Pitch: district disaster officers (the one
user from the 2026-10-07 interview — residents/planners are "what's
next", not shown live). Guaranteed-offline path is primary; the live
server is the backup if asked "does this work for ANY city."

**Before judges arrive:** `outputs/delhi/flood_3d.html` open in a
browser tab already, zoomed to the terrain view, auto-rotate OFF (so the
screen isn't moving while you talk over it). Confirm `outputs/index.html`
and the `delhi`/`rishikesh`/`hue` folders are current (`run.py` with no
args rebuilds all three — do this once the morning of judging, since
rainfall/river numbers are live-fetched at build time).

## 0. One line before touching anything (10s)

"HydroTwin simulates floods with real physics — not a model that just
guesses from past data — and we checked it against a flood that actually
happened."

## 1. The backtest first, not the live demo (60s)

This is the credibility beat. Lead with it, don't bury it.

- Say: "In July 2023 the Yamuna hit a record 208.66 metres in Delhi and
  flooded Yamuna Bazar, Kashmere Gate, the Red Fort stretch. We fed our
  model the same river conditions and asked: does it get it right?"
- Show the terminal output or a prepared slide from
  `BACKTEST_PREREG.md`'s Results section:
  - **2 of 3 main flood sites correctly identified** (Yamuna Bazar,
    Kashmere Gate ISBT) — flooded, matching reality.
  - **The one miss (Majnu ka Tilla) is explained, not hidden:** our
    elevation data doesn't resolve that street's actual height — we
    said this BEFORE running the test, not after.
  - **Bonus:** two more sites (Red Fort, Civil Lines) and Raj Ghat
    flooded correctly from pure physics, with zero tuning toward them.
  - One false alarm (Connaught Place), root-caused to a real local dip
    in the terrain plus no storm-drain modeling — name it if asked, it's
    in the writeup.
- Say: "We pre-registered exactly what would count as a hit before we
  ran it once. That table is in the repo, dated before the run."

**If a judge asks "why not all 3 / why the false alarm" — this is a WIN,
not a weakness, to have a ready, honest answer for. Don't get defensive.**

## 2. The live scene (60s)

- Switch to the open Delhi tab. Point at the satellite imagery under the
  terrain — "that's the real Yamuna, real streets."
- Scrub the timeline or hit play — water rises from the north edge
  (where the river enters) and spreads downstream, not a canned
  animation.
- Point at the honesty banner if a what-if scenario or synthetic terrain
  ever shows (it's yellow, impossible to miss) — "if anything on screen
  isn't the real forecast, it says so, right here."
- Point at the river discharge panel — "that's today's actual Yamuna
  flow against its 30-year seasonal average, not a static number."

## 3. The ML instant-preview, 20s, only if there's time

- Toggle "ML instant preview" ON in the right panel.
- Drag the river-excess slider — "that's not a 20-second physics rerun,
  that's instant, from a model fit to 380 of our own simulations. It's
  accurate to about 3 centimetres on water we never showed it during
  training" — point at the RMSE/IoU numbers printed right in the panel.
- Toggle it back OFF before moving on — don't leave the validated
  physics view showing an ML-preview state.

## 4. Laya field report, 15-20s

- Switch to the live server tab (pre-warmed — Laya takes ~90s to load,
  do this BEFORE judges arrive, not during).
- Submit one canned report ("water rising near the hospital, roads
  cut off") on a zone that's currently "monitor" priority.
- Point at it escalating, or if no exact POI match, say plainly: "field
  reports only auto-place when they name a known landmark exactly — this
  one didn't, so it's logged but not yet placed. We don't fake a match."

## 5. Close (15s)

"The physics is real, the backtest is real and the misses are explained,
and an officer using this sees exactly where the numbers come from. That's
the bar we held ourselves to."

## Fallback order if anything breaks live

1. Live server down / slow / no internet → `outputs/index.html` (fully
   offline, pre-built that morning).
2. Laya not loaded in time → skip step 4, don't apologize at length,
   move to the close.
3. A what-if/synthetic-terrain banner appears unexpectedly → use it as
   proof of the honesty design, don't scramble to hide it.

## Known weak points — have an answer ready, don't dodge

- Only 1 location backtested (Delhi) — "that's the one with a real flood
  record to check against; the other two are architecturally the same
  pipeline, just not validated against history yet."
- The ML preview is Delhi-only — "it's a fit to one fixed terrain's
  response surface, not a general flood predictor; we said that, it's in
  the panel."
- Evacuation decisions are advisory — "the AI (or the rule-based
  fallback) drafts zones and a public alert; a human officer makes the
  call. We don't present this as autonomous."
