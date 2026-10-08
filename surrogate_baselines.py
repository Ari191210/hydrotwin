"""Cheap alternatives to the CNN, tried before spending more training time.

All operate on the SAME 320/60 split already on disk. IoU excludes the OSM
water-mask + inflow-strip cells (wet in every sample, so they pad every
score if left in).
"""
import numpy as np

THRESH = 0.30


def load(case="delhi"):
    tr = np.load(f"assets/surrogate_{case}_train.npz")
    va = np.load(f"assets/surrogate_{case}_val.npz")
    return tr, va


def score(pred, true, exclude):
    """Mean wet-area IoU over samples, cells in `exclude` dropped from both
    sides first."""
    keep = ~exclude
    wp = (pred >= THRESH) & keep
    wt = (true >= THRESH) & keep
    inter = (wp & wt).reshape(len(pred), -1).sum(axis=1)
    union = (wp | wt).reshape(len(pred), -1).sum(axis=1)
    iou = np.where(union > 0, inter / np.maximum(union, 1), 1.0)
    rmse = float(np.sqrt(np.mean(((pred - true) * keep) ** 2)))
    return float(iou.mean()), rmse


def exclude_mask(case="delhi"):
    try:
        mask = np.load("C:/Users/DELL/AppData/Local/Temp/claude/"
                       "C--Users-DELL/ed9a1e5d-67ee-4357-a626-e3627eaebdba/"
                       "scratchpad/delhi_mask.npy")
    except Exception:
        mask = np.zeros(1, dtype=bool)
    # also exclude cells wet in every single training sample (inflow strip)
    tr, _ = load(case)
    always_wet = (tr["peak"] >= THRESH).all(axis=0)
    return mask | always_wet if mask.shape == always_wet.shape else always_wet


def mean_field_baseline(case="delhi"):
    tr, va = load(case)
    excl = exclude_mask(case)
    mean_peak = tr["peak"].mean(axis=0)
    pred = np.broadcast_to(mean_peak, va["peak"].shape)
    iou, rmse = score(pred, va["peak"], excl)
    print(f"[baseline] mean-field: IoU {iou:.3f}  RMSE {rmse:.3f} m")
    return iou, rmse


def per_pixel_poly(case="delhi", degree="quad"):
    tr, va = load(case)
    excl = exclude_mask(case)
    r, q = tr["rain_mult"], tr["river_q"] / 100.0   # rescale q to O(1)-ish
    if degree == "quad":
        X = np.stack([np.ones_like(r), r, q, r * r, q * q, r * q], axis=1)
    else:  # cubic
        X = np.stack([np.ones_like(r), r, q, r * r, q * q, r * q,
                      r ** 3, q ** 3, r * r * q, r * q * q], axis=1)
    Y = tr["peak"].reshape(len(r), -1)             # (n, 22500)
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)    # (k, 22500)

    rv, qv = va["rain_mult"], va["river_q"] / 100.0
    if degree == "quad":
        Xv = np.stack([np.ones_like(rv), rv, qv, rv * rv, qv * qv, rv * qv], axis=1)
    else:
        Xv = np.stack([np.ones_like(rv), rv, qv, rv * rv, qv * qv, rv * qv,
                       rv ** 3, qv ** 3, rv * rv * qv, rv * qv * qv], axis=1)
    pred = (Xv @ coef).reshape(va["peak"].shape)
    pred = np.clip(pred, 0, None)
    iou, rmse = score(pred, va["peak"], excl)
    print(f"[baseline] per-pixel {degree} poly: IoU {iou:.3f}  RMSE {rmse:.3f} m")
    return iou, rmse, coef


def pod_regression(case="delhi", k=20, method="poly"):
    from scipy.interpolate import RBFInterpolator

    tr, va = load(case)
    excl = exclude_mask(case)
    Y = tr["peak"].reshape(len(tr["peak"]), -1)
    mean = Y.mean(axis=0)
    Yc = Y - mean
    U, S, Vt = np.linalg.svd(Yc, full_matrices=False)
    explained = np.cumsum(S ** 2) / np.sum(S ** 2)
    print(f"[pod] explained variance at k=10/20/40: "
          f"{explained[9]:.3f}/{explained[19]:.3f}/{explained[39]:.3f}")
    modes = Vt[:k]                                   # (k, 22500)
    coeffs = Yc @ modes.T                            # (n, k)

    r, q = tr["rain_mult"], tr["river_q"]
    pts = np.stack([r, q], axis=1)
    rv, qv = va["rain_mult"], va["river_q"]
    ptsv = np.stack([rv, qv], axis=1)

    if method == "rbf":
        interp = RBFInterpolator(pts, coeffs, kernel="thin_plate_spline",
                                 smoothing=0.1)
        coeffs_v = interp(ptsv)
    else:
        X = np.stack([np.ones_like(r), r, q, r * r, q * q, r * q], axis=1)
        c, *_ = np.linalg.lstsq(X, coeffs, rcond=None)
        Xv = np.stack([np.ones_like(rv), rv, qv, rv * rv, qv * qv, rv * qv], axis=1)
        coeffs_v = Xv @ c

    pred = (coeffs_v @ modes + mean).reshape(va["peak"].shape)
    pred = np.clip(pred, 0, None)
    iou, rmse = score(pred, va["peak"], excl)
    print(f"[baseline] POD(k={k})+{method}: IoU {iou:.3f}  RMSE {rmse:.3f} m")
    return iou, rmse, (mean, modes, pts, coeffs)


FEATURE_NAMES = ["1", "r", "q", "r2", "q2", "rq", "r3", "q3", "r2q", "rq2"]


def _features(r, q):
    """q pre-scaled by /100 to keep polynomial terms well-conditioned."""
    return np.stack([np.ones_like(r), r, q, r * r, q * q, r * q,
                     r ** 3, q ** 3, r * r * q, r * q * q], axis=1)


def export_poly(case="delhi", degree="cubic", rain_max=4.0, river_qmax=400.0):
    """Fit the per-pixel cubic poly on train+val combined (more data, no
    reason to hold any back once the held-out check above has already
    validated the approach) and export compact weights for the JS forward
    pass: 10 floats per pixel, base64 float32, no elevation needed at
    inference (it's baked into the fit)."""
    import base64
    import json
    import os

    tr, va = load(case)
    r = np.concatenate([tr["rain_mult"], va["rain_mult"]])
    q = np.concatenate([tr["river_q"], va["river_q"]]) / 100.0
    Y = np.concatenate([tr["peak"], va["peak"]]).reshape(len(r), -1)
    X = _features(r, q)
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)        # (10, R*C), south-first

    rows, cols = tr["elevation"].shape
    # viewer3d.py works north-row-first throughout (elev_north = flipud);
    # flip here so the exported grid matches depthsB64/waterMaskB64, not
    # the raw physics (south-first) convention.
    coef_north = coef.reshape(10, rows, cols)[:, ::-1, :].reshape(10, -1)

    # report held-out accuracy using ONLY train for fitting (honest number,
    # matching what per_pixel_poly() printed) alongside the final all-data
    # export, so the shipped metrics aren't quietly better than validated
    iou, rmse, _ = per_pixel_poly(case, degree=degree)

    rows, cols = tr["elevation"].shape
    path = os.path.join("assets", "surrogate")
    os.makedirs(path, exist_ok=True)
    # coef_north, NOT coef: the viewer indexes cell i north-row-first
    blob = base64.b64encode(coef_north.astype("<f4").tobytes()).decode()
    out = {
        "case": case, "rows": rows, "cols": cols, "degree": degree,
        "features": FEATURE_NAMES, "rain_max": rain_max,
        "river_qmax": river_qmax, "q_scale": 100.0,
        "coefB64": blob,
        # viewer3d.py renders this as "Fit to " + method + ". Held-out
        # accuracy: RMSE ... IoU ...", so it must read as a noun phrase and
        # must not point "above" at numbers that come after it
        "metrics": {"rmse_m": rmse, "iou": iou, "method": "380 Landlab "
                    "physics runs (per-pixel cubic polynomial); the accuracy "
                    "figures are from a 320-run fit scored on the 60 "
                    "held-out runs"},
    }
    fpath = os.path.join(path, f"{case}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"[surrogate] {case}: poly surrogate exported to {fpath} "
          f"({os.path.getsize(fpath) / 1024:.0f} KB)")
    return out


if __name__ == "__main__":
    mean_field_baseline()
    per_pixel_poly(degree="quad")
    per_pixel_poly(degree="cubic")
    for k in (10, 20, 40):
        pod_regression(k=k, method="poly")
        pod_regression(k=k, method="rbf")
