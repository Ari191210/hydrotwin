"""Landlab OverlandFlow driver for HydroTwin.

Runs 2D shallow-water overland flow (de Almeida et al. scheme) over the loaded
terrain, forced by a rainfall time series, and returns depth snapshots.
"""

import os

import numpy as np
from landlab import RasterModelGrid
from landlab.components import OverlandFlow

import config

MM_HR_TO_M_S = 1.0 / 1000.0 / 3600.0


H_INIT_M = 1e-5            # thin film OverlandFlow adds to every node at init


def _start_depth(initial_depth, shape):
    """Node depth field that, once OverlandFlow has added its H_INIT_M film,
    reproduces `initial_depth` (a depth grid from an earlier run)."""
    d = np.asarray(initial_depth, dtype=float)
    if d.shape != tuple(shape):
        raise ValueError(f"initial_depth shape {d.shape} != grid {shape}")
    return np.maximum(d.flatten() - H_INIT_M, 1e-12)


def run_simulation(elevation, cell_size, rain_mm_hr_at, duration_s=None,
                   save_every_s=None, inflow=None, inflow_m3s_at=None,
                   initial_depth=None, initial_discharge=None):
    """Run OverlandFlow and return (times_s, depths).

    elevation      : 2D array (rows, cols), row 0 = south
    cell_size      : cell size in metres
    rain_mm_hr_at  : callable t_seconds -> rainfall intensity in mm/hr
    inflow         : river.find_inflow() result, or None
    inflow_m3s_at  : callable t_seconds -> river inflow in m3/s
    initial_depth  : optional depth grid (rows, cols) to start from instead
                     of dry ground, e.g. run_to_steady()["depth"]
    initial_discharge : optional link discharge (m2/s, one per grid link) to
                     start from, e.g. run_to_steady()["link_q"]; without it a
                     warm start has the water in place but at rest
    Returns times (list of s) and depths (list of 2D arrays, metres).
    """
    duration_s = duration_s or config.SIM_DURATION_HR * 3600.0
    save_every_s = save_every_s or config.SAVE_EVERY_S

    rows, cols = elevation.shape
    grid = RasterModelGrid((rows, cols), xy_spacing=cell_size)
    grid.add_field("topographic__elevation", elevation.flatten(), at="node")
    # Perimeter nodes default to open (fixed-value) boundaries: water exits the
    # domain at the edges. OverlandFlow needs a tiny nonzero starting depth.
    if initial_depth is None:
        grid.add_full("surface_water__depth", 1e-12, at="node")
    else:
        grid.add_field("surface_water__depth",
                       _start_depth(initial_depth, (rows, cols)), at="node")
    if inflow and inflow_m3s_at:
        # close the upstream edge across the channel, or the inflow would
        # drain straight back out of the boundary it entered by
        grid.status_at_node[inflow["closed"]] = grid.BC_NODE_IS_CLOSED
        in_nodes = np.asarray(inflow["nodes"])
    else:
        inflow_m3s_at, in_nodes = None, None

    of = OverlandFlow(grid, steep_slopes=True, mannings_n=config.MANNINGS_N)
    if initial_discharge is not None:
        # OverlandFlow zeroes the link discharge at init; put the flow back
        grid.at_link["surface_water__discharge"][:] = initial_discharge
    h = grid.at_node["surface_water__depth"]
    core = grid.core_nodes
    cell_area = cell_size * cell_size
    source = np.zeros(grid.number_of_nodes)

    times, depths = [], []
    elapsed, next_save, steps = 0.0, 0.0, 0
    vol_rain = vol_river = 0.0
    vol0 = float(h[core].sum()) * cell_area
    while elapsed < duration_s:
        rain = max(float(rain_mm_hr_at(elapsed)) * MM_HR_TO_M_S, 0.0)
        q_in = max(float(inflow_m3s_at(elapsed)), 0.0) \
            if inflow_m3s_at else 0.0
        if q_in > 0.0:
            # river inflow is a per-cell source (m/s) spread over the inlet
            source.fill(rain)
            source[in_nodes] += q_in / (len(in_nodes) * cell_area)
            of.rainfall_intensity = source
        else:
            of.rainfall_intensity = rain
        dt = min(of.calc_time_step(), config.DT_MAX_S, duration_s - elapsed)
        of.overland_flow(dt=dt)
        elapsed += dt
        steps += 1
        vol_rain += rain * dt * len(core) * cell_area
        vol_river += q_in * dt

        depth = grid.at_node["surface_water__depth"].reshape(rows, cols)
        if not np.isfinite(depth).all():
            raise RuntimeError(
                f"Solver produced non-finite depths at t={elapsed:.0f}s "
                f"(step {steps}) — reduce DT_MAX_S or check the terrain.")

        if elapsed >= next_save or elapsed >= duration_s:
            times.append(elapsed)
            depths.append(depth.copy())
            next_save = elapsed + save_every_s

    print(f"[simulate] {steps} solver steps over {elapsed / 3600.0:.2f} h, "
          f"{len(depths)} snapshots saved")
    stored = float(h[core].sum()) * cell_area - vol0
    print(f"[simulate] mass balance (Mm3): rain in {vol_rain / 1e6:.3f}"
          f" + river in {vol_river / 1e6:.3f} = stored {stored / 1e6:.3f}"
          f" + left the domain {(vol_rain + vol_river - stored) / 1e6:.3f}")
    return times, depths


def run_to_steady(elevation, cell_size, inflow, q_m3s, max_hours=None,
                  tol=None, check_every_s=3600.0, quiet=False):
    """Run a steady river inflow of q_m3s (no rain) from a dry start until
    the river is in steady state, and return the final state.

    Steady = outflow within `tol` of inflow, where outflow over each
    check_every_s window is inflow minus the change in stored volume (so
    "outflow matches inflow" and "stored volume has plateaued" are the same
    test), for two consecutive windows. Capped at max_hours of simulated
    time; `converged` says whether the criterion was met.

    Returns {"depth": (rows, cols) grid, "link_q": link discharge,
             "hours", "converged", "inflow_m3s", "outflow_m3s",
             "stored_m3", "history": [(hours, outflow_m3s), ..]}.
    """
    max_hours = config.STEADY_MAX_HOURS if max_hours is None else max_hours
    tol = config.STEADY_TOL if tol is None else tol
    rows, cols = elevation.shape
    grid = RasterModelGrid((rows, cols), xy_spacing=cell_size)
    grid.add_field("topographic__elevation", elevation.flatten(), at="node")
    grid.add_full("surface_water__depth", 1e-12, at="node")
    grid.status_at_node[inflow["closed"]] = grid.BC_NODE_IS_CLOSED
    in_nodes = np.asarray(inflow["nodes"])

    of = OverlandFlow(grid, steep_slopes=True, mannings_n=config.MANNINGS_N)
    h = grid.at_node["surface_water__depth"]
    core = grid.core_nodes
    cell_area = cell_size * cell_size
    source = np.zeros(grid.number_of_nodes)
    source[in_nodes] = q_m3s / (len(in_nodes) * cell_area)
    of.rainfall_intensity = source

    duration_s = max_hours * 3600.0
    elapsed, steps, ok_windows = 0.0, 0, 0
    vol0 = float(h[core].sum()) * cell_area
    win_t, win_vol = 0.0, vol0
    next_check = check_every_s
    outflow, history, converged = 0.0, [], False
    while elapsed < duration_s:
        dt = min(of.calc_time_step(), config.DT_MAX_S, next_check - elapsed)
        of.overland_flow(dt=dt)
        elapsed += dt
        steps += 1
        if elapsed >= next_check:
            if not np.isfinite(h).all():
                raise RuntimeError(
                    f"Solver produced non-finite depths at t={elapsed:.0f}s "
                    f"(steady run, {q_m3s:.0f} m3/s)")
            vol = float(h[core].sum()) * cell_area
            outflow = q_m3s - (vol - win_vol) / (elapsed - win_t)
            history.append((elapsed / 3600.0, outflow))
            win_t, win_vol = elapsed, vol
            next_check = min(elapsed + check_every_s, duration_s)
            ok_windows = ok_windows + 1 \
                if abs(outflow - q_m3s) <= tol * q_m3s else 0
            if ok_windows >= 2:
                converged = True
                break
    stored = float(h[core].sum()) * cell_area - vol0
    if not quiet:
        print(f"[simulate] steady run at {q_m3s:.1f} m3/s: "
              + (f"steady after {elapsed / 3600.0:.0f} h"
                 if converged else
                 f"NOT STEADY after {elapsed / 3600.0:.0f} h (cap)")
              + f", outflow {outflow:.1f} m3/s "
              f"({(outflow / q_m3s - 1) * 100:+.1f}% vs inflow), stored "
              f"{stored / 1e6:.2f} Mm3, {steps} solver steps")
    return {"depth": h.reshape(rows, cols).copy(),
            "link_q": grid.at_link["surface_water__discharge"].copy(),
            "hours": elapsed / 3600.0, "converged": converged,
            "inflow_m3s": float(q_m3s), "outflow_m3s": float(outflow),
            "stored_m3": stored, "history": history}


def save_checkpoint(times, depths, elevation, cell_size, path=None):
    """Persist depth grids to disk and print per-snapshot min/max depth."""
    path = path or os.path.join(config.OUTPUT_DIR, "depths.npz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, times=np.array(times), depths=np.stack(depths),
                        elevation=elevation, cell_size=cell_size)
    print(f"[simulate] Depth grids saved to {path}")
    print(f"{'t (min)':>8} {'min depth (m)':>14} {'max depth (m)':>14} "
          f"{'wet cells >30cm':>16}")
    for t, d in zip(times, depths):
        wet = int((d > config.FLOOD_DEPTH_M).sum())
        print(f"{t / 60.0:8.1f} {d.min():14.4f} {d.max():14.3f} {wet:16d}")
    return path
