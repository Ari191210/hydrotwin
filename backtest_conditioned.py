"""POST-HOC variant of the July 2023 Delhi backtest: same rules, same rain,
same hydrograph shape, same dry start, but on the channel-conditioned DEM
the live pipeline now uses (backtest_delhi.setup(conditioned=True)).

NOT pre-registered: BACKTEST_PREREG.md said the DEM would be unchanged. The
pre-registered result (raw DEM, peak_q=2900) stands as recorded there.

    python backtest_conditioned.py trials Q1 Q2 ...   # max 4 in parallel
    python backtest_conditioned.py report Q [--npz OUT.npz]

`trials` saves every run's 6 h frames under RUN_DIR, so the calibrated run
is scored from the frames of its own calibration trial (no rerun), and
peak_q=0 is the rain-only control. `report` needs the Q run and the 0 run.
"""

import json
import math
import os
import sys

import numpy as np

import backtest_delhi as bt

_HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.environ.get(
    "BT_COND_RUN_DIR", os.path.join(_HERE, "outputs", "backtest_conditioned"))
SAVE_EVERY_H = 6.0
MAX_WORKERS = 4
THRESH = 0.30
RADIUS_M = 250.0


def run_path(peak_q):
    return os.path.join(RUN_DIR, f"q{peak_q:.0f}.npz")


def trial(peak_q):
    """One 11-day run on the conditioned DEM; frames kept on disk.
    Returns (peak_q, ORB stage over the saved frames)."""
    elevation, cell_size, terrain_source, inflow, orb_rc = bt.setup(
        conditioned=True)
    times, depths = bt.run_once(peak_q, elevation, cell_size, inflow,
                                save_every_s=SAVE_EVERY_H * 3600.0)
    stage = bt.orb_stage(depths, elevation, orb_rc)
    os.makedirs(RUN_DIR, exist_ok=True)
    np.savez_compressed(run_path(peak_q), times=np.asarray(times),
                        depths=np.stack(depths).astype(np.float32),
                        stage=np.float64(stage), peak_q=np.float64(peak_q))
    with open(os.path.join(RUN_DIR, "trials.log"), "a",
              encoding="utf-8") as f:
        f.write(f"{peak_q:.0f}\t{stage:.4f}\n")
    return peak_q, stage


def masks(elevation, cell_size, inflow, peak_q):
    """(osm, inflow_mask, footprint, footprint_info, full_exclusion), built
    with the live pipeline's own functions and caches."""
    import riverstate
    import scenarios

    osm = scenarios.fetch_water_mask(elevation, cell_size)
    footprint, info = riverstate.bankfull_footprint(elevation, cell_size,
                                                    inflow, None)
    if footprint is None:
        raise RuntimeError("no cached bankfull footprint for this DEM")
    inflow_mask = np.zeros(elevation.shape, bool)
    inflow_mask.flat[np.asarray(inflow["nodes"])] = True
    # q_m3s only switches the inflow cells on; any non-zero value does it
    full = scenarios.exclude_mask(osm, elevation.shape, inflow,
                                  max(peak_q, 1.0), footprint)
    return osm, inflow_mask, footprint, info, full


def site_window(rc, k, shape):
    r, c = rc
    return (slice(max(0, r - k), min(shape[0], r + k + 1)),
            slice(max(0, c - k), min(shape[1], c + k + 1)))


def score(peak, mask, elevation, cell_size, strict):
    """Per-site (name, group, observed, modelled, max depth, match).
    strict=False is score_backtest.score's window logic copied exactly,
    including its fallback to the unmasked window when every cell is
    masked. strict=True (not pre-registered) reports such a site as
    'all excluded' instead of counting excluded water."""
    import terrain

    k = max(1, math.ceil(RADIUS_M / cell_size))
    rows = []
    for name, (lat, lon, group) in bt.SITES.items():
        rc = terrain.latlon_to_rc(lat, lon, *elevation.shape)
        observed = "flooded" if name in bt.OBSERVED_FLOODED else "dry"
        r, c = rc
        window = peak[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        wmask = mask[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1]
        window_land = window[~wmask] if wmask.any() else window
        if strict and not window_land.size:
            rows.append((name, group, observed, "all excluded", None, "n/a"))
            continue
        maxd = float(window_land.max()) if window_land.size \
            else float(window.max())
        modelled = "flooded" if maxd >= THRESH else "dry"
        rows.append((name, group, observed, modelled, maxd,
                     "YES" if modelled == observed else "no"))
    return rows


def connectivity(depths, elevation, cell_size, osm, inflow_mask, name,
                 structure):
    """Components of depth >= THRESH at the site's peak frame (the frame
    where its windowed land maximum, OSM mask excluded, is largest)."""
    import terrain
    from scipy import ndimage

    k = max(1, math.ceil(RADIUS_M / cell_size))
    lat, lon, _ = bt.SITES[name]
    rc = terrain.latlon_to_rc(lat, lon, *elevation.shape)
    win = site_window(rc, k, elevation.shape)
    land = ~osm[win]
    series = [float(d[win][land].max()) for d in depths]
    fi = int(np.argmax(series))
    out = {"peak_frame": fi, "comps": []}

    def comps_at(frame):
        wet = depths[frame] >= THRESH
        lab, _ = ndimage.label(wet, structure=structure)
        ids = np.unique(lab[win][land & wet[win]])
        return wet, lab, [int(i) for i in ids if i]

    wet, lab, ids = comps_at(fi)
    for i in ids:
        comp = lab == i
        site_cells = np.zeros_like(comp)
        site_cells[win] = comp[win] & land
        wse = (elevation + depths[fi])[site_cells]
        out["comps"].append({
            "cells": int(comp.sum()),
            "site_cells": int(site_cells.sum()),
            "inflow_cells": int((comp & inflow_mask).sum()),
            "osm_cells": int((comp & osm).sum()),
            "site_max_depth": float(depths[fi][site_cells].max()),
            "wse_min": float(wse.min()), "wse_max": float(wse.max()),
        })
    # any frame at all: is a wet site cell ever in a component that holds
    # inflow cells / channel-mask cells?
    ever_inflow, ever_osm = [], []
    for f in range(len(depths)):
        w, l, idf = comps_at(f)
        for i in idf:
            comp = l == i
            if (comp & inflow_mask).any():
                ever_inflow.append(f)
            if (comp & osm).any():
                ever_osm.append(f)
    out["frames_with_inflow_link"] = sorted(set(ever_inflow))
    out["frames_with_osm_link"] = sorted(set(ever_osm))
    return out


def report(peak_q, npz_path=None):
    import score_backtest as sb
    import terrain

    elevation, cell_size, terrain_source, inflow, orb_rc = bt.setup(
        conditioned=True)
    raw = terrain.load_terrain()[0]
    osm, inflow_mask, footprint, fp_info, full = masks(
        elevation, cell_size, inflow, peak_q)
    print(f"[cond] terrain: {terrain_source}")
    print(f"[cond] inflow: rc={inflow['rc']} nodes={inflow['nodes']} "
          f"closed={inflow['closed']}")
    print(f"[cond] ORB cell {orb_rc}: raw bed {raw[orb_rc]:.3f} m, "
          f"conditioned bed {elevation[orb_rc]:.3f} m; in OSM mask "
          f"{bool(osm[orb_rc])}, in footprint {bool(footprint[orb_rc])}")
    print(f"[cond] masks: OSM {int(osm.sum())}, inflow "
          f"{int(inflow_mask.sum())}, bankfull footprint "
          f"{int(footprint.sum())} (q={fp_info['q_m3s']} m3/s, steady "
          f"{fp_info['converged']} after {fp_info['hours']} h), full "
          f"exclusion {int(full.sum())}; footprint outside OSM "
          f"{int((footprint & ~osm).sum())}")

    z = np.load(run_path(peak_q))
    z0 = np.load(run_path(0.0))
    times, depths = list(z["times"]), list(z["depths"].astype(np.float64))
    depths0 = list(z0["depths"].astype(np.float64))
    stage = float(z["stage"])
    orb_series = [float(d[orb_rc]) for d in depths]
    print(f"[cond] peak_q={peak_q:.0f}: ORB stage {stage:.3f} m (target "
          f"{bt.OBSERVED_ORB_M}, error {stage - bt.OBSERVED_ORB_M:+.3f}); "
          f"peak frame t={times[int(np.argmax(orb_series))] / 3600:.0f} h; "
          f"rain-only ORB stage {float(z0['stage']):.3f} m")

    peak = np.maximum.reduce(depths)
    peak0 = np.maximum.reduce(depths0)
    k = max(1, math.ceil(RADIUS_M / cell_size))
    res = {"peak_q": peak_q, "stage": stage, "k": k,
           "cell_size": float(cell_size), "frames": len(depths),
           "mask_cells": {"osm": int(osm.sum()),
                          "inflow": int(inflow_mask.sum()),
                          "footprint": int(footprint.sum()),
                          "full": int(full.sum())},
           "sites": {}}
    tabs = {
        "pre_osm": score(peak, osm, elevation, cell_size, False),
        "full": score(peak, full, elevation, cell_size, True),
        "rain_osm": score(peak0, osm, elevation, cell_size, False),
        "rain_full": score(peak0, full, elevation, cell_size, True),
    }
    for key, rows in tabs.items():
        print(f"\n[cond] table {key}")
        for r in rows:
            d = "   n/a" if r[4] is None else f"{r[4]:6.3f}"
            print(f"  {r[0]:22s} {r[1]} obs={r[2]:8s} mod={r[3]:12s} "
                  f"{d}  {r[5]}")
            res["sites"].setdefault(r[0], {})[key] = list(r[3:])
        a = [r for r in rows if r[1] == "A"]
        dd = [r for r in rows if r[1] == "D"]
        print(f"  Group A {sum(r[5] == 'YES' for r in a)}/3 correct, "
              f"Group D false alarms {sum(r[3] == 'flooded' for r in dd)}/2")

    # window composition per site
    print("\n[cond] window cells per site (of (2k+1)^2): OSM-masked, "
          "fully excluded")
    for name, (lat, lon, _) in bt.SITES.items():
        rc = terrain.latlon_to_rc(lat, lon, *elevation.shape)
        win = site_window(rc, k, elevation.shape)
        res["sites"][name]["window"] = [int(osm[win].size),
                                        int(osm[win].sum()),
                                        int(full[win].sum())]
        res["sites"][name]["site_bed"] = [float(raw[rc]), float(elevation[rc])]
        print(f"  {name:22s} {osm[win].size} cells, OSM {int(osm[win].sum())},"
              f" full {int(full[win].sum())}")

    print("\n[cond] connectivity (depth >= 0.30 m), river run and rain-only")
    for name in bt.SITES:
        for label, dd in (("river", depths), ("rain", depths0)):
            for cname, st in (("4", None), ("8", np.ones((3, 3)))):
                c = connectivity(dd, elevation, cell_size, osm, inflow_mask,
                                 name, st)
                res["sites"][name][f"conn_{label}_{cname}"] = c
                fl = c["frames_with_inflow_link"]
                fo = c["frames_with_osm_link"]
                print(f"  {name:22s} {label:5s} conn{cname} frame "
                      f"{c['peak_frame']} (t={times[c['peak_frame']]/3600:.0f}"
                      f" h): " + ("no wet land cells" if not c["comps"] else
                                  "; ".join(
                          f"{m['cells']} cells (site {m['site_cells']}, "
                          f"inflow {m['inflow_cells']}, osm {m['osm_cells']}, "
                          f"depth {m['site_max_depth']:.2f}, wse "
                          f"{m['wse_min']:.2f}-{m['wse_max']:.2f})"
                          for m in c["comps"]))
                      + f" | frames linked to inflow: {len(fl)}"
                      + (f" (first t={times[fl[0]]/3600:.0f} h)" if fl else "")
                      + f", to OSM channel: {len(fo)}"
                      + (f" (first t={times[fo[0]]/3600:.0f} h)" if fo else ""))

    os.makedirs(RUN_DIR, exist_ok=True)
    with open(os.path.join(RUN_DIR, f"report_q{peak_q:.0f}.json"), "w",
              encoding="utf-8") as f:
        json.dump(res, f, indent=1)

    if npz_path:
        names = list(bt.SITES)
        by_full = {r[0]: r for r in tabs["full"]}
        by_rain = {r[0]: r for r in tabs["rain_osm"]}
        extra = {
            "dem_conditioned": np.bool_(True),
            "dem_note": np.array(
                "POST-HOC variant, not pre-registered: elevation is the "
                "pipeline DEM with the river channel conditioned "
                "(river.condition_channel); elevation_raw is the "
                "pre-registered DEM. " + terrain_source),
            "terrain_source": np.array(terrain_source),
            "elevation_raw": np.asarray(raw, dtype=np.float32),
            "bankfull_mask": footprint.astype(bool),
            "bankfull_q_m3s": np.float64(fp_info["q_m3s"]),
            "exclude_mask_full": full.astype(bool),
            # second, NOT pre-registered scoring column (full exclusion)
            "site_modelled_full_exclusion": np.array(
                [by_full[n][3] for n in names]),
            "site_max_depth_full_exclusion_m": np.array(
                [np.nan if by_full[n][4] is None else by_full[n][4]
                 for n in names], dtype=np.float64),
            # rain-only control (peak_q = 0), pre-registered OSM mask
            "site_max_depth_rain_only_m": np.array(
                [by_rain[n][4] for n in names], dtype=np.float64),
            "orb_stage_rain_only_m": np.float64(float(z0["stage"])),
        }
        sb.save_run(npz_path, peak_q, times, depths, elevation, cell_size,
                    osm, inflow, orb_rc, stage, tabs["pre_osm"], extra=extra)
    return res


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "trials":
        from concurrent.futures import ProcessPoolExecutor

        qs = [float(a) for a in args]
        with ProcessPoolExecutor(max_workers=min(MAX_WORKERS,
                                                 len(qs))) as ex:
            for q, stage in ex.map(trial, qs):
                print(f"TRIAL peak_q={q:.0f}  ORB stage={stage:.3f} m  "
                      f"error={stage - bt.OBSERVED_ORB_M:+.3f} m  "
                      f"{'IN' if abs(stage - bt.OBSERVED_ORB_M) <= 0.10 else 'out'}",
                      flush=True)
    elif cmd == "report":
        npz = None
        if "--npz" in args:
            i = args.index("--npz")
            npz = args[i + 1]
            del args[i:i + 2]
        report(float(args[0]), npz)
    else:
        sys.exit(__doc__)
