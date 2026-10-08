"""Score a calibrated backtest run against BACKTEST_PREREG.md's 9 sites.

Usage:
    python score_backtest.py PEAK_Q [--save-every-h 6] [--npz OUT.npz]
                                    [--mask-file MASK.npy]
    python score_backtest.py --fetch-mask MASK.npy

The channel mask comes from OSM via Overpass (river.water_mask), which
returns an EMPTY mask on any fetch failure. An empty mask changes which
cells count, so it is fetched (with retries) BEFORE the simulation and the
run aborts if it never arrives. --mask-file reuses a mask fetched earlier
with --fetch-mask, so parallel runs score against the identical mask.
"""

import math
import time

import numpy as np

import backtest_delhi as bt
import config
import river
import terrain

THRESH = 0.30
RADIUS_M = 250.0
MASK_EXPECTED_CELLS = 908      # Delhi frame, seen on earlier successful fetches


def fetch_mask(elevation, cell_size, tries=12, wait_s=20.0):
    """river.water_mask with retries; raises if it never returns cells."""
    for attempt in range(1, tries + 1):
        mask = river.water_mask(elevation, cell_size)
        n = int(mask.sum())
        if n > 0:
            print(f"[score] channel mask: {n} cells (attempt {attempt})",
                  flush=True)
            if abs(n - MASK_EXPECTED_CELLS) > 0.1 * MASK_EXPECTED_CELLS:
                print(f"[score] WARNING: mask size {n} is far from the "
                      f"expected ~{MASK_EXPECTED_CELLS}", flush=True)
            return mask
        print(f"[score] empty channel mask (attempt {attempt}/{tries}), "
              f"retrying in {wait_s:.0f}s", flush=True)
        time.sleep(wait_s)
    raise RuntimeError("channel mask is still empty after retries; refusing "
                       "to score without it")


def score(peak_q, save_every_h=6.0, npz_path=None, mask_file=None):
    elevation, cell_size, terrain_source, inflow, orb_rc = bt.setup()
    if mask_file:
        mask = np.load(mask_file).astype(bool)
        assert mask.shape == elevation.shape, "mask file / grid shape mismatch"
        print(f"[score] channel mask: {int(mask.sum())} cells "
              f"(loaded from {mask_file})", flush=True)
        if not mask.any():
            raise RuntimeError("mask file is empty")
    else:
        mask = fetch_mask(elevation, cell_size)

    times, depths = bt.run_once(peak_q, elevation, cell_size, inflow,
                                save_every_s=save_every_h * 3600.0)
    peak = np.maximum.reduce(depths)        # max depth over the whole run
    stage = float(elevation[orb_rc]) + max(float(d[orb_rc]) for d in depths)

    k = max(1, math.ceil(RADIUS_M / cell_size))

    print(f"\n[score] peak_q={peak_q:.0f} m3/s, {len(depths)} frames saved "
          f"every {save_every_h:g} h")
    print(f"[score] ORB calibration check: stage {stage:.3f} m "
          f"(target {bt.OBSERVED_ORB_M} m, {'OK' if abs(stage-bt.OBSERVED_ORB_M)<0.10 else 'OFF'})")
    print(f"[score] cell size {cell_size:.1f} m, search radius {k} cells, "
          f"channel mask {int(mask.sum())} cells\n")
    print(f"{'site':22s} {'group':6s} {'observed':9s} {'modelled':9s} "
          f"{'max depth':10s} {'match':6s}")
    rows_out = []
    for name, (lat, lon, group) in bt.SITES.items():
        rc = terrain.latlon_to_rc(lat, lon, *elevation.shape)
        observed = "flooded" if name in bt.OBSERVED_FLOODED else "dry"
        if rc is None:
            rows_out.append((name, group, observed, "N/A", None, "?"))
            continue
        r, c = rc
        window = peak[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        wmask = mask[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        window_land = window[~wmask] if wmask.any() else window
        maxd = float(window_land.max()) if window_land.size else float(window.max())
        modelled = "flooded" if maxd >= THRESH else "dry"
        match = "YES" if modelled == observed else "no"
        rows_out.append((name, group, observed, modelled, maxd, match))
        print(f"{name:22s} {group:6s} {observed:9s} {modelled:9s} "
              f"{maxd:10.3f} {match:6s}")

    groupA = [r for r in rows_out if r[1] == "A"]
    groupD = [r for r in rows_out if r[1] == "D"]
    hitsA = sum(1 for r in groupA if r[5] == "YES")
    falseD = sum(1 for r in groupD if r[3] == "flooded")
    print(f"\n[score] Group A (overbank, scored): {hitsA}/{len(groupA)} correct")
    print(f"[score] Group D (control, should stay dry): "
          f"{len(groupD) - falseD}/{len(groupD)} correct "
          f"({falseD} false alarm(s))", flush=True)

    if npz_path:
        save_run(npz_path, peak_q, times, depths, elevation, cell_size,
                 mask, inflow, orb_rc, stage, rows_out)
    return rows_out, stage


def save_run(path, peak_q, times, depths, elevation, cell_size, mask, inflow,
             orb_rc, stage, rows_out, extra=None):
    """Persist the scored run so a viewer can replay it without re-simulating.
    Grids are (rows, cols) with row 0 = south, like `elevation`.
    extra: optional dict of additional arrays to store (used by the
    post-hoc conditioned-DEM variant); None keeps the original key set."""
    rows, cols = elevation.shape
    hours = np.arange(bt.DURATION_H + 1, dtype=np.float64)
    inflow_mask = np.zeros((rows, cols), dtype=bool)
    if inflow:
        inflow_mask.flat[np.asarray(inflow["nodes"])] = True
    names = list(bt.SITES)
    site_rc = np.array([terrain.latlon_to_rc(bt.SITES[n][0], bt.SITES[n][1],
                                             rows, cols) for n in names])
    by_name = {r[0]: r for r in rows_out}
    np.savez_compressed(
        path,
        times=np.asarray(times, dtype=np.float64),           # seconds
        depths=np.stack(depths).astype(np.float32),          # (frames, R, C) m
        elevation=np.asarray(elevation, dtype=np.float32),   # m
        cell_size=np.float64(cell_size),                     # m
        peak_q=np.float64(peak_q),                           # m3/s, peak excess
        orb_stage_m=np.float64(stage),
        orb_observed_m=np.float64(bt.OBSERVED_ORB_M),
        orb_rc=np.asarray(orb_rc),
        hours=hours,                                         # 0..264
        rain_mm_hr=np.array([bt.rain_mm_hr_at(h * 3600.0) for h in hours]),
        river_q_m3s=np.array([bt.river_q_at(h * 3600.0, peak_q)
                              for h in hours]),
        rain_daily_mm=np.asarray(bt.RAIN_DAILY_MM, dtype=np.float64),
        rain_start_date=np.array("2023-07-06"),
        river_mask=mask.astype(bool),
        inflow_mask=inflow_mask,
        basin_lat=np.float64(config.BASIN_LAT),
        basin_lon=np.float64(config.BASIN_LON),
        site_names=np.array(names),
        site_groups=np.array([bt.SITES[n][2] for n in names]),
        site_latlon=np.array([bt.SITES[n][:2] for n in names]),
        site_rc=site_rc,
        site_observed=np.array([by_name[n][2] for n in names]),
        site_modelled=np.array([by_name[n][3] for n in names]),
        site_max_depth_m=np.array([by_name[n][4] for n in names]),
        flood_depth_m=np.float64(THRESH),
        radius_m=np.float64(RADIUS_M),
        **(extra or {}),
    )
    print(f"[score] saved {len(depths)} frames to {path}", flush=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("peak_q", nargs="?", type=float, default=4000.0)
    ap.add_argument("--save-every-h", type=float, default=6.0)
    ap.add_argument("--npz", default=None,
                    help="write the scored run (frames, forcing, mask) here")
    ap.add_argument("--mask-file", default=None,
                    help=".npy channel mask from an earlier --fetch-mask")
    ap.add_argument("--fetch-mask", default=None, metavar="OUT.npy",
                    help="only fetch the OSM channel mask and save it")
    a = ap.parse_args()

    if a.fetch_mask:
        elevation, cell_size, *_ = bt.setup()
        np.save(a.fetch_mask, fetch_mask(elevation, cell_size))
        print(f"[score] mask saved to {a.fetch_mask}")
    else:
        score(a.peak_q, save_every_h=a.save_every_h, npz_path=a.npz,
              mask_file=a.mask_file)
