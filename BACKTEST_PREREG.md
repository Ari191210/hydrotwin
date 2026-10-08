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
