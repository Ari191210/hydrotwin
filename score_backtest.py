"""Score a calibrated backtest run against BACKTEST_PREREG.md's 9 sites."""

import math

import numpy as np

import backtest_delhi as bt
import config
import river
import terrain

THRESH = 0.30
RADIUS_M = 250.0


def score(peak_q, save_every_h=12.0):
    elevation, cell_size, terrain_source, inflow, orb_rc = bt.setup()
    times, depths = bt.run_once(peak_q, elevation, cell_size, inflow,
                                save_every_s=save_every_h * 3600.0)
    peak = np.maximum.reduce(depths)        # max depth over the whole run
    stage = float(elevation[orb_rc]) + max(float(d[orb_rc]) for d in depths)

    mask = river.water_mask(elevation, cell_size)
    k = max(1, math.ceil(RADIUS_M / cell_size))

    print(f"\n[score] ORB calibration check: stage {stage:.3f} m "
          f"(target {bt.OBSERVED_ORB_M} m, {'OK' if abs(stage-bt.OBSERVED_ORB_M)<0.10 else 'OFF'})")
    print(f"[score] cell size {cell_size:.1f} m, search radius {k} cells\n")
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
              f"{maxd:10.2f} {match:6s}")

    groupA = [r for r in rows_out if r[1] == "A"]
    groupD = [r for r in rows_out if r[1] == "D"]
    hitsA = sum(1 for r in groupA if r[5] == "YES")
    falseD = sum(1 for r in groupD if r[3] == "flooded")
    print(f"\n[score] Group A (overbank, scored): {hitsA}/{len(groupA)} correct")
    print(f"[score] Group D (control, should stay dry): "
          f"{len(groupD) - falseD}/{len(groupD)} correct "
          f"({falseD} false alarm(s))")
    return rows_out, stage


if __name__ == "__main__":
    import sys

    peak_q = float(sys.argv[1]) if len(sys.argv) > 1 else 4000.0
    score(peak_q)
