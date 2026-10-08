"""Fit, score and export the Delhi "ML instant preview" surrogate.

Data: assets/surrogate_<case>_{train,val}.npz from surrogate.py (the live
pipeline: conditioned DEM, warm start at the routed discharge, 6 h run).
Inputs r (rain multiplier, 96 mm per unit) and q (routed river discharge
above the dry-season baseline, m3/s); target = peak depth field.

Scoring is on cells OUTSIDE the live exclusion mask only (OSM water + inflow
cells + bankfull footprint), because that is what "flooded" means on the
page. Rules fixed before any result was looked at:

  * wet-area IoU at 0.30 m, per sample, averaged over the samples whose
    union (predicted or true wet cells) is not empty. Samples where both are
    empty are counted and reported separately: scoring them 1.0 would pad
    every average, since below bankfull with little rain nothing floods.
    A pooled IoU (sum of intersections / sum of unions) is reported too.
  * RMSE over the kept cells only.
  * bands by routed discharge: below bankfull (q < 1100), around it
    (1100..1600; bankfull is ~1304), well above (q > 1600).
  * model choice: by leave-discharges-out cross-validation on the TRAINING
    set; the validation set is scored once for the chosen model (the other
    forms are printed beside it for the record, not used to choose).
  * ship only if held-out IoU >= 0.80 overall AND >= 0.70 in the well-above
    band AND overall IoU beats the mean-field baseline by >= 0.10.

Every model form here is "feature vector of (r, q)" times per-pixel
coefficients, optionally with the coefficient matrix factored through a few
spatial modes, so the viewer's forward pass is a short pure-JS loop.

    .venv/Scripts/python -u surrogate_baselines.py            # table
    .venv/Scripts/python -u surrogate_baselines.py export     # table + ship
"""
import base64
import json
import os
import sys

import numpy as np

THRESH = 0.30
BANDS = (("below bankfull (q < 1100)", -1.0, 1100.0),
         ("around bankfull (1100-1600)", 1100.0, 1600.5),
         ("well above bankfull (q > 1600)", 1600.5, 1e12))
SHIP_IOU_ALL = 0.80
SHIP_IOU_ABOVE = 0.70
SHIP_MARGIN = 0.10

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_HERE, "assets", "surrogate")
_EXCL = {}


def load(case="delhi"):
    tr = np.load(os.path.join(_HERE, "assets", f"surrogate_{case}_train.npz"))
    va = np.load(os.path.join(_HERE, "assets", f"surrogate_{case}_val.npz"))
    return tr, va


def exclude_mask(case="delhi"):
    """The live exclusion mask (row 0 = south), rebuilt with the pipeline's
    own functions from the cached OSM mask and bankfull footprint in
    assets/masks/. Must equal the mask stored with the training data."""
    if case not in _EXCL:
        import surrogate
        ex = surrogate.pipeline_state(case, use_discharge=False)["exclude"]
        tr, va = load(case)
        for z in (tr, va):
            if not np.array_equal(z["exclude"], ex):
                raise RuntimeError(
                    "the exclusion mask stored with the surrogate data is "
                    "not the pipeline's current one: regenerate the data")
        _EXCL[case] = ex
    return _EXCL[case]


def score(pred, true, exclude):
    """Scores on cells outside `exclude`. Returns a dict:
    iou (mean over samples with a non-empty union), n_scored, n_empty (both
    empty, left out of the mean), iou_pooled, rmse (kept cells), per_sample
    (IoU, nan where the union is empty)."""
    keep = ~exclude
    n = len(pred)
    wp = ((pred >= THRESH) & keep).reshape(n, -1)
    wt = ((true >= THRESH) & keep).reshape(n, -1)
    inter = (wp & wt).sum(axis=1).astype(float)
    union = (wp | wt).sum(axis=1).astype(float)
    per = np.where(union > 0, inter / np.maximum(union, 1), np.nan)
    ok = union > 0
    err = (pred - true)[:, keep]
    either = (wp | wt)[:, keep.ravel()]
    return {"iou": float(per[ok].mean()) if ok.any() else float("nan"),
            "n_scored": int(ok.sum()), "n_empty": int((~ok).sum()),
            "iou_pooled": float(inter.sum() / union.sum()) if union.sum()
            else float("nan"),
            "rmse": float(np.sqrt(np.mean(err ** 2))), "per_sample": per,
            # over the cells flooded in the physics or the model only: the
            # plain RMSE is diluted by ~18k cells that are dry in both
            "rmse_wet": float(np.sqrt(np.mean(err[either] ** 2)))
            if either.any() else float("nan"),
            "true_cells": float(wt.sum(axis=1).mean()),
            "pred_cells": float(wp.sum(axis=1).mean())}


def score_bands(pred, true, exclude, q):
    out = {"overall": score(pred, true, exclude)}
    for name, lo, hi in BANDS:
        m = (q >= lo) & (q < hi)
        out[name] = score(pred[m], true[m], exclude) if m.any() else None
    return out


# ------------------------------------------------------------ features ----

FEATURE_NAMES = ["1", "r", "q", "r2", "q2", "rq", "r3", "q3", "r2q", "rq2"]
Q_SCALE = 1000.0


def _features(r, q):
    """Cubic in (r, q); q pre-scaled to O(1) by the caller."""
    return np.stack([np.ones_like(r), r, q, r * r, q * q, r * q,
                     r ** 3, q ** 3, r * r * q, r * q * q], axis=1)


def _hat(x, knots):
    """Piecewise-linear (hat) basis: (n, len(knots)), rows sum to 1, x
    clamped to the knot range."""
    knots = np.asarray(knots, float)
    x = np.clip(np.asarray(x, float), knots[0], knots[-1])
    j = np.clip(np.searchsorted(knots, x, side="right") - 1, 0,
                len(knots) - 2)
    t = (x - knots[j]) / (knots[j + 1] - knots[j])
    B = np.zeros((len(x), len(knots)))
    B[np.arange(len(x)), j] = 1.0 - t
    B[np.arange(len(x)), j + 1] += t
    return B


def _r_basis(r, spec):
    if spec["r"] == "hat":
        return _hat(r, spec["knots_r"])
    return np.stack([r ** p for p in range(spec["r_degree"] + 1)], axis=1)


def features(r, q, spec):
    """(n, F) design matrix of a model spec.
      cubic / quad : polynomial in (r, q/1000)
      hinge        : cubic in r, quadratic in q/1000 and in the excess over
                     bankfull h = max(q - q_bankfull, 0)/1000, plus r*q, r*h
      pwl          : hat basis in q at spec["knots_q"]  (x)  a basis in r
                     (polynomial of r_degree, or hats at knots_r); feature
                     index = knot * m + j
    """
    r, q = np.asarray(r, float), np.asarray(q, float)
    kind = spec["kind"]
    if kind == "cubic":
        return _features(r, q / Q_SCALE)
    if kind == "quad":
        return _features(r, q / Q_SCALE)[:, :6]
    if kind == "hinge":
        s = q / Q_SCALE
        h = np.maximum(q - spec["q_bankfull"], 0.0) / Q_SCALE
        return np.stack([np.ones_like(r), r, r * r, r ** 3, s, s * s, h,
                         h * h, r * s, r * h], axis=1)
    Bq, Br = _hat(q, spec["knots_q"]), _r_basis(r, spec)
    return (Bq[:, :, None] * Br[:, None, :]).reshape(len(r), -1)


def fit(spec, r, q, Y):
    """Per-pixel least squares. Y (n, N). Returns (spec with the knots
    filled in, coef (F, N)). A pwl spec with knots_q "data" takes the
    distinct discharges of the data it is fitted to as its knots."""
    spec = dict(spec)
    if spec["kind"] == "pwl" and isinstance(spec["knots_q"], str):
        spec["knots_q"] = sorted({float(v) for v in q})
    X = features(r, q, spec)
    w_end = spec.get("end_weight", 0.0)
    if w_end:
        # Every discharge has a run at exactly r = 0 and at the last r knot:
        # weight those rows so the end knots reproduce them (a nearby run at
        # r ~ 0.2 otherwise drags knot 0 up). The no-rain prediction is then
        # a blend of two no-rain physics fields, nothing else.
        kr = spec["knots_r"]
        w = np.where((r == kr[0]) | (r == kr[-1]), w_end, 1.0)[:, None]
        X, Y = X * w, Y * w
    lam = spec.get("smooth_r", 0.0)
    if lam:
        # roughness penalty lam * (second difference along the r knots)^2,
        # per q knot. With as many r knots as runs per discharge the plain
        # fit interpolates, and a knot that only gets a sliver of weight
        # from its nearest run (random rains) is then free to take any
        # value; the penalty pulls such a knot onto its neighbours' line.
        # "pin_ends": leave the first and last r knot out of the penalty.
        # Every discharge has a run at exactly r = 0 and r = 4, so those
        # knots are data; and depth has a real kink at r = 0 (the first rain
        # ponds), which a penalty reaching knot 0 smears into the no-rain
        # field (0.2 m of invented water at 275 m3/s where the physics has
        # 0.02 m).
        nq, m = len(spec["knots_q"]), len(spec["knots_r"])
        js = range(2, m - 2) if spec.get("pin_ends") else range(1, m - 1)
        D = np.zeros((nq * len(js), nq * m))
        for k in range(nq):
            for i, j in enumerate(js):
                D[k * len(js) + i, k * m + j - 1:k * m + j + 2] = \
                    (1.0, -2.0, 1.0)
        X = np.vstack([X, np.sqrt(lam) * D])
        Y = np.vstack([Y, np.zeros((len(D), Y.shape[1]), Y.dtype)])
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    return spec, coef


def predict(spec, coef, r, q, shape):
    return np.clip(features(r, q, spec) @ coef, 0, None).reshape(
        len(r), *shape)


def compress(coef, k):
    """coef (F, N) ~= A (F, k) @ modes (k, N): truncated SVD. The forward
    pass becomes weights = phi @ A (k numbers), depth = weights @ modes."""
    U, S, Vt = np.linalg.svd(coef, full_matrices=False)
    return U[:, :k] * S[:k], Vt[:k]


SPECS = {
    "per-pixel cubic": {"kind": "cubic"},
    "cubic + bankfull hinge": {"kind": "hinge", "q_bankfull": 1305.0},
    "pwl in q x quadratic in r": {"kind": "pwl", "knots_q": "data",
                                  "r": "poly", "r_degree": 2},
    "pwl in q x cubic in r": {"kind": "pwl", "knots_q": "data",
                              "r": "poly", "r_degree": 3},
    "pwl in q x pwl in r (5 knots)": {"kind": "pwl", "knots_q": "data",
                                      "r": "hat",
                                      "knots_r": [0, 1, 2, 3, 4]},
    "pwl in q x pwl in r (9 knots)": {"kind": "pwl", "knots_q": "data",
                                      "r": "hat", "knots_r":
                                      [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
    # added after the first table, for a reason that is not a score: the
    # 9-knot fit above has zero degrees of freedom left (9 runs, 9 knots per
    # discharge), see fit(). Chosen between by the same CV.
    "pwl q x pwl r (9 knots), smooth 0.02": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.02,
        "knots_r": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
    "pwl q x pwl r (9 knots), smooth 0.2": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.2,
        "knots_r": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
    "pwl q x pwl r (7 knots), smooth 0.02": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.02,
        "knots_r": [0, 2 / 3, 4 / 3, 2, 8 / 3, 10 / 3, 4]},
    # added third, again not for a score: the smoothed fits put 0.2 m of
    # water outside the river at the panel's default position, a point the
    # physics was run at (see "pin_ends" in fit()).
    "pwl q x pwl r (9), smooth 0.02, ends pinned": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.02,
        "pin_ends": True, "knots_r": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
    "pwl q x pwl r (9), smooth 0.1, ends pinned": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.1,
        "pin_ends": True, "knots_r": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
    # pinning alone left 0.1-0.2 m there; this makes the r = 0 and r = 4
    # knots reproduce the runs made at exactly those rains
    "pwl q x pwl r (9), smooth 0.02, ends exact": {
        "kind": "pwl", "knots_q": "data", "r": "hat", "smooth_r": 0.02,
        "pin_ends": True, "end_weight": 30.0,
        "knots_r": [0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4]},
}
# Shipped in place of the CV winner when its CV IoU is within PREFER_TOL of
# it: decided after the tables had been seen, for the fidelity reason above
# (no invented water at zero rain), not for its score.
PREFERRED = "pwl q x pwl r (9), smooth 0.02, ends exact"
PREFER_TOL = 0.005
N_FOLDS = 6


def cross_validate(spec, r, q, peak, exclude, k_modes=None):
    """Leave-discharges-out CV on the training set: the interior discharge
    values are dealt into N_FOLDS interleaved groups; each group's runs are
    predicted from a fit that never saw those discharges (so the gaps it
    interpolates across are about twice the real grid spacing)."""
    qs = sorted({float(v) for v in q})[1:-1]      # ends always stay in
    shape = peak.shape[1:]
    Y = peak.reshape(len(r), -1)
    pred = np.full_like(peak, np.nan)
    for f in range(N_FOLDS):
        held = np.isin(q, qs[f::N_FOLDS])
        sp, coef = fit(spec, r[~held], q[~held], Y[~held])
        if k_modes:
            A, M = compress(coef, k_modes)
            coef = A @ M
        pred[held] = predict(sp, coef, r[held], q[held], shape)
    m = np.isin(q, qs)
    out = score_bands(pred[m], peak[m], exclude, q[m])
    out["river only"] = river_only(pred[m], peak[m], exclude, r[m], q[m])
    out["pred"] = pred
    return out


def river_only(pred, true, exclude, r, q):
    """The bankfull threshold itself: the runs with NO rain. Where the
    physics floods nothing outside the exclusion (below bankfull) the model
    must not either: count the runs where it does and its worst cell count.
    Where the physics does flood: mean IoU and cell counts."""
    m = r == 0
    keep = ~exclude
    wp = ((pred[m] >= THRESH) & keep).reshape(m.sum(), -1)
    wt = ((true[m] >= THRESH) & keep).reshape(m.sum(), -1)
    dry = wt.sum(axis=1) == 0
    inter = (wp & wt).sum(axis=1)
    union = np.maximum((wp | wt).sum(axis=1), 1)
    land = pred[m][:, keep]
    return {"n_dry": int(dry.sum()),
            "dry_max_depth": float(land[dry].max()) if dry.any() else 0.0,
            "false_alarm_runs": int((wp[dry].sum(axis=1) > 0).sum()),
            "false_alarm_max_cells": int(wp[dry].sum(axis=1).max())
            if dry.any() else 0,
            "n_wet": int((~dry).sum()),
            "iou_wet": float((inter / union)[~dry].mean())
            if (~dry).any() else float("nan"),
            "true_cells": wt[~dry].sum(axis=1).tolist(),
            "pred_cells": wp[~dry].sum(axis=1).tolist(),
            "q_wet": q[m][~dry].tolist()}


def sweep(spec, coef, exclude, shape, n_r=33, n_q=51):
    """Wet-cell count outside the exclusion over the whole slider range, to
    catch what a 50-run validation set cannot: a badly determined corner.
    More rain or more river never floods fewer cells in the physics table,
    so count the places where the model's count DROPS along either axis."""
    import surrogate
    rr = np.linspace(0, surrogate.RAIN_MULT_MAX, n_r)
    qq = np.linspace(0, surrogate.Q_MAX, n_q)
    keep = ~exclude.ravel()
    cnt = np.empty((n_q, n_r))
    lo = np.inf
    for i, qv in enumerate(qq):
        raw = features(rr, np.full(n_r, qv), spec) @ coef
        lo = min(lo, float(raw[:, keep].min()))
        cnt[i] = ((raw >= THRESH) & keep).sum(axis=1)
    dr, dq = np.diff(cnt, axis=1), np.diff(cnt, axis=0)
    return {"drop_r_max": max(float(-dr.min()), 0.0),
            "drop_q_max": max(float(-dq.min()), 0.0),
            "drops_over_20": int((dr < -20).sum() + (dq < -20).sum()),
            "most_negative_raw_m": lo, "counts": cnt}


def _row(name, sb):
    cells = [f"{name:44s}"]
    for key in ("overall", *[b[0] for b in BANDS]):
        s = sb[key]
        cells.append("      -      " if s is None else
                     f"{s['iou']:.3f}/{s['iou_pooled']:.3f}/{s['rmse']:.3f}"
                     f"/{s['rmse_wet']:.3f}")
    return "  ".join(cells)


def _header(title):
    print("\n" + title)
    print(f"{'IoU mean/IoU pooled/RMSE m/RMSE wet cells':44s}  "
          f"{'overall':23s}  {'below':23s}  {'around':23s}  "
          f"{'well above':23s}")


def evaluate(case="delhi", verbose=True):
    """CV table on train, then the held-out table. Returns a dict with the
    chosen spec name and all the numbers."""
    tr, va = load(case)
    ex = exclude_mask(case)
    r, q, peak = tr["rain_mult"], tr["river_q"], tr["peak"]
    rv, qv, pv = va["rain_mult"], va["river_q"], va["peak"]
    shape = peak.shape[1:]
    Y = peak.reshape(len(r), -1)

    cv = {name: cross_validate(spec, r, q, peak, ex)
          for name, spec in SPECS.items()}
    mean_field = np.broadcast_to(peak.mean(axis=0), pv.shape)
    held = {"mean-field baseline": score_bands(mean_field, pv, ex, qv)}
    fits = {}
    for name, spec in SPECS.items():
        fits[name] = fit(spec, r, q, Y)
        held[name] = score_bands(predict(*fits[name], rv, qv, shape), pv, ex,
                                 qv)
    cv_best = max(cv, key=lambda n: cv[n]["overall"]["iou"])
    chosen = cv_best
    if cv[PREFERRED]["overall"]["iou"] >= \
            cv[cv_best]["overall"]["iou"] - PREFER_TOL:
        chosen = PREFERRED
    if verbose:
        print("\nNO-RAIN RUNS (the bankfull threshold), from the CV "
              "predictions; and wet-cell-count drops over the slider range")
        for name in SPECS:
            ro = cv[name]["river only"]
            sw = sweep(*fits[name], ex, shape)
            print(f"{name:44s}  below bankfull: false alarms in "
                  f"{ro['false_alarm_runs']}/{ro['n_dry']} runs (worst "
                  f"{ro['false_alarm_max_cells']} cells, deepest "
                  f"{ro['dry_max_depth']:.2f} m); flooding runs: "
                  f"IoU {ro['iou_wet']:.3f} over {ro['n_wet']}; sweep: max "
                  f"drop {sw['drop_r_max']:.0f} cells along rain, "
                  f"{sw['drop_q_max']:.0f} along river, "
                  f"{sw['drops_over_20']} drops > 20 cells")
        low = rv < 0.5
        print(f"held-out runs with under 48 mm of rain (n={int(low.sum())}"
              f"), chosen model, per run  q / r / physics cells / IoU:")
        ps = held[chosen]["overall"]["per_sample"]
        wt = ((pv >= THRESH) & ~ex).reshape(len(rv), -1).sum(axis=1)
        print("   " + "; ".join(f"{qv[i]:.0f}/{rv[i]:.2f}/{wt[i]}/{ps[i]:.2f}"
                                for i in np.nonzero(low)[0]))
        _header(f"CROSS-VALIDATION on the {len(r)} training runs "
                f"(leave discharges out) - used to choose the model")
        for name in SPECS:
            print(_row(name, cv[name]))
        print(f"best by CV: {cv_best}; chosen: {chosen}"
              + ("" if chosen == cv_best else
                 f" (within {PREFER_TOL} of the best; preferred because it "
                 f"reproduces the no-rain runs)"))
        _header(f"HELD-OUT: fitted on {len(r)} runs, scored on {len(rv)} "
                f"validation runs, cells outside the exclusion mask "
                f"({int(ex.sum())} of {ex.size} cells excluded)")
        for name in held:
            print(_row(name, held[name]))
        o = held[chosen]
        print("samples scored / both-empty (left out of the IoU mean): "
              + ", ".join(f"{k.split(' (')[0]} {o[k]['n_scored']}/"
                          f"{o[k]['n_empty']}" for k in o if o[k]))
        print("mean wet cells outside the exclusion, physics vs chosen "
              "model: " + ", ".join(
                  f"{k.split(' (')[0]} {o[k]['true_cells']:.0f} vs "
                  f"{o[k]['pred_cells']:.0f}" for k in o if o[k]))
    return {"chosen": chosen, "cv": cv, "held": held, "fits": fits,
            "exclude": ex, "n_train": len(r), "n_val": len(rv)}


def per_pixel_poly(case="delhi", degree="cubic"):
    """Held-out score of the plain per-pixel polynomial (kept for
    comparison). Returns (iou, rmse, coef)."""
    tr, va = load(case)
    ex = exclude_mask(case)
    spec = {"kind": "cubic" if degree == "cubic" else "quad"}
    sp, coef = fit(spec, tr["rain_mult"], tr["river_q"],
                   tr["peak"].reshape(len(tr["peak"]), -1))
    s = score(predict(sp, coef, va["rain_mult"], va["river_q"],
                      va["peak"].shape[1:]), va["peak"], ex)
    print(f"[baseline] per-pixel {degree} poly: IoU {s['iou']:.3f}  "
          f"RMSE {s['rmse']:.3f} m")
    return s["iou"], s["rmse"], coef


def ship_decision(held, chosen):
    o = held[chosen]
    above = o[BANDS[2][0]]
    base = held["mean-field baseline"]["overall"]["iou"]
    checks = {
        f"overall IoU {o['overall']['iou']:.3f} >= {SHIP_IOU_ALL}":
            o["overall"]["iou"] >= SHIP_IOU_ALL,
        f"well-above-bankfull IoU {above['iou']:.3f} >= {SHIP_IOU_ABOVE}":
            above["iou"] >= SHIP_IOU_ABOVE,
        f"overall IoU beats mean-field {base:.3f} by >= {SHIP_MARGIN}":
            o["overall"]["iou"] - base >= SHIP_MARGIN,
    }
    return all(checks.values()), checks


DEFAULT_RAIN_MM = 0.0       # panel default: a normal day (12 mm of the
                            # design storm already ponds ~85 cells)
DEFAULT_RIVER_Q = 275.0     # ~ the routed discharge on a normal day
K_MODES = (16, 24, 32, 48, 64, 96)
K_TOLERANCE = 0.005         # smallest k whose CV IoU is within this of full


def choose_modes(case, spec):
    """Smallest number of spatial modes whose leave-discharges-out CV IoU
    (training set only) is within K_TOLERANCE of the uncompressed fit."""
    tr, _ = load(case)
    ex = exclude_mask(case)
    r, q, peak = tr["rain_mult"], tr["river_q"], tr["peak"]
    full = cross_validate(spec, r, q, peak, ex)["overall"]["iou"]
    for k in K_MODES:
        got = cross_validate(spec, r, q, peak, ex, k_modes=k)
        print(f"[surrogate] {k:3d} modes: CV IoU "
              f"{got['overall']['iou']:.3f} (uncompressed {full:.3f})")
        if got["overall"]["iou"] >= full - K_TOLERANCE:
            return k
    return K_MODES[-1]


def export_model(res, ship, case="delhi"):
    """Write the chosen model, fitted on the TRAINING runs only (exactly the
    model the held-out table scored), for the viewer's JS forward pass.

    Layout: the coefficient matrix (F features x N cells) is factored as
    A (F x k) @ modes (k x N). aB64 = A, float32, row-major (feature, mode);
    modesB64 = k blocks of rows*cols float32, each NORTH-row-first (flipud
    of the physics grid, which is row 0 = south) like every other grid in
    viewer3d.py. depth = max(0, (phi(r, q) @ A) @ modes).

    ship=False writes <case>.rejected.json instead and removes <case>.json,
    so viewer3d._load_surrogate() returns None and the panel is not shown.
    """
    import surrogate

    tr, va = load(case)
    ex = res["exclude"]
    name = res["chosen"]
    spec, coef = res["fits"][name]
    rows, cols = tr["elevation"].shape
    shape = (rows, cols)
    k = choose_modes(case, SPECS[name])
    A, M = compress(coef, k)
    # score exactly what is shipped (float32, compressed)
    A32, M32 = A.astype("<f4"), M.astype("<f4")
    rv, qv = va["rain_mult"], va["river_q"]
    pred = np.clip((features(rv, qv, spec).astype("<f4") @ A32) @ M32, 0,
                   None).reshape(len(rv), *shape)
    sb = score_bands(pred, va["peak"], ex, qv)
    _header(f"SHIPPED FORM ({name}, {k} spatial modes, float32), held-out")
    print(_row("as exported", sb))
    print(_row("uncompressed", res["held"][name]))
    print(_row("mean-field baseline", res["held"]["mean-field baseline"]))
    ok2, checks = ship_decision({**res["held"], name: sb}, name)
    for text, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] (as exported) {text}")
    ship = ship and ok2

    M_north = M32.reshape(k, rows, cols)[:, ::-1, :]
    bands = {b[0].split(" (")[0]: sb[b[0]] for b in BANDS}
    out = {
        "case": case, "rows": rows, "cols": cols,
        "kind": spec["kind"], "name": name,
        "knots_q": spec.get("knots_q"), "r_basis": spec.get("r"),
        "r_degree": spec.get("r_degree"), "knots_r": spec.get("knots_r"),
        "q_bankfull": spec.get("q_bankfull"), "q_scale": Q_SCALE,
        "n_features": int(A.shape[0]), "k": int(k),
        "aB64": base64.b64encode(A32.tobytes()).decode(),
        "modesB64": base64.b64encode(
            np.ascontiguousarray(M_north).tobytes()).decode(),
        "rain_mult_max": surrogate.RAIN_MULT_MAX,
        "rain_mm_per_unit": float(tr["rain_mm_per_unit"]),
        "river_qmax": surrogate.Q_MAX,
        "default_rain_mm": DEFAULT_RAIN_MM,
        "default_river_q": DEFAULT_RIVER_Q,
        "metrics": {
            "n_train": res["n_train"], "n_val": res["n_val"],
            "iou": sb["overall"]["iou"],
            "iou_pooled": sb["overall"]["iou_pooled"],
            "rmse_m": sb["overall"]["rmse"],
            "rmse_wet_m": sb["overall"]["rmse_wet"],
            "n_scored": sb["overall"]["n_scored"],
            "n_empty": sb["overall"]["n_empty"],
            "iou_mean_field":
                res["held"]["mean-field baseline"]["overall"]["iou"],
            "bands": {b: {"iou": s["iou"], "iou_pooled": s["iou_pooled"],
                          "rmse_m": s["rmse"], "rmse_wet_m": s["rmse_wet"],
                          "n_scored": s["n_scored"],
                          "n_empty": s["n_empty"]}
                      for b, s in bands.items() if s},
            "thresh_m": THRESH,
        },
    }
    os.makedirs(MODEL_DIR, exist_ok=True)
    live = os.path.join(MODEL_DIR, f"{case}.json")
    rejected = os.path.join(MODEL_DIR, f"{case}.rejected.json")
    path = live if ship else rejected
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    other = rejected if ship else live
    if os.path.exists(other):
        os.remove(other)
    print(f"[surrogate] {case}: {'SHIPPED' if ship else 'NOT SHIPPED'} -> "
          f"{path} ({os.path.getsize(path) / 1024:.0f} KB)")
    return out


if __name__ == "__main__":
    res = evaluate()
    ok, checks = ship_decision(res["held"], res["chosen"])
    for text, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {text}")
    print("SHIP" if ok else "DO NOT SHIP")
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_model(res, ok)
