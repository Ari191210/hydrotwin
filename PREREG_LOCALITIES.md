# Pre-registration: level-indexed lookup against 2023 localities

Written and committed 2026-10-10, before the stage library
(`stagelib.py`) was read or scored. This is a second, larger test than
the nine-site one in BACKTEST_PREREG.md, with a different method.

## Why a second test

- The official warning stages are keyed to the barrage release. Across
  the eight large floods from 1978 to 2019 a larger Hathnikund release
  went with a higher level at Delhi (r = 0.67). A straight-line fit to
  those eight predicts 206.13 m for the 2023 release. The observed peak
  was 208.66 m, 2.53 m higher. (Data: SANDRP, 16 July 2023.)
- So the lookup here is keyed on the river level at the Old Railway
  Bridge, not on the release.
- The earlier backtest ran 11 days with rain, and rain pooled in closed
  terrain dips because the model has no drains. Here every run is river
  only, at steady state, so that artefact cannot produce a "hit".

## Method (fixed)

1. `stagelib.py` runs the model to steady state with no rain at a ladder
   of river discharges on the channel-conditioned DEM. Each run gives one
   level at the Old Railway Bridge cell and one depth field.
2. The depth field for the 2023 record level, 208.66 m, is the linear
   interpolation between the two runs that bracket it. No calibration:
   the only input is the observed level.
3. A locality counts as **flooded in the model** if any cell within
   250 m (Chebyshev, `ceil(250 / cell_size)` cells) of its grid cell has
   depth >= 0.30 m, excluding cells in the OpenStreetMap river mask.
   These are the same threshold, radius and mask as BACKTEST_PREREG.md.
4. Two elevation datasets are scored and both are reported: SRTM (the
   default, a surface model that reads rooftops) and FABDEM (bare earth,
   non-commercial licence). SRTM is the primary result.

## Localities (fixed, `localities.py`)

- 7 "river" localities: recorded as submerged in July 2023.
- 3 "drain" localities: recorded as flooded, attributed to drain backflow
  or the drain 12 regulator. Not expected to flood in the model. Reported
  separately and not counted in the scores.
- 12 "dry" localities: no record of Yamuna flooding found. This is the
  absence of a report, not a record of staying dry.

Dropped before scoring because OpenStreetMap could not place them or
placed them wrongly: Garhi Mandu, Old Usmanpur village, Monastery Market,
Sadar Bazar. Shastri Park was dropped because I could not confirm a
source for its 2023 flooding.

## Scores (fixed)

On the 19 river + dry localities, for each dataset:
- hits (river localities flooded in the model), of 7
- false alarms (dry localities flooded in the model), of 12
- critical success index = hits / (hits + misses + false alarms)

Baseline to beat, also fixed now: the "bathtub" rule that a locality
floods if any raw DEM cell within 250 m lies below 208.66 m. A hydraulic
model that cannot beat that rule adds nothing.

## Known risks, stated before scoring

- SRTM reads rooftops, so river localities may be out of reach.
- East-bank colonies (Geeta Colony, Gandhi Nagar, Seelampur) sit low but
  behind embankments that a 67 m grid may not resolve, so false alarms
  there are likely.
- The domain is about 10 km. Localities further downstream (Jaitpur,
  Badarpur Khadar, Okhla) that the official report lists are outside it
  and are not tested.

## Change log

(empty)
