# Backtest, second result: Delhi July 2023 on a bare-earth DEM (FABDEM V1-2)

Run 2026-10-08. This is the **second, separately reported result** that the
DEM section of `BACKTEST_PREREG.md` allows for. It is **not a replacement**
for the primary (SRTM) result, and the primary pipeline, the primary DEM and
the primary result are unchanged. Nothing in `BACKTEST_PREREG.md`,
`terrain.py`, `backtest_delhi.py`, `score_backtest.py` or `config.py` was
edited. Everything here is produced by `fabdem_backtest.py`, which imports
the primary code and swaps only the elevation array.

## Short version

- Calibrated by the pre-registered rule, FABDEM gives **Group A 3/3** and
  **Group D 1 false alarm of 2** (Connaught Place, same as SRTM).
- That calibration needs a peak excess inflow of **24,000 m3/s**, which is
  about **2.4 times the Hathnikund peak release** (about 10,190 m3/s) that
  caused the flood, and about 8 times the 2,900 m3/s of the SRTM
  calibration. That inflow is not physically credible.
- At every trial at or below the Hathnikund peak (2,000, 5,000 and
  9,000 m3/s) the FABDEM result is **Group A 2/3**, the same headline as
  SRTM, and the ORB stage is 0.9 m or more below the observed 208.66 m.
- Group B is **worse** on FABDEM by the rule: 0 of 2 (Red Fort and Civil
  Lines stay dry at every trial), against 2 of 2 on SRTM. The primary
  document now says those two SRTM hits are rain ponding, not river water.
- The one difference that holds at every trial with river inflow (2,000
  m3/s and up): on FABDEM the river itself reaches **Kashmere Gate ISBT**
  as well as Yamuna Bazar. On SRTM the river reaches only Yamuna Bazar.
  This rests on a no-river run and a peak-envelope connectivity check.
- So the table below shows 3/3 under the rule as written, but this should
  not be presented as "the bare-earth DEM fixes the Majnu ka Tilla miss".
  See "How much weight the 3/3 can carry".

## Licence

FABDEM V1-2 (Hawker et al., 2022, University of Bristol and Fathom) is
licensed **CC BY-NC-SA 4.0: non-commercial use only**. Commercial use needs
a licence from Fathom. The tile and every grid derived from it under
`assets/dem/` carry that restriction. This result is fine for a competition
demo and for research. It must not ship in a commercial product without
that licence, and derived data must be shared under the same terms.

## Data and how it was read

- Tile: `N28E077_FABDEM_V1-2.tif` (23,812,146 bytes) from
  `https://huggingface.co/buckets/links-ads/fabdem/resolve/tiles/N20E070-N30E080_FABDEM_V1-2/N28E077_FABDEM_V1-2.tif`,
  saved to `assets/dem/`. The first download attempt failed with a
  connection reset and the retry returned HTTP 200.
- Read with `tifffile` (plus `imagecodecs` for the deflate tiles), both
  installed into the venv with pip.
- Georeferencing was taken from the file's own tags, not assumed:
  - 3600 x 3600, float32, no nodata pixels in the tile (`GDAL_NODATA` is
    -9999 and occurs 0 times).
  - `GeographicTypeGeoKey` 4326 (WGS 84), angular unit degrees.
  - `ModelPixelScaleTag` (1/3600, 1/3600, 0).
  - `ModelTiepointTag` (0, 0, 0, 77.0, 29.0, 0): pixel (0, 0) is at lon
    77.0, lat 29.0, so the raster is north-up and row 0 is the north edge.
  - `GTRasterTypeGeoKey` is RasterPixelIsPoint, so the tiepoint is the
    **centre** of pixel (0, 0). Pixel (i, j) centre is lat 29 - i/3600,
    lon 77 + j/3600. No half-pixel shift was added. The other reading
    would move everything by about 15 m, under a quarter of a grid cell.
- Known-value check, nearest tile pixel: Yamuna at 28.66, 77.25 reads
  205.80 m. The ORB coordinates (28.6636, 77.2487) read 204.07 m. Kamla
  Nehru Ridge (28.687, 77.214) reads 222.62 m. Central Ridge (28.61, 77.18)
  reads 243.06 m. River about 200 to 206 m, Ridge higher, as expected.

## Resampling onto the primary grid

- Target grid is exactly the primary one: 150 x 150 cells, Web-Mercator
  zoom 11, 67.07 m per cell, centred 28.665, 77.240, same integer pixel
  origin as `terrain.latlon_to_rc`, row 0 = south. Each cell centre is the
  inverse of that function's crop (pixel x0 + col + 0.5, y0 + (149 - row)
  + 0.5, then inverse Mercator).
- Round-trip check: `terrain.latlon_to_rc` of every cell centre returns
  that same (row, col). Mismatches: **0 of 22,500**.
- Method: **bilinear sampling at cell centres.** This was fixed before any
  simulation. Nodata handling (a weight-normalised bilinear mean) is in the
  code but was never triggered: 0 cells had any nodata weight.
- Then the same `terrain._sanity_check` and the same sigma-1.2 gaussian
  (`terrain._fill_noise_pits`) as the primary. The only difference from
  the primary is the elevation source.
- Sensitivity, not simulated: a block mean (4 x 4 bilinear sub-samples per
  cell) was also built. Its terrain-only counts are identical to the
  bilinear grid for 8 of 9 sites (Red Fort is 2 instead of 4).

## Alignment check against the primary DEM

SRTM grid is from `terrain.load_terrain()` (AWS Terrain Tiles, zoom 11).

| Check | Value |
|---|---|
| Pearson r, smoothed grids (the ones the model uses) | 0.976 |
| Pearson r, raw grids | 0.955 |
| FABDEM minus SRTM, smoothed: mean / median | -1.89 m / -1.74 m |
| FABDEM minus SRTM, raw: mean / median | -1.89 m / -1.69 m |
| FABDEM minus SRTM, smoothed: std, 5th to 95th percentile | 1.89 m, -5.03 to +0.88 m |
| High-pass correlation (sigma-8 trend removed) at zero shift | 0.695 |
| Best high-pass correlation over shifts of +/-3 cells | 0.695 at shift (0, 0) |
| Mean elevation inside / outside the OSM channel mask, FABDEM | 205.91 m / 212.86 m |
| Mean elevation inside / outside the OSM channel mask, SRTM | 208.22 m / 214.73 m |
| FABDEM minus SRTM inside mask / outside mask (mean) | -2.32 m / -1.87 m |

The grids are co-registered: with the regional trend removed, the
correlation peaks at zero offset, and the OSM river polygon sits in the low
cells of both DEMs (about 7 m below the rest of the grid on each).

One check was weak and is reported as such: the per-row lowest cell near
the OSM channel differs between the two DEMs by a median of 2 cells and a
mean of 7.6 cells, within 2 cells in only 77 of 150 rows. The floodplain is
wide and nearly flat, so "lowest cell in the row" is noisy. It is not good
evidence either way.

FABDEM is lower than SRTM almost everywhere, by about 1.7 to 1.9 m, which
is what removing buildings and trees should do. Part of that could also be
a vertical datum offset: FABDEM inherits EGM2008 from Copernicus DEM, SRTM
is EGM96, and the 208.66 m gauge reading is on the Indian mean sea level
datum. No datum correction was applied. The calibration absorbs a constant
offset for the hydraulics. The terrain-only check below compares against
an absolute 208.66 m and does not.

The ORB cell (72, 88) is 203.82 m on FABDEM and 206.85 m on SRTM. So the
target stage needs 4.84 m of water at ORB on FABDEM against 1.81 m on SRTM.
The bed is below 208.66 m, so the target is reachable in principle.

The inflow snaps differently on this DEM (same `river.find_inflow` code):
north edge at cell (148, 64), bed 203.3 m, channel about 469 m, 35 inflow
cells. On SRTM it is cell (148, 66), bed 204.5 m, about 201 m, 15 cells.

## Terrain-only check (before any physics run)

Cells below 208.66 m within 250 m (9 x 9 window, 81 cells), smoothed grid
first, raw grid in brackets. The SRTM column was recomputed here and
matches the numbers already in `BACKTEST_PREREG.md` exactly.

| Site | Group | SRTM cells < 208.66 (of 81) | SRTM local min | FABDEM cells < 208.66 (of 81) | FABDEM local min |
|---|---|---|---|---|---|
| Yamuna Bazar | A | 11 (raw 14) | 205.78 m | 39 (raw 41) | 201.61 m |
| Kashmere Gate ISBT | A | 0 (raw 4) | 210.30 m | 11 (raw 14) | 206.06 m |
| Majnu ka Tilla | A | 0 (raw 0) | 215.33 m | 0 (raw 0) | 211.68 m |
| Red Fort (Ring Road) | B | 0 (raw 0) | 211.39 m | 4 (raw 8) | 208.38 m |
| Civil Lines | B | 0 (raw 0) | 212.28 m | 0 (raw 0) | 211.21 m |
| ITO | C | 2 (raw 8) | 208.43 m | 47 (raw 48) | 206.18 m |
| Raj Ghat | C | 12 (raw 21) | 206.52 m | 45 (raw 55) | 206.39 m |
| Connaught Place | D | 0 (raw 0) | 216.29 m | 0 (raw 0) | 213.34 m |
| DU North Campus | D | 0 (raw 0) | 219.92 m | 0 (raw 0) | 215.32 m |

Local minimum is on the smoothed grid. Some of the FABDEM cells counted at
Yamuna Bazar (8 of the window) and Raj Ghat (15) are inside the channel
mask and cannot score. Counting land cells only gives 31 and 37.

On FABDEM, 2 of the 3 Group A sites have ground below the observed peak
stage (1 of 3 on SRTM). Majnu ka Tilla still has none: its lowest cell is
211.68 m, 3.0 m above 208.66 m. That is 3.6 m lower than on SRTM but still
above a flat 208.66 m water surface. ITO, which the pre-registration puts
outside the model, is mostly below the peak stage on FABDEM.

## Calibration

Same rule as the primary: the one calibrated number is the peak excess
inflow of the same triangular hydrograph (48 h rise, 48 h fall, peak on
07-11), chosen so the modelled peak stage at the ORB cell is within
+/-0.10 m of 208.66 m. Same rain forcing, same Manning n, same solver.
Snapshots were saved every 6 h (the `run_once` default). The 12 h subset,
which is what `score_backtest.py` uses, gives the same stage and the same
site table in every trial.

Two rounds of 4 parallel trials, then one no-river run (peak_q = 0) as a
diagnostic, matching the one in the primary document. Every run is listed:

| Round | peak_q (m3/s) | ORB peak stage (m) | Error vs 208.66 m | Within +/-0.10 m | Group A | Group D false alarms |
|---|---|---|---|---|---|---|
| 3 (diagnostic) | 0 (no river) | 203.822 | -4.838 | no | 1/3 | 1 |
| 1 | 2,000 | 206.407 | -2.253 | no | 2/3 | 1 |
| 1 | 5,000 | 207.358 | -1.302 | no | 2/3 | 1 |
| 1 | 9,000 | 207.766 | -0.894 | no | 2/3 | 1 |
| 1 | 14,000 | 208.147 | -0.513 | no | 3/3 | 1 |
| 2 | 18,000 | 208.388 | -0.272 | no | 3/3 | 1 |
| 2 | 21,000 | 208.552 | -0.108 | no | 3/3 | 1 |
| 2 | **24,000** | **208.697** | **+0.037** | **yes** | 3/3 | 1 |
| 2 | 28,000 | 208.885 | +0.225 | no | 3/3 | 1 |

**Chosen: peak_q = 24,000 m3/s, ORB stage 208.697 m (+0.037 m).** It is the
only trial inside the tolerance. 21,000 misses the tolerance by 0.008 m.
No further trials were run. Stage is read at saved frames only: the ORB
depth at 24,000 is 4.21, 4.33 and 4.24 m at hours 114, 120 and 126, so
the true modelled peak can sit slightly above the sampled one (the
primary document has the same caveat). That could put 21,000 inside the
tolerance too. Site outcomes at 21,000 and 24,000 are identical.

The target was numerically reachable, so the run was not stopped. But the
inflow it takes is a finding in its own right: 24,000 m3/s is about 2.4
times the Hathnikund peak release, and about 8.3 times the 2,900 m3/s of
the SRTM calibration (6.9 times the 3,500 m3/s of the first SRTM run).
The bare-earth floodplain is lower and wider than the SRTM one, the grid has no embankments, bridges or barrages to hold
water up, and water leaves freely through the open downstream edge. The
model on this DEM conveys the flood too easily, and the calibration rule
makes up for that with more water. The peak_q is a tuning number that
compensates for missing structures, not an estimate of the real discharge.

Each FABDEM run with river inflow took 17 to 35 minutes of wall time
(about 127,000 to 150,000 solver steps, with other jobs sharing the CPU),
against roughly 3.5 minutes on SRTM, because the water is deeper and the
stable time step is smaller. The no-river run took about 3 minutes.

## Results (peak_q = 24,000 m3/s, ORB stage 208.697 m)

Same hit rule: any cell within 250 m (Chebyshev, 4 cells) reaching 0.30 m
or more at any saved time, excluding the OSM channel mask.
**Channel mask: 908 cells**, from `river.water_mask` (Overpass; two 504
timeouts, then success on the third try), cached to
`assets/dem/delhi_osm_channel_mask_150.npy`.

| Site | Group | Observed | Modelled | Max depth (m) | Match |
|---|---|---|---|---|---|
| Yamuna Bazar | A | flooded | flooded | 7.43 | YES |
| Kashmere Gate ISBT | A | flooded | flooded | 3.38 | YES |
| Majnu ka Tilla | A | flooded | flooded | 1.61 | YES |
| Red Fort (Ring Road) | B | flooded | dry | 0.22 | no |
| Civil Lines | B | flooded | dry | 0.02 | no |
| ITO | C | flooded (drain 12) | dry | 0.26 | no (expected, outside the model) |
| Raj Ghat | C | flooded (drain 12) | flooded | 0.88 | YES (river-fed in the peak envelope, see below) |
| Connaught Place | D | dry | **flooded** | 0.51 | **no, false alarm** |
| DU North Campus | D | dry | dry | 0.01 | YES |

**Headline: Group A 3/3 correct. Group D: 1/2 correct, one false alarm.**
Group B: 0/2. Group C: ITO dry, Raj Ghat flooded overland.

Notes on individual rows:

- **Yamuna Bazar, 7.43 m.** The deepest scoring cell has a bed of 201.61 m.
  It is a low riverbank cell that the OSM mask does not cover, so this
  depth is closer to a channel depth than to street flooding. 33 of the 73
  unmasked cells in the window are wet. This site also counts as flooded
  with **no river at all** (1.18 m, 4 cells, see the next section), so on
  FABDEM it is not a discriminating test.
- **Connaught Place, 0.51 m.** The depth is identical in all 9 runs, from
  no river to 28,000 m3/s, so it does not come from the river. It is rain
  pooling in a closed depression (bed 213.3 to 213.5 m) with no storm
  drains in the model: the same mechanism as the SRTM false alarm.
- **Red Fort, 0.22 m.** Also identical in all 9 runs, so it is rain
  ponding below the threshold, not river water. 4 cells in its window are
  below 208.66 m but the river does not reach them.
- **ITO** crosses the threshold only at 28,000 m3/s (0.39 m).

## What the hits are made of (evidence, not a scoring change)

The primary document added two checks after its run: a no-river run, and
connected components of depth >= 0.30 m. The same two were done here.
The connectivity check here uses the **peak-over-time depth grid** of each
trial, because per-frame grids were not saved. It is therefore weaker than
the per-frame check in the primary document: two cells can be joined in the
peak envelope without having been joined at the same moment.

| Site | No river (peak_q 0) | 2,000 | 9,000 | 24,000 (calibrated) | Wet scoring cells joined to the river-fed area at 24,000 |
|---|---|---|---|---|---|
| Yamuna Bazar | 1.18, flooded | 5.08 | 6.47 | 7.43 | 33 of 33 |
| Kashmere Gate ISBT | 0.23, dry | 1.07 | 2.41 | 3.38 | 13 of 13 |
| Majnu ka Tilla | 0.00, dry | 0.00 | 0.05 | 1.61 | 15 of 15 |
| Red Fort (Ring Road) | 0.22, dry | 0.22 | 0.22 | 0.22 | none wet |
| Civil Lines | 0.02, dry | 0.02 | 0.02 | 0.02 | none wet |
| ITO | 0.06, dry | 0.06 | 0.06 | 0.26 | none wet |
| Raj Ghat | 0.10, dry | 0.10 | 0.10 | 0.88 | 8 of 8 |
| Connaught Place | 0.51, flooded | 0.51 | 0.51 | 0.51 | 0 of 13 (isolated 13-cell pond, surface 213.85 m) |
| DU North Campus | 0.01, dry | 0.01 | 0.01 | 0.01 | none wet |

Values are maximum depth in metres over the unmasked cells in the window.
The river-fed area is the connected wet component that holds the inflow
cells, the ORB cell and most of the channel mask (7,671 cells at 24,000,
of which 683 are mask cells). 4- and 8-connectivity give the same answer.

What this shows:

- **Rain ponding is much smaller on FABDEM than on SRTM.** With no river,
  SRTM has 2.23 m at Kashmere Gate, 1.67 m at Red Fort, 2.69 m at Civil
  Lines and 2.06 m at Raj Ghat (figures from the primary document). FABDEM
  has 0.23, 0.22, 0.02 and 0.10 m. The closed depressions that fill with
  rain on SRTM are mostly absent on the bare-earth grid. That is why Group
  B drops from 2/2 to 0/2: the SRTM hits there were ponds, and FABDEM does
  not have the ponds.
- **Connaught Place is still a rain pond** on FABDEM: same 0.51 m with and
  without the river, never joined to the river-fed area.
- **Kashmere Gate ISBT is flooded by the river on FABDEM.** Dry (0.23 m)
  with no river, 1.07 m at 2,000 m3/s, and all its wet cells are joined to
  the river-fed area in every trial checked (2,000, 9,000, 14,000 and
  24,000). On SRTM the water there is an isolated rain pond 4.3 m above
  the river stage.
- **Yamuna Bazar counts as flooded even with no river** on FABDEM: 4
  unmasked cells with a bed near 201.6 m collect rain runoff to 1.18 m.
  With the river they are part of the river-fed area. The OSM mask does
  not cover all of the low channel-side cells on this DEM.
- With rain alone the FABDEM table scores Group A 1/3 (Yamuna Bazar), the
  same count as SRTM with rain alone (Kashmere Gate, per the primary
  document), but a different site.

## How much weight the 3/3 can carry

Not much, for two reasons that should be said out loud whenever the number
is quoted.

1. **It depends on an implausible inflow.** Majnu ka Tilla is dry at
   2,000, 5,000 and 9,000 m3/s and first floods at 14,000 m3/s, which is
   already above the Hathnikund peak release, and where the ORB stage is
   still 0.51 m short of the observed peak.
2. **It needs a water surface that is too steep.** The lowest ground near
   Majnu ka Tilla is 211.68 m. In the calibrated run the water surface
   there peaks at 213.42 m, about 4.7 m above the modelled ORB stage,
   across roughly 5 km of river. The pre-registration estimated about +1 m
   over that reach. Majnu ka Tilla is at row 139 of 150, 5 to 9 cells
   from where the model injects the inflow (rows 144 to 148), so this looks
   like water piling up near the inflow boundary at an oversized discharge.
   The hit is very likely right for the wrong reason.

What FABDEM does show without that caveat: the terrain-only check moves
Kashmere Gate ISBT from "no ground below the peak stage" (SRTM, 0 cells) to
"ground below the peak stage" (11 cells), and the river reaches Kashmere
Gate ISBT at every trial from 2,000 m3/s up. That is one more river-fed
Group A site than SRTM has, at every trial with river inflow, including
plausible ones.

## Comparison with the primary (SRTM) result

SRTM figures are as written in `BACKTEST_PREREG.md` when this was finished
on 2026-10-08. That file was revised by its owner while this run was in
progress: the pre-registered SRTM result is now the in-tolerance run at
peak_q = 2,900 m3/s (stage 208.648 m), and the earlier 3,500 m3/s run is
kept there for the record. Site outcomes are the same in both SRTM runs.

| | SRTM (primary, peak_q 2,900) | FABDEM (this second result, peak_q 24,000) |
|---|---|---|
| Calibrated peak_q | 2,900 m3/s | 24,000 m3/s |
| ORB stage | 208.648 m (-0.012 m, inside tolerance) | 208.697 m (+0.037 m, inside tolerance) |
| Frames, mask | every 6 h, 908 cells | every 6 h, the same 908 cells |
| Group A | 2/3 | 3/3 |
| Group D false alarms | 1 of 2 (Connaught Place) | 1 of 2 (Connaught Place) |
| Group B | 2/2 | 0/2 |
| Group C | ITO dry, Raj Ghat flooded | ITO dry, Raj Ghat flooded |
| All 9 rows matching observation | 6 of 9 | 5 of 9 |
| Group A with rain only (no river) | 1/3 (Kashmere Gate ISBT) | 1/3 (Yamuna Bazar) |
| Group A sites the river itself reaches | 1 (Yamuna Bazar) | 3 at 24,000; 2 at 2,000 to 9,000 (Yamuna Bazar, Kashmere Gate ISBT) |

Per site, max depth in metres:

| Site | Group | SRTM (2,900) | FABDEM (24,000) |
|---|---|---|---|
| Yamuna Bazar | A | flooded, 3.32 | flooded, 7.43 |
| Kashmere Gate ISBT | A | flooded, 2.23 (rain pond) | flooded, 3.38 (river) |
| Majnu ka Tilla | A | dry, 0.29 | flooded, 1.61 |
| Red Fort (Ring Road) | B | flooded, 1.67 (rain pond) | dry, 0.22 |
| Civil Lines | B | flooded, 2.69 (rain pond) | dry, 0.02 |
| ITO | C | dry, 0.05 | dry, 0.26 |
| Raj Ghat | C | flooded, 2.06 (rain pond) | flooded, 0.88 (river) |
| Connaught Place | D | flooded, 0.76 (rain pond) | flooded, 0.51 (rain pond) |
| DU North Campus | D | dry, 0.01 | dry, 0.01 |

The "rain pond" and "river" labels for SRTM are the primary document's own
findings. For FABDEM they come from the section above.

Plain reading:

- On the pre-registered headline (Group A, plus Group D false alarms),
  FABDEM scores one site higher: 3/3 against 2/3, with the same single
  false alarm. That gain is Majnu ka Tilla, and it carries the two caveats
  above. At a physically plausible inflow FABDEM gives the same 2/3.
- FABDEM is worse on Group B (0/2 against 2/2) and worse on the whole
  table (5 of 9 against 6 of 9). The SRTM Group B hits are rain ponds
  according to the primary document, and those ponds do not form on
  FABDEM. Neither DEM gets river water to Red Fort or Civil Lines.
- The false alarm is the same site with the same cause on both DEMs. A
  bare-earth DEM makes the pond shallower (0.51 m against 0.76 m) but does
  not remove it. It needs drainage in the model.
- The firmest difference is Kashmere Gate ISBT: a rain pond on SRTM, river
  flooding on FABDEM, at every trial with river inflow.
- Both calibrations are now inside the tolerance. The calibrated inflow is
  far less credible on FABDEM (24,000 m3/s) than on SRTM (2,900 m3/s).
- FABDEM does not make the model more believable overall. It removes most
  of the spurious ponding and lets the river reach one more real flood
  site, and it exposes that the model has nothing to hold the river up.

## What was not done or not verified

- No vertical datum correction (EGM2008, EGM96, Indian MSL). Not checked
  how large the offset is at Delhi.
- The SRTM run was not repeated here. Its numbers, including the no-river
  depths and the rain-pond findings, are quoted from `BACKTEST_PREREG.md`. Only the SRTM grid and its terrain-only counts
  were recomputed, and those match.
- No trial between 9,000 and 14,000 m3/s, so the exact inflow at which
  Majnu ka Tilla first floods is not known, only the bracket.
- No trial between 21,000 and 24,000 m3/s. One trial is inside the
  tolerance and it was taken.
- Only the bilinear grid was simulated. The block-mean grid was used for
  the terrain-only sensitivity only.
- Connectivity was checked on peak-over-time grids only, not per frame.
- The cause of the steep water surface near the inflow boundary is an
  inference from the numbers above. It was not tested with a separate run.
- Timing is not scored, as pre-registered. For the record, the modelled
  ORB peak falls on the snapshot at hour 120, the hydrograph peak.

## Files

- `fabdem_backtest.py`: build, mask, terrain, calib, score subcommands.
- `fabdem_inspect.py`: prints the GeoTIFF tags.
- `fabdem_connect.py`: the connectivity diagnostic.
- `assets/dem/N28E077_FABDEM_V1-2.tif`: the tile (CC BY-NC-SA 4.0).
- `assets/dem/delhi_fabdem_raw_150.npy`, `delhi_fabdem_smooth_150.npy`,
  `delhi_fabdem_blockmean_raw_150.npy`: the resampled grids.
- `assets/dem/delhi_srtm_raw_150.npy`, `delhi_srtm_smooth_150.npy`: the
  primary grid as loaded, for the comparison only.
- `assets/dem/delhi_osm_channel_mask_150.npy`: the 908-cell mask.
- `assets/dem/alignment.json`, `terrain_only.json`, `score_q*.json`,
  `calib_round1.log`, `calib_round2.log`, `calib_round3_q0.log`.
- `assets/dem/trials/trial_q*.npz`: per-trial peak-depth grids and the ORB
  depth series, so any trial can be re-scored without re-running it.

To reproduce: `python -u fabdem_backtest.py build`, then `mask`, `terrain`,
`calib 2000 5000 9000 14000`, `calib 18000 21000 24000 28000`, `calib 0`,
`score 24000`, and `python -u fabdem_connect.py 0 2000 9000 24000`.
