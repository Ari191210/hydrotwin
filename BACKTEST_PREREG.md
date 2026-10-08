# Backtest pre-registration: Delhi, Yamuna flood, July 2023

Written and committed 2026-10-07, **before any backtest run**. Whatever the
score is, it gets reported against these rules. Changes after the first run
go in the change log at the bottom, with the reason, and the original score
stays reported.

## Event (sources)

- Hathnikund Barrage (HKB) peak release 3,59,760 cusecs (~10,190 m3/s) at
  11:00-12:00 on 11 July 2023 (SANDRP, 2023-07-16; Hindustan Times).
- Yamuna at Old Railway Bridge (ORB), Delhi: record 208.66 m at 18:00 on
  13 July 2023, 1.17 m above the 1978 HFL (SANDRP).
- ITO and Rajghat flooded through the broken regulator of drain no. 12
  (near the WHO building / IP depot), which failed around 19:00 on 13 July
  and let river water flow back into the city (NDTV, ThePrint).
- GloFAS (Open-Meteo flood API) for the Delhi cells peaks near 1,000 m3/s
  on 13 July, about 10x below the HKB release. GloFAS does not reproduce
  this event and is not used as the backtest inflow.

## Question being tested

Given the river flow that reached Delhi, does the 2D model flood the places
that flooded, and leave dry the places that stayed dry? This tests the
hydraulics, not a rainfall or discharge forecast.

## Scoring sites (OSM Nominatim coordinates, see config.py)

| Group | Site | lat, lon | Observed in 2023 |
|---|---|---|---|
| A: overbank, scored | Yamuna Bazar | 28.6620, 77.2394 | flooded |
| A: overbank, scored | Kashmere Gate ISBT | 28.6687, 77.2304 | flooded |
| A: overbank, scored | Majnu ka Tilla | 28.7043, 77.2245 | flooded |
| B: mechanism unclear, scored separately | Red Fort (Ring Road) | 28.6561, 77.2408 | flooded |
| B: mechanism unclear, scored separately | Civil Lines | 28.6807, 77.2226 | flooded |
| C: drain backflow, outside the model | ITO | 28.6282, 77.2410 | flooded (via drain 12) |
| C: drain backflow, outside the model | Raj Ghat | 28.6442, 77.2498 | flooded (via drain 12) |
| D: control | Connaught Place | 28.6318, 77.2194 | dry |
| D: control | DU North Campus (Faculty of Arts area) | 28.6925, 77.2182 | dry |

The headline score is group A (x of 3), plus group D (false alarms, x of 2).
Group B is reported separately. Group C is reported as "outside what the
model can represent". If the model floods C overland, that gets reported too.

## Hit rule

A site counts as **flooded** if any cell within **250 m** (Chebyshev,
`ceil(250 / cell_size)` cells) of its snapped grid cell reaches water depth
**>= 0.30 m** (`FLOOD_DEPTH_M`) at any saved time in the run, **excluding
cells inside the main river channel**. The channel mask is the OSM Yamuna
river-area polygon (`natural=water` + `water=river`) rasterized to the grid,
plus the `waterway=river` centreline buffered by one cell. It is fixed from
OSM before the run and does not depend on any model output.

## Second metric: river stage

Modelled peak water-surface elevation (bed + depth) at the ORB cell, against
the observed 208.66 m. ORB coordinates get fixed from OSM before the run.

## Known risk, stated before running

The DEM is SRTM via AWS Terrain Tiles at zoom 11 (~67 m). SRTM is a surface
model: in dense old Delhi it reads rooftops, not streets. Snapped DEM
elevations at the group A sites are 211-218 m, which is 2.5-9 m above the
208.66 m observed peak. **With this DEM the model is expected to miss most
of group A.** If it does, that is the result, and the explanation is the
DEM, not a reason to change the thresholds.

## Inflow hydrograph (decided 2026-10-07, before any run)

Delhi's actual discharge in July 2023 is not public in the sources found,
and a 2-hour peak at HKB attenuates heavily over ~200 km. So:

- **Shape:** the HKB release series, if an hourly or daily series can be
  sourced. Otherwise a symmetric triangular hydrograph that rises over 48 h
  and falls over 48 h on top of the seasonal-median baseline.
- **Magnitude:** the one calibrated number. The peak excess inflow is set so
  that the modelled peak stage at the ORB cell matches the observed
  208.66 m (+/- 0.10 m). **ORB stage is therefore a calibration target, not
  a result,** and will not be reported as model skill.
- The independent check is the site hit/miss table above.
- Timing is not scored.

## Terrain-only check (done before any physics run)

Count of DEM cells below 208.66 m within 250 m of each site (SRTM via AWS
zoom 11; the pipeline's sigma-1.2 smoothing first, raw tile in brackets):

| Site | cells < 208.66 m (of 81) |
|---|---|
| Yamuna Bazar | 11 (raw 14) |
| Kashmere Gate ISBT | 0 (raw 4) |
| Majnu ka Tilla | 0 (raw 0); local minimum 215.3 m |
| Red Fort | 0 (raw 0) |
| Civil Lines | 0 (raw 0) |
| ITO | 2 (raw 8) |
| Raj Ghat | 12 (raw 21) |
| Connaught Place | 0 |
| DU North Campus | 0 |

On SRTM, with the pipeline as it is, at most 1 of the 3 group A sites
can flood, whatever the hydraulics do. The river surface slopes up toward
Majnu ka Tilla (~5 km upstream of ORB, roughly +1 m), but that is still
~4.5 m below the site's lowest cell.

## DEM

- **Primary:** the pipeline's DEM (SRTM, AWS Terrain Tiles, zoom 11,
  sigma-1.2 smoothing). It is unchanged for the backtest, so there is no
  terrain knob to tune.
- If a bare-earth DEM (FABDEM V1-2, CC BY-NC-SA 4.0) is added, it runs as a
  second, separately reported result with the same rules. FABDEM is licensed
  for non-commercial use only, and commercial use needs a Fathom license.

## Results (run 2026-10-08, calibration + scoring per the rules above)

There are two scored runs. **The pre-registered result is the in-tolerance
run (peak_q=2900).** The first run (peak_q=3500) missed the calibration
tolerance and is kept below for the record. Site outcomes are identical in
both.

### Pre-registered result: in-tolerance run, peak_q=2900 m3/s

**Calibration trials** (triangular hydrograph, rise/fall 48 h each, peaking
07-11; ORB stage = bed + peak depth over the saved frames):

| peak_q (m3/s) | ORB stage (m) | error vs 208.66 (m) | in ±0.10? |
|---|---|---|---|
| 0 (no river, diagnostic only) | 206.854 | -1.806 | no |
| 2400 | 208.517 | -0.143 | no |
| 2800 | 208.623 | -0.037 | yes |
| **2900** | **208.648** | **-0.012** | **yes** |
| 3000 | 208.672 | +0.012 | yes |
| 3200 | 208.716 | +0.056 | yes |
| 3500 | 208.777 | +0.117 | no |
| 3750 | 208.821 | +0.161 | no |
| 4000 | 208.864 | +0.204 | no |
| 5000 | 209.005 | +0.345 | no |

2900 was chosen for one reason only: the smallest absolute stage error
(0.01183 m, against 0.01190 m at 3000). The scored tables at 2800, 2900 and
3000 have the same nine outcomes, so the choice among the in-tolerance
values does not change the score. Save cadence: 2400, 2800 and 3200 were
first run with frames every 24 h; 0, 2800, 2900, 3000 and 3500 were run
with frames every 6 h; 3750, 4000 and 5000 (and the original 3500) are
earlier trials whose cadence was not recorded. 2800 gives the same stage
to 1 mm at 24 h and at 6 h, and the 3500 rerun at 6 h reproduces the
original 208.777 m. The saved ORB peak is the frame at t=120 h,
the hour the inflow peaks, so the true modelled peak may sit slightly above
the sampled one.

**Scoring setup:** frames saved every 6 h (45 frames), 67.1 m cells, search
radius 4 cells, threshold 0.30 m, OSM channel mask **908 cells** (fetched
before the run; Overpass returned 504 twice and succeeded on the third try).

| Site | Group | Observed | Modelled | Max depth (m) | Match |
|---|---|---|---|---|---|
| Yamuna Bazar | A | flooded | flooded | 3.32 | YES |
| Kashmere Gate ISBT | A | flooded | flooded | 2.23 | YES |
| Majnu ka Tilla | A | flooded | dry | 0.29 | no |
| Red Fort (Ring Road) | B | flooded | flooded | 1.67 | YES |
| Civil Lines | B | flooded | flooded | 2.69 | YES |
| ITO | C | flooded (drain 12) | dry | 0.05 | no (expected, outside the model) |
| Raj Ghat | C | flooded (drain 12) | flooded | 2.06 | YES by the hit rule (see below: not river water) |
| Connaught Place | D | dry | **flooded** | 0.76 | **no, false alarm** |
| DU North Campus | D | dry | dry | 0.01 | YES |

**Headline: Group A 2/3 correct.** Group D: 1/2 correct, one false alarm.
Group B 2/2. Group C: ITO dry, Raj Ghat flooded.

**Difference from the first run:** no site's outcome changed. Only Yamuna
Bazar's depth moved (3.45 m at 3500, 3.32 m at 2900). Every other site's
maximum depth is the same to within 2 mm.

### What the hits are made of (evidence, not a scoring change)

The score above stands as the rules give it. But two checks show that most
of the "flooded" calls do not come from the river:

1. **A run with no river inflow at all** (peak_q=0, same rain, same mask,
   same rules) gives the same depths at eight of the nine sites: Kashmere
   Gate 2.23 m, Red Fort 1.67 m, Civil Lines 2.69 m, Raj Ghat 2.06 m,
   Connaught Place 0.76 m, Majnu ka Tilla 0.29 m, ITO 0.05 m, DU North
   Campus 0.01 m. Only Yamuna Bazar changes: 0.01 m (dry) without the
   river, 3.32 m with it. With rain alone the table scores Group A 1/3.
2. **Connected components** of depth >= 0.30 m, labelled at each site's
   peak frame and also at every saved frame (4- and 8-connectivity agree):
   - Yamuna Bazar: its wet cells belong to one ~4,660-cell flooded area
     that includes the inflow cells and 484 channel-mask cells. River-fed,
     from t=84 h onward.
   - Kashmere Gate ISBT: an isolated 15-cell pond, water surface 212.92 m,
     which is 4.3 m above the modelled stage at ORB. Never connected to the
     river in any frame.
   - Red Fort: an isolated 10-cell pond, water surface 217.12 m. Never
     connected.
   - Civil Lines: an isolated 19-cell pond, water surface 214.98 m. Never
     connected.
   - Raj Ghat: an isolated 18-cell pond, water surface 208.58 m. Never
     connected, and identical with the river switched off.
   - Connaught Place: two isolated ponds of 3 and 5 cells, water surfaces
     218.74 m and 217.64 m, about 9-10 m above the river stage. Never
     connected.

So the honest reading is: **the river hydraulics produce exactly one of the
flooded calls, Yamuna Bazar, and it is correct.** Kashmere Gate, Red Fort,
Civil Lines and Raj Ghat count as hits under the frozen rule, but the water
there is 11 days of rain collecting in closed DEM depressions with no
drains and no infiltration. It is the same mechanism that produces the
Connaught Place false alarm. This agrees with the terrain-only check made
before any run ("at most 1 of the 3 group A sites can flood" from the
river). The hit rule did not separate river flooding from rain ponding,
which is a weakness of the rule as written. It is not changed here.

### First run (out of tolerance, kept for the record): peak_q=3500 m3/s

**Calibration:** peak excess inflow Q=3500 m3/s (triangular, rise/fall 48h
each, peaking 07-11) gives ORB stage 208.777 m against the 208.66 m
target — off by +0.12 m, outside the pre-registered ±0.10 m tolerance.
Accepted under time pressure rather than running another iteration; the
site table below is scored on this run, not a tuned-tighter one. Rescored
on 2026-10-08 with the 908-cell mask and 6 h frames, it reproduces this
table exactly.

| Site | Group | Observed | Modelled | Max depth (m) | Match |
|---|---|---|---|---|---|
| Yamuna Bazar | A | flooded | flooded | 3.45 | YES |
| Kashmere Gate ISBT | A | flooded | flooded | 2.23 | YES |
| Majnu ka Tilla | A | flooded | dry | 0.29 | no |
| Red Fort (Ring Road) | B | flooded | flooded | 1.67 | YES |
| Civil Lines | B | flooded | flooded | 2.69 | YES |
| ITO | C | flooded (drain 12) | dry | 0.05 | no (expected — outside the model) |
| Raj Ghat | C | flooded (drain 12) | flooded | 2.06 | YES by the hit rule (originally noted as "reached by overbank flow alone"; that was wrong, see above) |
| Connaught Place | D | dry | **flooded** | 0.76 | **no — false alarm** |
| DU North Campus | D | dry | dry | 0.01 | YES |

**Headline (first run): Group A 2/3 correct.** Group D: 1/2 correct, one
false alarm. Same as the in-tolerance run.

### Explanations (apply to both runs; checked against the 2900 numbers)

**The Majnu ka Tilla miss** matches the terrain-only check from Day 1
exactly (local minimum 215.3 m, DEM-imposed ceiling) — an explained,
pre-registered limitation, not a surprise. The 0.29 m found there is rain
ponding too (it is the same with the river switched off), just under the
0.30 m threshold.

**The Connaught Place false alarm, root-caused:** CP's own cell sits at
217.6 m, but a real local depression 200-300 m away dips to 216.3-216.6 m
(confirmed in the raw DEM, not a smoothing artifact). The model has no
storm-drain outflow or infiltration, so the full 11-day rain forcing
(~156 mm total, spread evenly across the whole grid) pools in ANY
enclosed low point on the map and eventually crosses the 0.30 m
threshold — unrelated to the Yamuna or the inflow calibration entirely.
The 2026-10-08 checks confirm this directly: the ponds are isolated from
the river-fed area in every saved frame, sit 9-10 m above the river stage,
and reach the same 0.76 m with zero river inflow.
This did not show up in the normal 6h demo because 6 hours of rain is
nowhere near enough to fill a pit this size; it only appears once the
run is stretched to 11 days for the backtest. This is the same category
of limitation as the ITO/Raj Ghat drain issue (no sewer network modeled)
but in the opposite direction — water that should drain away through
storm drains instead has nowhere to go in the model.

**For the pitch (corrected 2026-10-08).** The earlier wording here said
"2 of 3 main flood sites correctly identified from physics alone" and
called Red Fort, Civil Lines and Raj Ghat corroborations from "pure
overbank routing". The no-river run and the connectivity check show that
is not supportable, so it is withdrawn. What can be said:

- By the pre-registered rule the score is Group A 2/3, with one false
  alarm in 2 controls.
- The river model, calibrated on one number (ORB stage), floods Yamuna
  Bazar by overbank flow, which is what happened.
- The other "flooded" calls (Kashmere Gate, Red Fort, Civil Lines, Raj
  Ghat) and the Connaught Place false alarm are rain ponding in DEM
  depressions, because the model has no storm drains. They should not be
  presented as river-flood skill.
- The Majnu ka Tilla miss is the DEM limit stated before the run.

## Post-hoc variant: conditioned river bed (2026-10-08/09)

**This section is NOT pre-registered.** The DEM section above said the DEM
would be unchanged for the backtest. Here the DEM is changed, after the
pre-registered result was known. The pre-registered result (raw DEM,
peak_q=2900 m3/s, Group A 2/3, one false alarm) stands exactly as recorded
above. This variant is reported next to it, not instead of it.

### Why the DEM was changed

The change was made for the live demo, not for the backtest. On the raw DEM
the mapped Yamuna channel climbs and falls by metres (bars, noise over
water, bridge decks), so a steady 96 m3/s routed in at the north edge never
left the grid: the channel filled like a bathtub and the live view showed
flooding on a normal day. The fix (`river.condition_channel`, switched on
by `config.CHANNEL_CONDITIONING`) traces the thalweg from the inflow to the
outlet and cuts it to a non-increasing bed; cells are only lowered. That
false alarm was found in the live view, independently of the backtest
outcome. Because the demo now runs on the conditioned DEM, the backtest is
repeated on it so the two describe the same model.

### What changed and what did not

- **Changed:** the DEM only. 513 of 22,500 cells lowered (max 5.13 m, mean
  1.91 m), a 3-cell-wide channel along a 13.3 km thalweg from (148, 66) to
  the outlet (0, 100); 11 sills removed, the highest 4.64 m at (64, 88).
  No cell is raised. The ORB cell (72, 88) lies in the carved channel: its
  bed drops from 206.852 m to 203.638 m.
- **Not changed:** sites, hit rule (250 m, 0.30 m), OSM channel mask (the
  same cached 908 cells), rain series, triangular hydrograph (48 h rise,
  48 h fall, peak 07-11), dry start, 6 h frames (45 frames), the calibration
  rule (ORB stage within 0.10 m of 208.66 m) and the tie-break (smallest
  absolute stage error).
- **Inflow cells:** found with `river.find_inflow` on the conditioned DEM,
  as `run.py` does. The reported bed cell snaps one column over, (148, 65)
  instead of (148, 66), but the 15 inflow cells and the 9 closed boundary
  cells are identical to the raw-DEM run, and the simulation reads only
  those lists. So the water enters through the same cells.
- The live pipeline also warm-starts the river and uses GloFAS discharge.
  Neither is used here: the backtest keeps its own forcing and dry start.

Code: `backtest_delhi.setup(conditioned=True)` (default `False` reproduces
the raw setup; checked against the saved raw run, same elevation and inflow
cells), `backtest_conditioned.py` (trials, both scoring columns, control,
connectivity).

### Calibration trials (conditioned DEM, all with 6 h frames)

| peak_q (m3/s) | ORB stage (m) | error vs 208.66 (m) | in ±0.10? |
|---|---|---|---|
| 0 (no river, also the control run) | 203.954 | -4.706 | no |
| 4500 | 208.139 | -0.521 | no |
| 7000 | 208.522 | -0.138 | no |
| 7800 | 208.624 | -0.036 | yes |
| 8000 | 208.648 | -0.012 | yes |
| **8200** | **208.671** | **+0.011** | **yes** |
| 8400 | 208.694 | +0.034 | yes |
| 11000 | 208.969 | +0.309 | no |

These are all the trials that were run, in two batches of four (0, 4500,
7000, 11000, then 7800 to 8400). **8200 is chosen by the same tie-break as
before**, the smallest absolute stage error (0.0111 m, against 0.0121 m at
8000). All nine site outcomes, in both scoring columns below, are the same
at every trial from 4500 to 11000, so the choice does not change the score.
The saved ORB peak is again the frame at t=120 h.

**On the size of peak_q.** The calibrated peak is 2.8 times the raw-DEM
value (8200 against 2900). That is the expected direction: on the raw DEM
the ORB cell sat behind sills, so a small flow was enough to raise the
stage there; with a continuous bed 3.2 m lower the same stage needs far
more water. 8200 m3/s (excess above the dry-season baseline the DEM
already holds) is below the Hathnikund peak release (about 10,190 m3/s, so
about 80% of it) and below the 12,000 m3/s level at which this number would
have been flagged as not physically credible. But it would mean that about
80% of a 2-hour peak survived some 200 km of river, where this document
itself expects heavy attenuation, so it is not shown to be credible either.
It is not confirmed against a measured Delhi discharge (none was found),
and it is
still one calibrated number that absorbs the model's channel geometry
(a 3-cell, about 200 m wide carved slot) and roughness. It is not a
discharge estimate for the event.

### Scoring at peak_q=8200 m3/s

Two columns from the **same run**. The primary column is the pre-registered
hit rule with the pre-registered OSM channel mask (908 cells). The second
column is **not pre-registered**: it uses the live pipeline's fuller
exclusion (`scenarios.exclude_mask`): OSM mask (908) + inflow cells (15) +
bankfull footprint (3,497 cells, the steady wet area at 1,304 m3/s above
the dry-season baseline, steady after 18 h, cached in `assets/masks/`),
3,996 cells together. No site's window is fully excluded (the most is
Raj Ghat, 15 of 81 cells; Yamuna Bazar 12 of 81), so the "all cells
masked" fallback in the scoring code is never used.

| Site | Group | Observed | Primary: OSM mask (pre-registered rule) | Max depth (m) | Second: full exclusion (not pre-registered) | Max depth (m) | Match (both) |
|---|---|---|---|---|---|---|---|
| Yamuna Bazar | A | flooded | flooded | 3.55 | flooded | 1.24 | YES |
| Kashmere Gate ISBT | A | flooded | flooded | 2.23 | flooded | 2.23 | YES |
| Majnu ka Tilla | A | flooded | dry | 0.29 | dry | 0.29 | no |
| Red Fort (Ring Road) | B | flooded | flooded | 1.67 | flooded | 1.67 | YES |
| Civil Lines | B | flooded | flooded | 2.69 | flooded | 2.69 | YES |
| ITO | C | flooded (drain 12) | dry | 0.05 | dry | 0.05 | no (expected, outside the model) |
| Raj Ghat | C | flooded (drain 12) | flooded | 2.06 | flooded | 2.06 | YES by the hit rule (not river water, see below) |
| Connaught Place | D | dry | **flooded** | 0.76 | **flooded** | 0.76 | **no, false alarm** |
| DU North Campus | D | dry | dry | 0.01 | dry | 0.01 | YES |

**Headline, both columns: Group A 2/3 correct. Group D 1/2 correct, one
false alarm. Group B 2/2. Group C: ITO dry, Raj Ghat flooded.** The fuller
exclusion changes one number only: Yamuna Bazar's deepest counted cell
drops from 3.55 m to 1.24 m, because the deepest cells in its window are
inside the bankfull footprint. It is still flooded.

### Rain-only control and connectivity (conditioned DEM)

Rain-only run: peak_q=0, same rain, same masks, same rules.

| Site | Max depth with river, 8200 (m) | Max depth rain only (m) | Wet cells connected to the river-fed area? |
|---|---|---|---|
| Yamuna Bazar | 3.55 | 0.01 (dry) | **Yes.** One 5,214-cell area that holds all 15 inflow cells and 536 channel-mask cells; water surface at the site 209.33 to 209.47 m. Linked from t=84 h, in 15 of 45 frames |
| Kashmere Gate ISBT | 2.23 | 2.23 | No. Isolated 15-cell pond, surface 212.93 m, never linked in any frame |
| Majnu ka Tilla | 0.29 (dry) | 0.29 | Not flooded |
| Red Fort (Ring Road) | 1.67 | 1.67 | No. Isolated 10-cell pond, surface 217.12 m, never linked |
| Civil Lines | 2.69 | 2.69 | No. Isolated 19-cell pond, surface 214.98 m, never linked |
| ITO | 0.05 (dry) | 0.05 | Not flooded |
| Raj Ghat | 2.06 | 2.06 | No. Isolated 18-cell pond, surface 208.58 m, never linked |
| Connaught Place | 0.76 | 0.76 | No. Two isolated ponds of 3 and 5 cells, surfaces 218.74 m and 217.64 m, never linked |
| DU North Campus | 0.01 (dry) | 0.01 | Not flooded |

Method: connected components of depth >= 0.30 m, labelled at each site's
peak frame (the saved frame where its windowed maximum outside the OSM mask
is largest) and at every saved frame; "linked" means a wet site cell shares
a component with inflow cells or channel-mask cells. 4- and 8-connectivity
give the same answer for every site. With rain alone the table scores
Group A 1/3 (Kashmere Gate only), in both columns. The rain-only depths at
the eight other sites match the with-river depths to within 4 mm.

**What holds now: the same as on the raw DEM.** The river hydraulics
produce exactly one of the flooded calls, Yamuna Bazar, and it is correct.
Kashmere Gate, Red Fort, Civil Lines and Raj Ghat are hits under the frozen
rule, but they are the same rain ponds in closed depressions, at the same
depths and surfaces as before, 4 to 10 m above the river (Raj Ghat's pond
sits at 208.58 m, close to the river stage, but is never connected and is
the same with the river off). Connaught Place is the same rain-pond false
alarm. Conditioning lowered only cells in the river corridor, so it could
not drain these depressions, and it did not.

### Side by side

| | Pre-registered (raw DEM) | Post-hoc (conditioned river bed) |
|---|---|---|
| Status | pre-registered result | not pre-registered |
| ORB bed (m) | 206.852 | 203.638 |
| Calibrated peak_q (m3/s) | 2900 | 8200 |
| ORB stage (m), error | 208.648, -0.012 | 208.671, +0.011 |
| ORB depth at peak (m) | 1.80 | 5.03 |
| Rain-only ORB stage (m) | 206.854 | 203.954 |
| Group A | 2/3 | 2/3 (both columns) |
| Group B | 2/2 | 2/2 |
| Group C | ITO dry, Raj Ghat flooded | ITO dry, Raj Ghat flooded |
| Group D false alarms | 1 of 2 (Connaught Place) | 1 of 2 (Connaught Place) |
| Yamuna Bazar depth (m) | 3.32 | 3.55 (1.24 outside the bankfull footprint) |
| Other eight sites, depth | as tabled above | same to within 3 mm |
| Sites flooded by river water | Yamuna Bazar only | Yamuna Bazar only |
| River-fed area at t=120 h (cells >= 0.30 m) | 4,662 | 5,214 |
| ... of which outside the full exclusion (*) | 1,116 | 1,590 |

(*) The bankfull footprint exists only for the conditioned DEM. The raw-DEM
figure applies that same mask to the raw run for comparison; the raw
pipeline never had a footprint.

**Reading.** Conditioning the river bed does not change any site outcome,
and it does not make the backtest better or worse by the frozen rule. It
changes the calibrated inflow a great deal (2900 to 8200 m3/s), which shows
that the raw-DEM number was set by the sills in the channel and should not
be read as a discharge. The 8200 figure is below the 12,000 m3/s flag level
but is equally unverified and is not a discharge estimate. The evidence
the backtest gives for the river model is unchanged: one river-fed site,
correctly flooded; one DEM-limited miss; the rest is rain ponding that the
hit rule cannot tell apart from river flooding.

Not checked: a finer frame cadence than 6 h (the true stage peak may sit
slightly above the sampled one, as before); peak_q values between 8000 and
8200; the FABDEM variant (`BACKTEST_FABDEM.md`) was not rerun with a
conditioned bed.

The run is saved at `assets/backtest_delhi_2023_conditioned.npz` (same keys
as `assets/backtest_delhi_2023.npz`, `elevation` is the conditioned DEM,
plus `elevation_raw`, `bankfull_mask`, `exclude_mask_full`,
`dem_conditioned`, `dem_note` and the second-column and rain-only site
depths).

## Change log

- 2026-10-07, before any run: renamed the table column to "Observed in 2023"
  (it was "Expected by the model", which contradicted the known-risk
  section). Replaced the channel mask: the original rule (cells wet at median
  flow, no inflow, no rain) masks nothing under this design. Recorded the
  inflow design, the terrain-only check and the DEM policy.
- 2026-10-08, after running: accepted calibration at +0.12 m off target
  (outside the pre-registered ±0.10 m) rather than iterating further,
  under explicit time pressure. Noted here per the pre-registration's own
  rule that any deviation from the frozen process gets logged, not
  silently absorbed into a "looks right" result.
- 2026-10-08, later the same day: finished the calibration. peak_q=2900
  gives ORB stage 208.648 m (-0.012 m, inside the tolerance) and is now the
  pre-registered result; the 3500 table is kept as the first,
  out-of-tolerance run. No site outcome differs between the two. No rule
  was changed (threshold, radius, sites, mask rule). Process changes:
  scoring frames are saved every 6 h instead of 12 h, and the OSM channel
  mask is fetched with retries before the run and its size printed (908
  cells), because an empty mask on an Overpass failure would have changed
  which cells count. It is not known whether the first 3500 scoring had a
  non-empty mask; the 3500 rescore with the 908-cell mask gives the same
  table. Added a no-river run and a connectivity check as evidence, and
  withdrew the "from physics alone" and "pure overbank routing" wording,
  which they contradict. The calibrated run is saved at
  `assets/backtest_delhi_2023.npz`.
- 2026-10-09 (work started 2026-10-08), after the pre-registered result:
  added the section "Post-hoc variant: conditioned river bed". It reruns
  the backtest on the channel-conditioned DEM the live demo now uses, which
  departs from the DEM section ("unchanged for the backtest") and is
  therefore labelled not pre-registered. Reason for the DEM change: a
  normal-day false alarm in the live view (the raw channel ponded), found
  independently of the backtest outcome. Nothing else was changed (sites,
  hit rule, OSM mask, rain, hydrograph shape, calibration rule). Result:
  peak_q=8200 m3/s gives ORB stage 208.671 m (+0.011 m); all nine site
  outcomes equal the pre-registered ones (Group A 2/3, one false alarm),
  also under the live pipeline's fuller exclusion, and Yamuna Bazar is
  still the only river-fed site. The pre-registered result is not
  replaced. Code: `setup(conditioned=False)` and a `conditioned=False`
  argument to `calib_trial` in `backtest_delhi.py`, `--conditioned` in
  `calib_parallel.py`, an optional `extra=` in `score_backtest.save_run`,
  and the new `backtest_conditioned.py`; all defaults reproduce the
  earlier behaviour. Run saved at
  `assets/backtest_delhi_2023_conditioned.npz`.
