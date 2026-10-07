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

## Change log

- 2026-10-07, before any run: renamed the table column to "Observed in 2023"
  (it was "Expected by the model", which contradicted the known-risk
  section). Replaced the channel mask: the original rule (cells wet at median
  flow, no inflow, no rain) masks nothing under this design. Recorded the
  inflow design, the terrain-only check and the DEM policy.
