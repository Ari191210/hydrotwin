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
    .venv/Scripts/python surrogate.py train delhi
    .venv/Scripts/python surrogate.py train rishikesh
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

# River inflow only exists for cases with a config.INFLOW point (Delhi).
RIVER_Q_MAX = {"delhi": 400.0}   # m3/s excess; ~4x today's live excess


def _sample_params(case, n, rng):
    rain_mult = rng.uniform(0.0, 4.0, n)
    if case in RIVER_Q_MAX:
        river_q = rng.uniform(0.0, RIVER_Q_MAX[case], n)
    else:
        river_q = np.zeros(n)
    return rain_mult, river_q


def _run_one(args):
    case, rain_mult, river_q, elevation, cell_size, inflow, base_series = args
    import config as cfg
    cfg.set_case(case)
    series = [r * rain_mult for r in base_series]
    _, depths = simulate.run_simulation(
        elevation, cell_size,
        lambda t, s=series: s[min(int(t // 3600), len(s) - 1)],
        inflow=inflow, inflow_m3s_at=(lambda t: river_q) if river_q else None)
    return np.stack(depths).max(axis=0).astype(np.float32)


def generate_dataset(case, n_samples, seed=0):
    """Returns (elevation, cell_size, rain_mult[n], river_q[n], peak[n,R,C])."""
    import rainfall
    from concurrent.futures import ProcessPoolExecutor

    config.set_case(case)
    elevation, cell_size, terrain_source = terrain.load_terrain()
    inflow = river.find_inflow(elevation, cell_size) if case in RIVER_Q_MAX \
        else None
    base_series = rainfall.design_storm()   # fixed, strong-enough forcing
    # scale so x1 is a moderate storm, giving the sampled [0,4] range real range
    base_series = [r * 0.6 for r in base_series]

    rng = np.random.default_rng(seed)
    rain_mult, river_q = _sample_params(case, n_samples, rng)

    t0 = time.time()
    jobs = [(case, float(rain_mult[i]), float(river_q[i]), elevation,
             cell_size, inflow, base_series) for i in range(n_samples)]
    peaks = np.empty((n_samples, *elevation.shape), dtype=np.float32)
    with ProcessPoolExecutor() as ex:
        for i, peak in enumerate(ex.map(_run_one, jobs, chunksize=2)):
            peaks[i] = peak
            if (i + 1) % 20 == 0 or i + 1 == n_samples:
                print(f"[surrogate] {case}: {i + 1}/{n_samples} physics runs "
                      f"({time.time() - t0:.0f}s elapsed)")
    return elevation, cell_size, rain_mult, river_q, peaks


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
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 320
        seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        tag = sys.argv[5] if len(sys.argv) > 5 else "train"
        e, c, rm, rq, peaks = generate_dataset(case_arg, n, seed=seed)
        np.savez(f"assets/surrogate_{case_arg}_{tag}.npz", elevation=e,
                 cell_size=c, rain_mult=rm, river_q=rq, peak=peaks)
