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

| Group | Site | lat, lon | Expected by the model |
|---|---|---|---|
| A: overbank, scored | Yamuna Bazar | 28.6620, 77.2394 | flooded |
| A: overbank, scored | Kashmere Gate ISBT | 28.6687, 77.2304 | flooded |
| A: overbank, scored | Majnu ka Tilla | 28.7043, 77.2245 | flooded |
| B: mechanism unclear, scored separately | Red Fort (Ring Road) | 28.6561, 77.2408 | flooded |
| B: mechanism unclear, scored separately | Civil Lines | 28.6807, 77.2226 | flooded |
| C: drain backflow, NOT expected | ITO | 28.6282, 77.2410 | dry (no drains in model) |
| C: drain backflow, NOT expected | Raj Ghat | 28.6442, 77.2498 | dry (no drains in model) |
| D: control, should stay dry | Connaught Place | 28.6318, 77.2194 | dry |
| D: control, should stay dry | DU North Campus (Faculty of Arts area) | 28.6925, 77.2182 | dry |

The headline score is group A (x of 3), plus group D (false alarms, x of 2).
Group B is reported separately. Group C is reported as "outside what the
model can represent". If the model floods C overland, that gets reported too.

## Hit rule

A site counts as **flooded** if any cell within **250 m** (Chebyshev,
`ceil(250 / cell_size)` cells) of its snapped grid cell reaches water depth
**>= 0.30 m** (`FLOOD_DEPTH_M`) at any saved time in the run, **excluding
cells inside the main river channel**. The channel mask is the set of cells
already wet (>= 0.30 m) in a run at the seasonal-median flow (zero excess
inflow) with no rain.

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

## Still open (decided and recorded here before the run)

- Inflow hydrograph at the domain's north edge (HKB release series, travel
  time and attenuation over ~200 km), and its source.
- Whether a bare-earth DEM (e.g. FABDEM) is used. If it is, both DEM results
  are reported.

## Change log

(empty)
