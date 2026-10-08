"""Neural surrogate for instant what-if sliders.

Scope, deliberately narrow: for ONE fixed preset location, learn the map
(rain multiplier, river excess m3/s) -> peak flood depth field. Terrain is
fixed per location, so this is a smooth 2-input response surface, not a
general "flood predictor for any place" — that distinction matters for
what we can honestly claim in front of judges.

Training data comes from the SAME validated Landlab physics (simulate.py)
this project already runs, so the surrogate's ceiling is "as good as the
physics it was trained to imitate," never better. Accuracy is reported
against held-out physics runs, same as any other result in this repo.

Usage:
    .venv/Scripts/python -u surrogate.py gendata delhi 7   # ~30 min, 7 procs
    .venv/Scripts/python -u surrogate_baselines.py export  # fit, score, ship

The shipped model is the one fitted in surrogate_baselines.py. The CNN below
(`surrogate.py train`) is unused and predates the current river pipeline.
"""

import json
import os
import sys
import time

import numpy as np

import config
import river
import simulate
import terrain

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_HERE, "assets", "surrogate")

# ---------------------------------------------------- training data ----
# The samples are produced by the SAME calls run.py makes for the live Delhi
# page: OSM water mask -> conditioned DEM -> inflow -> bankfull footprint ->
# exclusion mask -> warm start at the routed discharge -> 6 h run. Only the
# two inputs vary:
#   rain_mult  r in [0, RAIN_MULT_MAX], applied to rainfall.design_storm()
#              x RAIN_BASE_SCALE (96 mm per unit over 6 h for Delhi)
#   river_q    routed discharge above the dry-season baseline, m3/s, in
#              [0, Q_MAX]. Always a multiple of config.SPINUP_Q_STEP_M3S, so
#              the warm start is computed at exactly the discharge routed in.
RAIN_MULT_MAX = 4.0
RAIN_BASE_SCALE = 0.6
Q_MAX = 5000.0                    # ~4x the bankfull excess (1304 m3/s)
RIVER_Q_MAX = {"delhi": Q_MAX}

# Discharge is sampled on a grid (one cached spin-up per value), denser at
# low flows and around bankfull; rain is random within each discharge.
TRAIN_Q = [0, 50, 100, 150, 200, 275, 350, 450, 600, 800, 1000, 1100, 1200,
           1305, 1400, 1500, 1600, 1800, 2000, 2300, 2600, 3000, 3500, 4000,
           4500, 5000]
TRAIN_R_PER_Q = 9                 # r = 0 and r = 4 exactly, 7 jittered between
# Validation: discharges the fit never sees (three "whole" values left out of
# the grid, ten in-between ones), plus a few grid values with new rain.
VAL_Q_HELDOUT = [400, 1250, 3250]                       # 5 rains each
VAL_Q_BETWEEN = [125, 700, 1150, 1355, 1450, 1700, 2150, 2450, 4250, 4750]
VAL_Q_ONGRID = [0, 275, 1305, 2600, 5000]               # 1 rain each


def sample_design(seed=0):
    """((r_train, q_train), (r_val, q_val)) as float arrays."""
    rng = np.random.default_rng(seed)
    rt, qt = [], []
    n_in = TRAIN_R_PER_Q - 2
    for q in TRAIN_Q:
        inner = (np.arange(n_in) + rng.uniform(0, 1, n_in)) / n_in \
            * RAIN_MULT_MAX
        for r in [0.0, *inner, RAIN_MULT_MAX]:
            rt.append(float(r))
            qt.append(float(q))
    rv, qv = [], []
    for qs, n in ((VAL_Q_HELDOUT, 5), (VAL_Q_BETWEEN, 3), (VAL_Q_ONGRID, 1)):
        for q in qs:
            for r in rng.uniform(0.0, RAIN_MULT_MAX, n):
                rv.append(float(r))
                qv.append(float(q))
    return (np.array(rt), np.array(qt)), (np.array(rv), np.array(qv))


def pipeline_state(case, use_discharge=True):
    """Everything run.py builds before it simulates, for `case`:
    {"elevation" (conditioned), "cell_size", "inflow", "channel",
     "footprint", "exclude", "q_bankfull_routed", "state_hash"}.

    use_discharge=False skips the GloFAS fetch; the bankfull footprint then
    comes from its cache in assets/masks/ (scenarios.river_footprint with no
    discharge), which is how surrogate_baselines.exclude_mask() rebuilds the
    live exclusion mask without touching the network."""
    import flooddata
    import riverstate
    import scenarios as scen

    config.set_case(case)
    elevation, cell_size, terrain_source = terrain.load_terrain()
    water_mask = scen.fetch_water_mask(elevation, cell_size)
    elevation, terrain_source, channel = scen.condition_terrain(
        elevation, cell_size, terrain_source, water_mask)
    discharge = flooddata.get_river_discharge() if use_discharge else None
    inflow = river.find_inflow(elevation, cell_size)
    footprint = scen.river_footprint(elevation, cell_size, inflow, discharge,
                                     channel)
    # q_m3s nonzero: the inflow cells are part of the live exclusion
    exclude = scen.exclude_mask(water_mask, elevation.shape, inflow, 1.0,
                                footprint)
    qb = None
    if discharge and discharge.get("q_bankfull") is not None:
        qb = discharge["q_bankfull"] - discharge["q_dem_baseline"]
    return {"elevation": elevation, "cell_size": cell_size, "inflow": inflow,
            "channel": channel, "footprint": footprint, "exclude": exclude,
            "q_bankfull_routed": qb,
            "state_hash": riverstate.state_hash(elevation, cell_size, inflow)
            if inflow else None}


def _worker_init(case):
    config.set_case(case)


def _spinup_one(args):
    """One steady state per distinct discharge (cached by riverstate). Run
    for every discharge BEFORE the samples, one process per value, so no two
    workers ever compute and write the same cache file."""
    case, q, elevation, cell_size, inflow = args
    import riverstate
    config.set_case(case)
    st = riverstate.warm_start(elevation, cell_size, inflow, q)
    return {"q": q, "converged": bool(st["converged"]),
            "hours": float(st["hours"]), "seconds": float(st["seconds"]),
            "cached": bool(st["cached"]),
            "outflow_m3s": float(st["outflow_m3s"])}


def _run_one(args):
    """Peak depth (row 0 = south) of one sample, through the live path:
    scenarios.river_warm_start + scenarios.run_all."""
    case, rain_mult, river_q, elevation, cell_size, inflow, base_series, \
        exclude = args
    import scenarios as scen
    config.set_case(case)
    config.POIS = scen.resolve_pois(config.POIS, elevation.shape)
    t0 = time.time()
    # channel=True: the DEM handed in is already conditioned
    initial = scen.river_warm_start(elevation, cell_size, inflow, river_q,
                                    True)
    if river_q and (initial is None or not initial["cached"]):
        raise RuntimeError(f"warm start at {river_q} m3/s was not precomputed")
    spec = scen._spec(f"r{rain_mult:.3f} q{river_q:.0f}", rain_mult,
                      base_series, "surrogate training", whatif=True)
    out = scen.run_all([spec], elevation, cell_size, inflow, river_q,
                       exclude=exclude, initial=initial)[0]
    peak = np.stack(out["depths"]).max(axis=0).astype(np.float32)
    return peak, time.time() - t0


def generate_dataset(case, rain_mult, river_q, state, workers=7):
    """Physics peaks for the given (rain_mult, river_q) pairs.
    Returns (peak[n, R, C], spinups[list of dict], seconds per sample[n])."""
    import rainfall
    from concurrent.futures import ProcessPoolExecutor

    config.set_case(case)
    elevation, cell_size = state["elevation"], state["cell_size"]
    inflow, exclude = state["inflow"], state["exclude"]
    step = config.SPINUP_Q_STEP_M3S
    if any(abs(q / step - round(q / step)) > 1e-9 for q in river_q):
        raise ValueError("river_q must be multiples of SPINUP_Q_STEP_M3S")
    base_series = [r * RAIN_BASE_SCALE for r in rainfall.design_storm()]

    t0 = time.time()
    spinups = []
    qs = sorted({float(q) for q in river_q if q > 0}, reverse=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                             initargs=(case,)) as ex:
        for s in ex.map(_spinup_one, [(case, q, elevation, cell_size, inflow)
                                      for q in qs]):
            spinups.append(s)
            print(f"[surrogate] spin-up {s['q']:.0f} m3/s: "
                  f"{'cached' if s['cached'] else 'computed'}, "
                  f"{'steady' if s['converged'] else 'NOT STEADY'} after "
                  f"{s['hours']:.0f} h ({s['seconds']:.0f} s)", flush=True)
        print(f"[surrogate] {len(qs)} spin-ups ready after "
              f"{time.time() - t0:.0f} s", flush=True)

        n = len(rain_mult)
        jobs = [(case, float(rain_mult[i]), float(river_q[i]), elevation,
                 cell_size, inflow, base_series, exclude) for i in range(n)]
        peaks = np.empty((n, *elevation.shape), dtype=np.float32)
        secs = np.empty(n)
        for i, (peak, s) in enumerate(ex.map(_run_one, jobs)):
            peaks[i], secs[i] = peak, s
            if (i + 1) % 20 == 0 or i + 1 == n:
                print(f"[surrogate] {case}: {i + 1}/{n} physics runs "
                      f"({time.time() - t0:.0f}s elapsed)", flush=True)
    return peaks, spinups, secs


def generate_and_save(case="delhi", workers=7, seed=0):
    """Regenerate assets/surrogate_<case>_{train,val}.npz on the live
    pipeline. Returns the wall time in seconds."""
    t0 = time.time()
    state = pipeline_state(case)
    (rt, qt), (rv, qv) = sample_design(seed)
    base_mm = sum(r * RAIN_BASE_SCALE for r in
                  __import__("rainfall").design_storm())
    print(f"[surrogate] {case}: {len(rt)} train + {len(rv)} val samples, "
          f"state hash {state['state_hash']}, exclusion "
          f"{int(state['exclude'].sum())} cells, {base_mm:.1f} mm per unit "
          f"rain", flush=True)
    for tag, r, q in (("train", rt, qt), ("val", rv, qv)):
        peaks, spinups, secs = generate_dataset(case, r, q, state, workers)
        np.savez(f"assets/surrogate_{case}_{tag}.npz",
                 elevation=state["elevation"], cell_size=state["cell_size"],
                 rain_mult=r, river_q=q, peak=peaks,
                 exclude=state["exclude"], footprint=state["footprint"],
                 rain_mm_per_unit=base_mm,
                 q_bankfull_routed=state["q_bankfull_routed"] or np.nan,
                 state_hash=state["state_hash"],
                 spinups=json.dumps(spinups), sample_seconds=secs)
        print(f"[surrogate] {case} {tag}: saved ({time.time() - t0:.0f}s "
              f"since start)", flush=True)
    return time.time() - t0


# ------------------------------------------------------------- model ----

class SurrogateNet:
    """Tiny CNN: [elevation, rain_mult broadcast, river_q broadcast]
    (3, R, C) -> peak depth (1, R, C). Three 3x3 conv layers, no pooling
    (flood response at this grid size is local-ish; keeping it
    resolution-preserving also makes the hand-rolled JS forward pass in
    the viewer trivial — no up/downsampling to reimplement)."""

    def __init__(self, hidden=20):
        import torch.nn as nn

        self.hidden = hidden
        self.net = nn.Sequential(
            nn.Conv2d(3, hidden, 3, padding=1), nn.ReLU(),
            nn.Conv2d(hidden, hidden, 3, padding=1), nn.ReLU(),
            nn.Conv2d(hidden, 1, 3, padding=1), nn.Softplus(),  # depth >= 0
        )

    def __call__(self, x):
        return self.net(x)

    def parameters(self):
        return self.net.parameters()

    def state_dict(self):
        return self.net.state_dict()

    def load_state_dict(self, sd):
        self.net.load_state_dict(sd)

    def eval(self):
        self.net.eval()
        return self

    def train(self):
        self.net.train()
        return self


def _norms(elevation):
    emin, emax = float(elevation.min()), float(elevation.max())
    erange = max(emax - emin, 1e-6)
    return emin, erange


def _to_input(elevation, rain_mult, river_q, emin, erange, qmax):
    """(rain_mult, river_q) scalars (array-like, len N) + fixed elevation
    -> (N, 3, R, C) float32 tensor. Scalars normalized to roughly [0,1]."""
    import torch

    rows, cols = elevation.shape
    elev_n = (elevation - emin) / erange
    n = len(rain_mult)
    x = np.empty((n, 3, rows, cols), dtype=np.float32)
    x[:, 0] = elev_n
    x[:, 1] = (np.asarray(rain_mult) / 4.0)[:, None, None]
    x[:, 2] = (np.asarray(river_q) / max(qmax, 1e-6))[:, None, None]
    return torch.from_numpy(x)


def train_surrogate(case, max_seconds=240, hidden=12, lr=3e-3):
    """Time-budgeted, not epoch-budgeted: a bad early estimate of
    epochs-needed is how the first attempt at this ran unobserved for
    20+ minutes on full-resolution (no-pooling) convs. Prints every
    epoch, flushed, so a stall or runaway cost is visible immediately
    instead of discovered later."""
    import torch
    import torch.nn as nn

    torch.set_num_threads(min(8, os.cpu_count() or 4))

    tr = np.load(f"assets/surrogate_{case}_train.npz")
    va = np.load(f"assets/surrogate_{case}_val.npz")
    elevation = tr["elevation"]
    emin, erange = _norms(elevation)
    qmax = RIVER_Q_MAX.get(case, 1.0)

    xt = _to_input(elevation, tr["rain_mult"], tr["river_q"], emin, erange, qmax)
    yt = torch.from_numpy(tr["peak"]).unsqueeze(1)
    xv = _to_input(elevation, va["rain_mult"], va["river_q"], emin, erange, qmax)
    yv = torch.from_numpy(va["peak"]).unsqueeze(1)

    model = SurrogateNet(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    n = xt.shape[0]
    batch = 32
    t0 = time.time()
    ep = 0
    while True:
        ep_t0 = time.time()
        model.train()
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            pred = model(xt[idx])
            loss = loss_fn(pred, yt[idx])
            loss.backward()
            opt.step()
            tot += float(loss) * len(idx)
        ep_s = time.time() - ep_t0
        if ep == 0:
            budget_epochs = max(3, int(max_seconds / max(ep_s, 1e-3)))
            print(f"[surrogate] {case}: {ep_s:.1f}s/epoch measured -> "
                  f"budgeting ~{budget_epochs} epochs for a {max_seconds}s cap",
                  flush=True)
        if ep % 5 == 0 or ep_s > 5:
            model.eval()
            with torch.no_grad():
                vpred = model(xv)
                vrmse = float(torch.sqrt(loss_fn(vpred, yv)))
            print(f"[surrogate] {case} epoch {ep + 1}  train MSE {tot / n:.4f}  "
                  f"val RMSE {vrmse:.3f} m  ({ep_s:.1f}s/epoch, "
                  f"{time.time() - t0:.0f}s total)", flush=True)
        ep += 1
        if time.time() - t0 > max_seconds:
            print(f"[surrogate] {case}: time budget reached after {ep} epochs",
                  flush=True)
            break

    model.eval()
    with torch.no_grad():
        vpred = model(xv).squeeze(1).numpy()
    yv_np = va["peak"]
    rmse = float(np.sqrt(np.mean((vpred - yv_np) ** 2)))
    mae = float(np.mean(np.abs(vpred - yv_np)))
    thresh = config.FLOOD_DEPTH_M if hasattr(config, "FLOOD_DEPTH_M") else 0.3
    wet_p, wet_t = vpred >= thresh, yv_np >= thresh
    inter = (wet_p & wet_t).sum(axis=(1, 2))
    union = (wet_p | wet_t).sum(axis=(1, 2))
    iou = np.where(union > 0, inter / np.maximum(union, 1), 1.0)
    print(f"[surrogate] {case} VALIDATION: RMSE {rmse:.3f} m, MAE {mae:.3f} m, "
          f"wet-area IoU mean {iou.mean():.3f} (n={len(iou)} held-out "
          f"physics runs, never seen in training)", flush=True)

    os.makedirs(MODEL_DIR, exist_ok=True)
    export_js(case, model, elevation, emin, erange, qmax,
             metrics={"rmse_m": rmse, "mae_m": mae, "iou": float(iou.mean())})
    return model, {"rmse_m": rmse, "mae_m": mae, "iou": float(iou.mean())}


def export_js(case, model, elevation, emin, erange, qmax, metrics):
    """Dump weights + norm constants as JSON (small enough: 3x20 + 20x20x20
    + 20x1 conv kernels, a few thousand floats) for the hand-rolled JS
    forward pass in viewer3d.py — no ONNX/TF.js runtime, stays offline."""
    sd = model.state_dict()
    layers = []
    for i in (0, 2, 4):
        w = sd[f"{i}.weight"].numpy().astype(np.float32)  # (out,in,3,3)
        b = sd[f"{i}.bias"].numpy().astype(np.float32)
        layers.append({"w": w.flatten().tolist(), "b": b.tolist(),
                       "cin": w.shape[1], "cout": w.shape[0]})
    out = {
        "case": case, "rows": int(elevation.shape[0]),
        "cols": int(elevation.shape[1]),
        "emin": emin, "erange": erange, "qmax": qmax,
        "layers": layers, "metrics": metrics,
    }
    path = os.path.join(MODEL_DIR, f"{case}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    size_kb = os.path.getsize(path) / 1024
    print(f"[surrogate] {case}: weights exported to {path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "train"
    case_arg = sys.argv[2] if len(sys.argv) > 2 else "delhi"
    if action == "train":
        train_surrogate(case_arg)
    elif action == "gendata":
        # .venv/Scripts/python -u surrogate.py gendata delhi [workers]
        generate_and_save(case_arg,
                          int(sys.argv[3]) if len(sys.argv) > 3 else 7)
