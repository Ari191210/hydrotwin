"""Second, separately reported backtest of the July 2023 Yamuna flood in
Delhi on a bare-earth DEM (FABDEM V1-2), per the DEM section of
BACKTEST_PREREG.md. Same grid, same smoothing, same forcing, same hit rule
and same OSM channel mask as the primary (SRTM) run. Only the elevation
source differs. The primary pipeline is imported, never modified.

FABDEM V1-2 is CC BY-NC-SA 4.0 (non-commercial). Commercial use needs a
licence from Fathom.

Usage:
  python -u fabdem_backtest.py build          # resample + alignment check
  python -u fabdem_backtest.py mask           # fetch + cache OSM channel mask
  python -u fabdem_backtest.py terrain        # terrain-only check
  python -u fabdem_backtest.py calib Q1 Q2 .. # parallel trials (max 4)
  python -u fabdem_backtest.py score Q        # score a saved trial
"""

import json
import math
import os
import sys
import time

import numpy as np

import backtest_delhi as bt
import config
import river
import terrain

HERE = os.path.dirname(os.path.abspath(__file__))
DEM_DIR = os.path.join(HERE, "assets", "dem")
TIF = os.path.join(DEM_DIR, "N28E077_FABDEM_V1-2.tif")
RAW_NPY = os.path.join(DEM_DIR, "delhi_fabdem_raw_150.npy")
BLOCK_NPY = os.path.join(DEM_DIR, "delhi_fabdem_blockmean_raw_150.npy")
SMOOTH_NPY = os.path.join(DEM_DIR, "delhi_fabdem_smooth_150.npy")
SRTM_RAW_NPY = os.path.join(DEM_DIR, "delhi_srtm_raw_150.npy")
SRTM_SMOOTH_NPY = os.path.join(DEM_DIR, "delhi_srtm_smooth_150.npy")
MASK_NPY = os.path.join(DEM_DIR, "delhi_osm_channel_mask_150.npy")
TRIAL_DIR = os.path.join(DEM_DIR, "trials")

THRESH = 0.30
RADIUS_M = 250.0
TOL_M = 0.10
SAVE_EVERY_H = 6.0     # run_once default; 12 h subset also reported


# ---------------------------------------------------------------- grid ----
def cell_centres_latlon():
    """Lat/lon of every cell centre of the primary grid: the exact inverse
    of terrain.latlon_to_rc (same centre, same integer pixel origin, same
    zoom; row 0 = south)."""
    rows, cols, zoom = config.GRID_ROWS, config.GRID_COLS, config.TERRAIN_ZOOM
    cx, cy = terrain._mercator_px(config.BASIN_LAT, config.BASIN_LON, zoom)
    x0, y0 = int(cx - cols / 2), int(cy - rows / 2)
    return _px_to_latlon(x0, y0, rows, cols, zoom, 0.5, 0.5)


def _px_to_latlon(x0, y0, rows, cols, zoom, fx, fy):
    """Lat/lon grids at fractional offset (fx, fy) inside each cell, where
    fy is measured from the cell's NORTH edge (tile pixel convention)."""
    world = 256.0 * 2 ** zoom
    r = np.arange(rows)[:, None]
    c = np.arange(cols)[None, :]
    px = x0 + c + fx + 0.0 * r
    py = y0 + (rows - 1 - r) + fy + 0.0 * c
    lon = px / world * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * py / world))))
    return lat, lon


def read_fabdem():
    """Return (array, lat_of_row0_centre, lon_of_col0_centre, dlat, dlon,
    nodata) from the GeoTIFF's own tags."""
    import tifffile

    with tifffile.TiffFile(TIF) as tf:
        page = tf.pages[0]
        scale = page.tags["ModelPixelScaleTag"].value
        tie = page.tags["ModelTiepointTag"].value
        nodata = float(page.tags["GDAL_NODATA"].value) \
            if "GDAL_NODATA" in page.tags else None
        meta = tf.geotiff_metadata
        arr = page.asarray().astype(np.float64)
    assert tie[0] == 0.0 and tie[1] == 0.0, tie
    assert int(meta["GeographicTypeGeoKey"]) == 4326, meta
    raster_type = int(meta["GTRasterTypeGeoKey"])   # 1 = area, 2 = point
    lon0, lat0 = tie[3], tie[4]
    dlon, dlat = scale[0], scale[1]
    if raster_type == 1:        # tiepoint is the pixel's NW corner
        lon0 += dlon / 2.0
        lat0 -= dlat / 2.0
    return arr, lat0, lon0, dlat, dlon, nodata, raster_type


def sample_bilinear(arr, lat0, lon0, dlat, dlon, lat, lon):
    """Bilinear sample; arr row 0 = north (lat decreases with row). NaNs
    (nodata) are handled by a normalised weighted mean."""
    from scipy.ndimage import map_coordinates

    fi = (lat0 - lat) / dlat
    fj = (lon - lon0) / dlon
    if fi.min() < 0 or fj.min() < 0 or fi.max() > arr.shape[0] - 1 \
            or fj.max() > arr.shape[1] - 1:
        raise ValueError("grid extends outside the FABDEM tile")
    valid = np.isfinite(arr).astype(np.float64)
    filled = np.where(np.isfinite(arr), arr, 0.0)
    num = map_coordinates(filled, [fi, fj], order=1, mode="nearest")
    den = map_coordinates(valid, [fi, fj], order=1, mode="nearest")
    out = np.where(den > 1e-9, num / np.maximum(den, 1e-9), np.nan)
    return out, den


def build():
    config.set_case("delhi")
    rows, cols, zoom = config.GRID_ROWS, config.GRID_COLS, config.TERRAIN_ZOOM
    cell = terrain.cell_size_m(zoom=zoom)
    arr, lat0, lon0, dlat, dlon, nodata, raster_type = read_fabdem()
    print(f"[fabdem] tile {arr.shape}, pixel(0,0) centre lat {lat0} lon {lon0}, "
          f"dlat {dlat:.10f} dlon {dlon:.10f}, raster_type {raster_type} "
          f"(1=area 2=point), nodata {nodata}")
    n_nodata = int((arr == nodata).sum()) if nodata is not None else 0
    n_nodata += int((~np.isfinite(arr)).sum())
    print(f"[fabdem] nodata pixels in tile: {n_nodata}")
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)

    # known-value sanity checks straight off the tile (nearest pixel)
    for name, la, lo in (("Yamuna near ORB", 28.66, 77.25),
                         ("Yamuna channel (ORB coords)", *bt.ORB_LATLON),
                         ("Delhi Ridge (Kamla Nehru Ridge)", 28.6870, 77.2140),
                         ("Central Ridge (Buddha Jayanti)", 28.6100, 77.1800)):
        i, j = int(round((lat0 - la) / dlat)), int(round((lo - lon0) / dlon))
        print(f"[fabdem] sanity {name} ({la}, {lo}) -> pixel ({i},{j}) "
              f"= {arr[i, j]:.2f} m")

    lat, lon = cell_centres_latlon()
    # round-trip: every cell centre must map back to its own (row, col)
    bad = 0
    for r in range(rows):
        for c in range(cols):
            if terrain.latlon_to_rc(lat[r, c], lon[r, c], rows, cols) != (r, c):
                bad += 1
    print(f"[fabdem] round-trip latlon_to_rc mismatches: {bad} of {rows * cols}")
    print(f"[fabdem] grid extent lat {lat.min():.5f}..{lat.max():.5f} "
          f"lon {lon.min():.5f}..{lon.max():.5f}; cell {cell:.2f} m")

    raw, den = sample_bilinear(arr, lat0, lon0, dlat, dlon, lat, lon)
    print(f"[fabdem] cells with any nodata weight: {int((den < 0.999).sum())}, "
          f"cells fully nodata: {int(np.isnan(raw).sum())}")
    if np.isnan(raw).any():
        raw = np.where(np.isnan(raw), np.nanmedian(raw), raw)

    # sensitivity only (NOT simulated): mean of a 4x4 lattice of bilinear
    # samples inside each cell, approximating an area average
    zoomv = zoom
    cx, cy = terrain._mercator_px(config.BASIN_LAT, config.BASIN_LON, zoomv)
    x0, y0 = int(cx - cols / 2), int(cy - rows / 2)
    acc = np.zeros((rows, cols))
    offs = (0.125, 0.375, 0.625, 0.875)
    for fy in offs:
        for fx in offs:
            la, lo = _px_to_latlon(x0, y0, rows, cols, zoomv, fx, fy)
            s, _ = sample_bilinear(arr, lat0, lon0, dlat, dlon, la, lo)
            acc += s
    block = acc / 16.0

    terrain._sanity_check(raw)
    smooth = terrain._fill_noise_pits(raw)
    np.save(RAW_NPY, raw)
    np.save(BLOCK_NPY, block)
    np.save(SMOOTH_NPY, smooth)
    print(f"[fabdem] raw bilinear grid {raw.min():.2f}..{raw.max():.2f} m; "
          f"smoothed {smooth.min():.2f}..{smooth.max():.2f} m")

    # primary DEM for the alignment check (not modified, just loaded)
    srtm_raw, cell2 = terrain._from_aws_terrain_tiles()
    srtm_smooth, cell3, label = terrain.load_terrain()
    assert abs(cell2 - cell) < 1e-9 and abs(cell3 - cell) < 1e-9
    assert np.allclose(terrain._fill_noise_pits(srtm_raw), srtm_smooth)
    np.save(SRTM_RAW_NPY, srtm_raw)
    np.save(SRTM_SMOOTH_NPY, srtm_smooth)
    alignment(raw, smooth, srtm_raw, srtm_smooth)


def alignment(raw, smooth, srtm_raw, srtm_smooth):
    def corr(a, b):
        return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])

    out = {}
    for tag, f, s in (("raw", raw, srtm_raw), ("smoothed", smooth, srtm_smooth)):
        d = f - s
        out[tag] = dict(pearson=corr(f, s), mean_diff=float(d.mean()),
                        median_diff=float(np.median(d)), std_diff=float(d.std()),
                        p05=float(np.percentile(d, 5)),
                        p95=float(np.percentile(d, 95)))
        print(f"[align] {tag}: Pearson r={out[tag]['pearson']:.4f}  "
              f"FABDEM-SRTM mean {d.mean():+.2f} m, median {np.median(d):+.2f} m, "
              f"std {d.std():.2f} m, p05 {out[tag]['p05']:+.2f}, "
              f"p95 {out[tag]['p95']:+.2f}")

    # shift test: correlation of detrended (high-pass) fields is maximal at
    # zero offset if the grids are co-registered
    from scipy.ndimage import gaussian_filter
    hp_f = raw - gaussian_filter(raw, 8)
    hp_s = srtm_raw - gaussian_filter(srtm_raw, 8)
    best, table = None, {}
    for dr in range(-3, 4):
        for dc in range(-3, 4):
            a = hp_f[3 + dr:147 + dr, 3 + dc:147 + dc]
            b = hp_s[3:147, 3:147]
            v = corr(a, b)
            table[(dr, dc)] = v
            if best is None or v > best[0]:
                best = (v, dr, dc)
    print(f"[align] high-pass (sigma 8 removed) correlation at zero shift "
          f"{table[(0, 0)]:.4f}; best over +/-3 cells = {best[0]:.4f} at "
          f"(drow {best[1]}, dcol {best[2]})")
    out["highpass_zero_shift"] = table[(0, 0)]
    out["highpass_best"] = best

    # river in the same cells: per-row argmin column within the OSM mask rows
    if os.path.exists(MASK_NPY):
        mask = np.load(MASK_NPY)
        for tag, g in (("FABDEM smoothed", smooth), ("SRTM smoothed", srtm_smooth)):
            print(f"[align] {tag}: mean elev inside OSM mask "
                  f"{g[mask].mean():.2f} m, outside {g[~mask].mean():.2f} m")
        out["mask_in_fabdem"] = float(smooth[mask].mean())
        out["mask_out_fabdem"] = float(smooth[~mask].mean())
        out["mask_in_srtm"] = float(srtm_smooth[mask].mean())
        out["mask_out_srtm"] = float(srtm_smooth[~mask].mean())
        d = smooth - srtm_smooth
        print(f"[align] FABDEM-SRTM inside mask: mean {d[mask].mean():+.2f}, "
              f"outside mask: mean {d[~mask].mean():+.2f}, "
              f"median {np.median(d[~mask]):+.2f}")
        out["diff_in_mask"] = float(d[mask].mean())
        out["diff_out_mask"] = float(d[~mask].mean())
        # thalweg column per row, restricted to rows where the mask is present
        rows_with = np.where(mask.any(axis=1))[0]
        dcol = []
        for r in rows_with:
            cols_m = np.where(mask[r])[0]
            lo, hi = max(0, cols_m.min() - 3), min(mask.shape[1], cols_m.max() + 4)
            dcol.append((lo + int(np.argmin(smooth[r, lo:hi])))
                        - (lo + int(np.argmin(srtm_smooth[r, lo:hi]))))
        dcol = np.array(dcol)
        print(f"[align] thalweg column (argmin near the OSM channel) FABDEM "
              f"minus SRTM over {len(dcol)} rows: median {np.median(dcol):+.0f}, "
              f"mean abs {np.abs(dcol).mean():.2f} cells, "
              f"within 2 cells in {int((np.abs(dcol) <= 2).sum())} rows")
        out["thalweg_rows"] = int(len(dcol))
        out["thalweg_median_dcol"] = float(np.median(dcol))
        out["thalweg_mean_abs_dcol"] = float(np.abs(dcol).mean())
        out["thalweg_within2"] = int((np.abs(dcol) <= 2).sum())
    with open(os.path.join(DEM_DIR, "alignment.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    return out


# ---------------------------------------------------------------- mask ----
def fetch_mask(max_tries=30):
    config.set_case("delhi")
    elev = np.load(SMOOTH_NPY)
    cell = terrain.cell_size_m(zoom=config.TERRAIN_ZOOM)
    for i in range(max_tries):
        m = river.water_mask(elev, cell)
        if m.any():
            np.save(MASK_NPY, m)
            print(f"[mask] saved {int(m.sum())} cells after {i + 1} tries")
            return m
        time.sleep(8)
    raise SystemExit("[mask] Overpass never returned a non-empty mask")


# ------------------------------------------------------- terrain-only ----
def terrain_only():
    config.set_case("delhi")
    cell = terrain.cell_size_m(zoom=config.TERRAIN_ZOOM)
    k = max(1, math.ceil(RADIUS_M / cell))
    grids = {"fab_smooth": np.load(SMOOTH_NPY), "fab_raw": np.load(RAW_NPY),
             "fab_block": np.load(BLOCK_NPY),
             "srtm_smooth": np.load(SRTM_SMOOTH_NPY),
             "srtm_raw": np.load(SRTM_RAW_NPY)}
    grids["fab_block_smooth"] = terrain._fill_noise_pits(grids["fab_block"])
    mask = np.load(MASK_NPY) if os.path.exists(MASK_NPY) else None
    print(f"[terrain-only] cell {cell:.2f} m, k={k}, window {(2*k+1)**2} cells, "
          f"threshold {bt.OBSERVED_ORB_M} m")
    out = {}
    for name, (lat, lon, group) in bt.SITES.items():
        r, c = terrain.latlon_to_rc(lat, lon, *grids["fab_smooth"].shape)
        row = {"group": group, "rc": (r, c)}
        for tag, g in grids.items():
            w = g[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            row[tag + "_n"] = int((w < bt.OBSERVED_ORB_M).sum())
            row[tag + "_min"] = float(w.min())
            row[tag + "_site"] = float(g[r, c])
            row[tag + "_size"] = int(w.size)
        if mask is not None:
            wm = mask[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            w = grids["fab_smooth"][max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            row["mask_cells"] = int(wm.sum())
            row["fab_smooth_n_land"] = int(((w < bt.OBSERVED_ORB_M) & ~wm).sum())
            ws = grids["srtm_smooth"][max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            row["srtm_smooth_n_land"] = int(((ws < bt.OBSERVED_ORB_M) & ~wm).sum())
        out[name] = row
        print(f"{name:22s} {group} rc={r},{c}  "
              f"FAB smooth n={row['fab_smooth_n']:2d} min={row['fab_smooth_min']:.2f} "
              f"site={row['fab_smooth_site']:.2f} | raw n={row['fab_raw_n']:2d} "
              f"min={row['fab_raw_min']:.2f} | block-smooth n="
              f"{row['fab_block_smooth_n']:2d} min={row['fab_block_smooth_min']:.2f} || "
              f"SRTM smooth n={row['srtm_smooth_n']:2d} min={row['srtm_smooth_min']:.2f} "
              f"site={row['srtm_smooth_site']:.2f} | raw n={row['srtm_raw_n']:2d} "
              f"min={row['srtm_raw_min']:.2f} | mask cells in window "
              f"{row.get('mask_cells')} land<thr FAB {row.get('fab_smooth_n_land')} "
              f"SRTM {row.get('srtm_smooth_n_land')}")
    with open(os.path.join(DEM_DIR, "terrain_only.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


# -------------------------------------------------------------- trials ----
def fab_setup():
    config.set_case("delhi")
    elevation = np.load(SMOOTH_NPY)
    cell = terrain.cell_size_m(zoom=config.TERRAIN_ZOOM)
    inflow = river.find_inflow(elevation, cell)
    orb_rc = terrain.latlon_to_rc(*bt.ORB_LATLON, *elevation.shape)
    return elevation, cell, inflow, orb_rc


def trial_path(peak_q):
    return os.path.join(TRIAL_DIR, f"trial_q{peak_q:.0f}.npz")


def trial(peak_q):
    """Importable worker (Windows spawn): one full 11-day run on FABDEM.
    Saves every snapshot's ORB depth, the 6 h and 12 h peak-depth grids."""
    peak_q = float(peak_q)
    os.makedirs(TRIAL_DIR, exist_ok=True)
    t0 = time.time()
    elevation, cell, inflow, orb_rc = fab_setup()
    times, depths = bt.run_once(peak_q, elevation, cell, inflow,
                                save_every_s=SAVE_EVERY_H * 3600.0)
    times = np.array(times)
    orb_depth = np.array([float(d[orb_rc]) for d in depths])
    peak6 = np.maximum.reduce(depths)
    # 12 h cadence subset, reproducing run_simulation's save rule
    keep, next_save = [], 0.0
    for i, t in enumerate(times):
        if t >= next_save or i == len(times) - 1:
            keep.append(i)
            next_save = t + 12 * 3600.0
    peak12 = np.maximum.reduce([depths[i] for i in keep])
    stage6 = float(elevation[orb_rc]) + float(orb_depth.max())
    stage12 = float(elevation[orb_rc]) + float(orb_depth[keep].max())
    np.savez_compressed(trial_path(peak_q), peak_q=peak_q, times=times,
                        orb_depth=orb_depth, peak6=peak6, peak12=peak12,
                        keep12=np.array(keep), stage6=stage6, stage12=stage12,
                        orb_rc=np.array(orb_rc), orb_bed=float(elevation[orb_rc]),
                        inflow_rc=np.array(inflow["rc"]),
                        inflow_bed=inflow["bed_m"], inflow_width=inflow["width_m"],
                        inflow_cells=len(inflow["nodes"]),
                        wall_s=time.time() - t0)
    return peak_q, stage6, stage12, time.time() - t0


def calibrate(qs):
    from concurrent.futures import ProcessPoolExecutor

    elevation, cell, inflow, orb_rc = fab_setup()
    bed = float(elevation[orb_rc])
    print(f"[calib] ORB cell {orb_rc} bed {bed:.3f} m on FABDEM, target "
          f"{bt.OBSERVED_ORB_M} m, needs depth {bt.OBSERVED_ORB_M - bed:.3f} m")
    if bed >= bt.OBSERVED_ORB_M - 0.0:
        raise SystemExit("[calib] ORB bed is at or above the target stage: "
                         "target unreachable, stopping")
    with ProcessPoolExecutor(max_workers=min(4, len(qs))) as ex:
        for q, s6, s12, wall in ex.map(trial, qs):
            ok = "WITHIN" if abs(s6 - bt.OBSERVED_ORB_M) <= TOL_M else "outside"
            print(f"[calib] peak_q={q:.0f}  ORB stage (6h saves)={s6:.3f} m "
                  f"({s6 - bt.OBSERVED_ORB_M:+.3f}, {ok} +/-{TOL_M})  "
                  f"(12h saves {s12:.3f})  wall {wall:.0f}s", flush=True)


# --------------------------------------------------------------- score ----
def score(peak_q):
    config.set_case("delhi")
    elevation = np.load(SMOOTH_NPY)
    cell = terrain.cell_size_m(zoom=config.TERRAIN_ZOOM)
    mask = np.load(MASK_NPY)
    z = np.load(trial_path(float(peak_q)))
    k = max(1, math.ceil(RADIUS_M / cell))
    print(f"[score] FABDEM, peak_q={float(peak_q):.0f}, ORB stage "
          f"{float(z['stage6']):.3f} m (6h saves), {float(z['stage12']):.3f} m "
          f"(12h saves); mask {int(mask.sum())} cells; cell {cell:.2f} m; k={k}")
    result = {"peak_q": float(peak_q), "stage6": float(z["stage6"]),
              "stage12": float(z["stage12"]), "mask_cells": int(mask.sum()),
              "sites": {}}
    for cadence in ("peak6", "peak12"):
        peak = z[cadence]
        print(f"\n--- {cadence} ---")
        hitsA = falseD = 0
        for name, (lat, lon, group) in bt.SITES.items():
            r, c = terrain.latlon_to_rc(lat, lon, *elevation.shape)
            window = peak[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            wmask = mask[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
            land = window[~wmask] if wmask.any() else window
            maxd = float(land.max()) if land.size else float(window.max())
            n_wet = int((land >= THRESH).sum())
            observed = "flooded" if name in bt.OBSERVED_FLOODED else "dry"
            modelled = "flooded" if maxd >= THRESH else "dry"
            match = "YES" if modelled == observed else "no"
            hitsA += group == "A" and match == "YES"
            falseD += group == "D" and modelled == "flooded"
            result["sites"].setdefault(name, {})[cadence] = dict(
                group=group, observed=observed, modelled=modelled,
                max_depth=maxd, match=match, wet_cells=n_wet,
                land_cells=int(land.size), unmasked_max=float(window.max()))
            print(f"{name:22s} {group} {observed:8s} {modelled:8s} "
                  f"{maxd:6.2f} {match:4s} wet land cells {n_wet}/{land.size}")
        print(f"Group A {hitsA}/3; Group D false alarms {falseD}/2")
        result[cadence + "_A"] = int(hitsA)
        result[cadence + "_D_false"] = int(falseD)
    with open(os.path.join(DEM_DIR, f"score_q{float(peak_q):.0f}.json"), "w") as fh:
        json.dump(result, fh, indent=1)
    return result


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build":
        build()
    elif cmd == "mask":
        fetch_mask()
    elif cmd == "terrain":
        terrain_only()
    elif cmd == "calib":
        calibrate([float(x) for x in sys.argv[2:]])
    elif cmd == "score":
        score(sys.argv[2])
    else:
        print(__doc__)
