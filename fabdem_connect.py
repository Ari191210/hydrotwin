"""Diagnostic only (not a scoring change): for a saved FABDEM trial, label
connected components of PEAK depth >= 0.30 m and say, per site, whether the
scoring cells belong to the component that contains the inflow cells.
Uses the peak-over-time grid (per-frame grids were not saved), so
'connected' here means connected in the envelope of maximum depth.

Usage: python -u fabdem_connect.py Q [Q ...]
"""
import math
import sys

import numpy as np
from scipy.ndimage import label

import backtest_delhi as bt
import config
import fabdem_backtest as f
import terrain

config.set_case("delhi")
elev = np.load(f.SMOOTH_NPY)
mask = np.load(f.MASK_NPY)
cell = terrain.cell_size_m(zoom=config.TERRAIN_ZOOM)
k = max(1, math.ceil(f.RADIUS_M / cell))
orb = terrain.latlon_to_rc(*bt.ORB_LATLON, 150, 150)

for q in sys.argv[1:]:
    z = np.load(f.trial_path(float(q)))
    peak = z["peak6"]
    wet = peak >= f.THRESH
    for conn, struct in ((4, None), (8, np.ones((3, 3)))):
        lab, n = label(wet, structure=struct)
        ir, ic = [int(v) for v in z["inflow_rc"]]
        # river component = the one holding most channel-mask cells
        ids, counts = np.unique(lab[mask & wet], return_counts=True)
        river_id = int(ids[np.argmax(counts)]) if len(ids) else -1
        print(f"\nQ={float(q):.0f} conn={conn}: {n} components; river component "
              f"id {river_id} has {int((lab == river_id).sum())} cells, "
              f"{int(((lab == river_id) & mask).sum())} mask cells; inflow cell "
              f"label {int(lab[ir, ic])}; ORB cell label {int(lab[orb])}")
        for name, (lat, lon, group) in bt.SITES.items():
            r, c = terrain.latlon_to_rc(lat, lon, 150, 150)
            sl = (slice(max(0, r - k), r + k + 1), slice(max(0, c - k), c + k + 1))
            w = wet[sl] & ~mask[sl]
            if not w.any():
                print(f"  {name:22s} {group} no scoring cell >= 0.30 m "
                      f"(max {peak[sl][~mask[sl]].max():.2f})")
                continue
            ls = lab[sl][w]
            n_river = int((ls == river_id).sum())
            wse = (elev[sl] + peak[sl])[w]
            other = sorted(set(int(v) for v in ls if v != river_id))
            sizes = [int((lab == o).sum()) for o in other]
            print(f"  {name:22s} {group} wet scoring cells {int(w.sum())}, in river "
                  f"component {n_river}; other components {len(other)} sizes "
                  f"{sizes}; WSE {wse.min():.2f}..{wse.max():.2f} m; max depth in "
                  f"river component "
                  f"{(peak[sl][w][ls == river_id].max() if n_river else 0):.2f} m")
