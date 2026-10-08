"""Steady river states for HydroTwin: the bankfull footprint and warm starts.

Both are the same computation, simulate.run_to_steady on the conditioned
DEM with no rain, at two different discharges:

  bankfull footprint  q_bankfull - q_dem_baseline. Every cell wetter than
      config.BANKFULL_WET_M at steady state is "the river" (what it occupies
      at an ordinary annual high flow) and never counts as flooding.
  warm start          today's routed discharge. Its depth and link-discharge
      fields are the initial condition of every scenario, so the 6 h window
      shows the forecast and not an empty river bed filling up.

Steady states are cached in assets/spinup/, keyed on the grid, the discharge
and a hash of everything else that shapes the result (DEM, inflow cells,
Manning's n, timestep cap). The footprint is stored beside the OSM mask in
assets/masks/ with a JSON sidecar holding the discharge it was built for.
"""

import hashlib
import json
import os
import time

import numpy as np

import config
import simulate

_HERE = os.path.dirname(os.path.abspath(__file__))
SPINUP_DIR = os.path.join(_HERE, "assets", "spinup")
MASK_DIR = os.path.join(_HERE, "assets", "masks")


def _grid_key(shape):
    return (f"{config.BASIN_LAT:.4f}_{config.BASIN_LON:.4f}"
            f"_z{config.TERRAIN_ZOOM}_{shape[0]}x{shape[1]}")


def state_hash(elevation, cell_size, inflow):
    """Short hash of everything except the discharge that a steady state
    depends on."""
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(elevation, dtype=np.float64).tobytes())
    h.update(json.dumps([round(float(cell_size), 4), config.MANNINGS_N,
                         config.DT_MAX_S, config.STEADY_TOL,
                         config.STEADY_MAX_HOURS,
                         [int(n) for n in inflow["nodes"]],
                         [int(n) for n in inflow["closed"]]]).encode())
    return h.hexdigest()[:10]


def steady_state(elevation, cell_size, inflow, q_m3s, what="steady state"):
    """Cached simulate.run_to_steady. Adds "cached" (bool) and "seconds"
    (wall time of the simulation that produced it) to the result."""
    sha = state_hash(elevation, cell_size, inflow)
    path = os.path.join(
        SPINUP_DIR, f"{_grid_key(elevation.shape)}_q{q_m3s:.1f}_{sha}.npz")
    if os.path.exists(path):
        try:
            z = np.load(path, allow_pickle=False)
            meta = json.loads(str(z["meta"]))
            out = {**meta, "depth": z["depth"], "link_q": z["link_q"],
                   "cached": True}
            print(f"[riverstate] {what} at {q_m3s:.1f} m3/s: cached "
                  f"({os.path.basename(path)}; "
                  + (f"steady after {meta['hours']:.0f} h"
                     if meta["converged"] else
                     f"NOT steady after {meta['hours']:.0f} h")
                  + f", outflow {meta['outflow_m3s']:.1f} m3/s; took "
                  f"{meta['seconds']:.0f} s to compute)")
            return out
        except Exception as exc:
            print(f"[riverstate] cached state unreadable "
                  f"({type(exc).__name__}: {exc}) -> recomputing")
    t0 = time.time()
    print(f"[riverstate] {what}: running {q_m3s:.1f} m3/s to steady state "
          f"(cap {config.STEADY_MAX_HOURS:.0f} simulated hours) ...")
    out = simulate.run_to_steady(elevation, cell_size, inflow, q_m3s)
    out["seconds"] = time.time() - t0
    out["cached"] = False
    if not out["converged"]:
        print(f"[riverstate] !!! {what} at {q_m3s:.1f} m3/s did NOT reach "
              f"steady state in {out['hours']:.0f} h: outflow "
              f"{out['outflow_m3s']:.1f} vs inflow {q_m3s:.1f} m3/s !!!")
    print(f"[riverstate] {what} took {out['seconds']:.0f} s")
    meta = {k: v for k, v in out.items()
            if k not in ("depth", "link_q", "cached")}
    try:
        os.makedirs(SPINUP_DIR, exist_ok=True)
        np.savez_compressed(path, depth=out["depth"], link_q=out["link_q"],
                            meta=json.dumps(meta))
    except Exception as exc:
        print(f"[riverstate] could not cache the state "
              f"({type(exc).__name__}: {exc})")
    return out


def _footprint_paths(shape):
    base = os.path.join(MASK_DIR, _grid_key(shape) + "_bankfull")
    return base + ".npy", base + ".json"


def bankfull_footprint(elevation, cell_size, inflow, q_m3s=None):
    """(mask, info): bool grid of cells the river occupies at bankfull.

    q_m3s is the bankfull discharge above the DEM baseline; None means it is
    unknown (no GloFAS history reachable), in which case a footprint already
    on disk for this DEM is used as it stands. (None, None) when there is
    nothing to compute and nothing cached.
    """
    npy, side = _footprint_paths(elevation.shape)
    sha = state_hash(elevation, cell_size, inflow)
    if os.path.exists(npy) and os.path.exists(side):
        try:
            with open(side, encoding="utf-8") as f:
                info = json.load(f)
            mask = np.load(npy)
            same_q = q_m3s is None or abs(info["q_m3s"] - q_m3s) < 0.05
            if (mask.shape == elevation.shape and info["state_hash"] == sha
                    and info["wet_m"] == config.BANKFULL_WET_M and same_q):
                print(f"[riverstate] bankfull footprint: {int(mask.sum())} "
                      f"cells at {info['q_m3s']:.0f} m3/s above baseline "
                      f"(cached {os.path.basename(npy)})")
                return mask.astype(bool), info
            print("[riverstate] cached bankfull footprint is for a different "
                  "discharge, DEM or threshold -> recomputing")
        except Exception as exc:
            print(f"[riverstate] cached footprint unreadable "
                  f"({type(exc).__name__}: {exc}) -> recomputing")
    if q_m3s is None or q_m3s <= 0.0:
        return None, None
    st = steady_state(elevation, cell_size, inflow, round(q_m3s, 1),
                      what="bankfull footprint")
    mask = st["depth"] >= config.BANKFULL_WET_M
    info = {"q_m3s": round(q_m3s, 1), "wet_m": config.BANKFULL_WET_M,
            "state_hash": sha, "cells": int(mask.sum()),
            "hours": st["hours"], "converged": bool(st["converged"]),
            "inflow_m3s": st["inflow_m3s"], "outflow_m3s": st["outflow_m3s"],
            "stored_m3": st["stored_m3"],
            "max_depth_m": float(st["depth"][mask].max()) if mask.any()
            else 0.0,
            "seconds": st["seconds"]}
    print(f"[riverstate] bankfull footprint: {info['cells']} cells >= "
          f"{config.BANKFULL_WET_M} m at {q_m3s:.0f} m3/s above baseline "
          f"(max depth {info['max_depth_m']:.2f} m)")
    try:
        os.makedirs(MASK_DIR, exist_ok=True)
        np.save(npy, mask)
        with open(side, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=1)
    except Exception as exc:
        print(f"[riverstate] could not cache the footprint "
              f"({type(exc).__name__}: {exc})")
    return mask, info


def spinup_discharge(q_m3s):
    """Routed discharge rounded to the warm-start cache step."""
    step = config.SPINUP_Q_STEP_M3S
    return round(q_m3s / step) * step


def warm_start(elevation, cell_size, inflow, q_m3s):
    """Steady state at the routed discharge (rounded to
    config.SPINUP_Q_STEP_M3S, and computed AT that rounded value so the
    cached field is exactly what its key says), or None when nothing is
    routed."""
    q = spinup_discharge(q_m3s)
    if q <= 0.0:
        return None
    return steady_state(elevation, cell_size, inflow, float(q),
                        what="river warm start")
