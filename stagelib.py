"""Stage-indexed inundation library for Delhi.

Barrage release is a poor predictor of the flood level at Delhi (the 2023
record came from the smallest release of the nine large floods since
1978), so the lookup is keyed on the river level at the Old Railway
Bridge (ORB), which is the variable the official warnings and CWC
forecasts use. For a ladder of steady river discharges the model is run
to steady state with NO rain; each run gives one ORB stage and one depth
field. A forecast stage is then answered by interpolating between runs.

No rain is deliberate: over long runs rain pools in closed terrain dips
because the model has no drains, which an earlier backtest showed
produces wet cells unrelated to the river.

    python stagelib.py build srtm      # or: fabdem
"""

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import config
import river
import riverstate
import terrain

ORB_LATLON = (28.6636, 77.2487)          # Old Iron Bridge / Loha Pul (OSM)
HERE = os.path.dirname(os.path.abspath(__file__))
FABDEM_GRID = os.path.join(HERE, "assets", "dem",
                           "delhi_fabdem_smooth_150.npy")
Q_LADDER = [250, 500, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000, 8000,
            9000, 10000, 12000]
Q_EXTRA = [15000, 18000, 21000, 24000, 28000, 32000]   # only if needed
TOP_STAGE_M = 209.2                       # ladder must reach past the record


def lib_path(dem):
    return os.path.join(HERE, "assets", f"stagelib_delhi_{dem}.npz")


def setup(dem):
    """(conditioned elevation, raw elevation, cell_size, inflow, mask,
    orb_rc, diagnostics) for dem in {'srtm', 'fabdem'}."""
    config.set_case("delhi")
    raw, cell, source = terrain.load_terrain()
    if dem == "fabdem":
        fab = np.load(FABDEM_GRID)
        assert fab.shape == raw.shape, "FABDEM grid / Delhi grid mismatch"
        raw, source = fab, "FABDEM V1-2 (bare earth), sigma 1.2"
    elif dem != "srtm":
        raise ValueError(dem)
    mask = river.water_mask(raw, cell)
    if not mask.any():
        raise RuntimeError("no OSM water mask (cache missing and fetch failed)")
    cond, diag = river.condition_channel(raw, cell, mask, quiet=True)
    if diag is None:
        raise RuntimeError("channel conditioning failed")
    inflow = river.find_inflow(cond, cell, quiet=True)
    orb_rc = terrain.latlon_to_rc(*ORB_LATLON, *raw.shape)
    return cond, raw, cell, inflow, mask, orb_rc, diag, source


def _one(args):
    dem, q = args
    cond, raw, cell, inflow, mask, orb_rc, diag, source = setup(dem)
    st = riverstate.steady_state(cond, cell, inflow, float(q),
                                 what=f"{dem} ladder")
    stage = float(cond[orb_rc]) + float(st["depth"][orb_rc])
    return (q, stage, bool(st["converged"]), float(st["hours"]),
            float(st["outflow_m3s"]), st["depth"].astype(np.float32))


def build(dem, workers=6):
    cond, raw, cell, inflow, mask, orb_rc, diag, source = setup(dem)
    print(f"[stagelib] {dem}: {source}; ORB cell {orb_rc}, bed "
          f"{cond[orb_rc]:.2f} m (raw {raw[orb_rc]:.2f} m)", flush=True)
    rows = []
    todo = list(Q_LADDER)
    extra = list(Q_EXTRA)
    while todo:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one, [(dem, q) for q in todo]):
                rows.append(r)
                print(f"[stagelib] {dem} Q={r[0]:>6.0f} m3/s -> ORB stage "
                      f"{r[1]:.3f} m ({'steady' if r[2] else 'NOT steady'} "
                      f"after {r[3]:.0f} h, outflow {r[4]:.0f})", flush=True)
        todo = []
        if max(r[1] for r in rows) < TOP_STAGE_M and extra:
            todo = extra[:3]
            extra = extra[3:]
    rows.sort(key=lambda r: r[0])
    np.savez_compressed(
        lib_path(dem),
        q_m3s=np.array([r[0] for r in rows], float),
        orb_stage_m=np.array([r[1] for r in rows], float),
        converged=np.array([r[2] for r in rows], bool),
        hours=np.array([r[3] for r in rows], float),
        outflow_m3s=np.array([r[4] for r in rows], float),
        depths=np.stack([r[5] for r in rows]),           # (nQ, R, C), south=0
        elevation=cond.astype(np.float32),
        elevation_raw=raw.astype(np.float32),
        cell_size=np.float64(cell), osm_mask=mask,
        orb_rc=np.array(orb_rc), dem=np.array(dem), source=np.array(source),
        inflow_nodes=np.array(inflow["nodes"]),
        conditioning=np.array(json.dumps(
            {k: diag[k] for k in ("cells_changed", "max_lowering_m",
                                  "mean_lowering_m", "path_length_m")})))
    print(f"[stagelib] saved {lib_path(dem)} ({len(rows)} discharges)",
          flush=True)


class Library:
    """Lookup: forecast ORB stage (m) -> depth field (row 0 = south)."""

    def __init__(self, dem="srtm"):
        z = np.load(lib_path(dem))
        self.dem = dem
        self.q = z["q_m3s"]
        self.stage = z["orb_stage_m"]
        self.depths = z["depths"]
        self.elevation = z["elevation"]
        self.elevation_raw = z["elevation_raw"]
        self.cell = float(z["cell_size"])
        self.mask = z["osm_mask"]
        self.orb_rc = tuple(int(v) for v in z["orb_rc"])
        self.source = str(z["source"])
        self.converged = z["converged"]
        if np.any(np.diff(self.stage) <= 0):
            raise RuntimeError("ORB stage is not increasing with discharge")

    def depth_at_stage(self, stage_m):
        """Depth field for an ORB stage, linear between the two bracketing
        runs. Raises outside the ladder rather than extrapolating."""
        if not (self.stage[0] <= stage_m <= self.stage[-1]):
            raise ValueError(
                f"stage {stage_m} m is outside the library "
                f"({self.stage[0]:.2f} to {self.stage[-1]:.2f} m)")
        i = int(np.searchsorted(self.stage, stage_m))
        if self.stage[i] == stage_m:
            return self.depths[i].copy(), float(self.q[i])
        w = (stage_m - self.stage[i - 1]) / (self.stage[i] - self.stage[i - 1])
        d = (1 - w) * self.depths[i - 1] + w * self.depths[i]
        q = (1 - w) * self.q[i - 1] + w * self.q[i]
        return d, float(q)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2], workers=int(sys.argv[3]) if len(sys.argv) > 3 else 6)
    else:
        print(__doc__)
