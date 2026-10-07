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


def run_simulation(elevation, cell_size, rain_mm_hr_at, duration_s=None,
                   save_every_s=None, inflow=None, inflow_m3s_at=None):
    """Run OverlandFlow and return (times_s, depths).

    elevation      : 2D array (rows, cols), row 0 = south
    cell_size      : cell size in metres
    rain_mm_hr_at  : callable t_seconds -> rainfall intensity in mm/hr
    inflow         : river.find_inflow() result, or None
    inflow_m3s_at  : callable t_seconds -> river inflow in m3/s
    Returns times (list of s) and depths (list of 2D arrays, metres).
    """
    duration_s = duration_s or config.SIM_DURATION_HR * 3600.0
    save_every_s = save_every_s or config.SAVE_EVERY_S

    rows, cols = elevation.shape
    grid = RasterModelGrid((rows, cols), xy_spacing=cell_size)
    grid.add_field("topographic__elevation", elevation.flatten(), at="node")
    # Perimeter nodes default to open (fixed-value) boundaries: water exits the
    # domain at the edges. OverlandFlow needs a tiny nonzero starting depth.
    grid.add_full("surface_water__depth", 1e-12, at="node")
    if inflow and inflow_m3s_at:
        # close the upstream edge across the channel, or the inflow would
        # drain straight back out of the boundary it entered by
        grid.status_at_node[inflow["closed"]] = grid.BC_NODE_IS_CLOSED
        in_nodes = np.asarray(inflow["nodes"])
    else:
        inflow_m3s_at, in_nodes = None, None

    of = OverlandFlow(grid, steep_slopes=True, mannings_n=config.MANNINGS_N)
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
