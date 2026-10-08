"""Day 2: backtest HydroTwin's physics against the real July 2023 Delhi
flood, per BACKTEST_PREREG.md. Run after that file's rules are frozen.

Rain forcing: IMD/Open-Meteo-archive daily totals for Delhi, 6-16 July 2023
(fetched 2026-10-07), spread evenly across each day as mm/hr.

River forcing: no public hourly/daily Delhi-stretch discharge series was
found (see BACKTEST_PREREG.md), so a symmetric triangular hydrograph is
used: baseline (seasonal median, i.e. zero excess) -> rises 48h -> peaks
-> falls 48h -> baseline. Peak excess Q is the ONE calibrated number,
tuned so modelled peak stage at the Old Railway Bridge (ORB) cell matches
the observed 208.66 m HFL. ORB stage is therefore a calibration target,
not a reported result; the site hit/miss table is the independent check.
"""

import numpy as np

import config
import river
import simulate
import terrain

ORB_LATLON = (28.6636, 77.2487)          # Old Iron Bridge / Loha Pul (OSM)
OBSERVED_ORB_M = 208.66

# Daily rain totals, Delhi, 2023-07-06..07-16 (Open-Meteo archive, fetched
# 2026-10-07). Index 0 = 07-06.
RAIN_DAILY_MM = [2.9, 3.2, 36.1, 22.3, 30.7, 2.4, 8.9, 5.7, 12.1, 16.4, 15.3]
PEAK_DAY = 5          # 07-11 (HKB peak release day) -> river hydrograph peaks here
RISE_H, FALL_H = 48, 48
DURATION_H = len(RAIN_DAILY_MM) * 24     # 264 h = 11 days

SITES = {
    # name: (lat, lon, group)
    "Yamuna Bazar": (28.6620, 77.2394, "A"),
    "Kashmere Gate ISBT": (28.6687, 77.2304, "A"),
    "Majnu ka Tilla": (28.7043, 77.2245, "A"),
    "Red Fort (Ring Road)": (28.6561, 77.2408, "B"),
    "Civil Lines": (28.6807, 77.2226, "B"),
    "ITO": (28.6282, 77.2410, "C"),
    "Raj Ghat": (28.6442, 77.2498, "C"),
    "Connaught Place": (28.6318, 77.2194, "D"),
    "DU North Campus": (28.6925, 77.2182, "D"),
}
OBSERVED_FLOODED = {"Yamuna Bazar", "Kashmere Gate ISBT", "Majnu ka Tilla",
                    "Red Fort (Ring Road)", "Civil Lines", "ITO", "Raj Ghat"}


def rain_mm_hr_at(t_seconds):
    day = min(int(t_seconds // 86400), len(RAIN_DAILY_MM) - 1)
    return RAIN_DAILY_MM[day] / 24.0


def river_q_at(t_seconds, peak_q):
    h = t_seconds / 3600.0
    peak_h = PEAK_DAY * 24.0
    if h < peak_h - RISE_H or h > peak_h + FALL_H:
        return 0.0
    if h <= peak_h:
        return peak_q * (h - (peak_h - RISE_H)) / RISE_H
    return peak_q * (1.0 - (h - peak_h) / FALL_H)


def setup(conditioned=False):
    """conditioned=False (default) is the pre-registered setup: the raw
    pipeline DEM. conditioned=True is the POST-HOC variant (see
    BACKTEST_PREREG.md): the same DEM with the river bed carved the way the
    live pipeline does it (scenarios.condition_terrain, cached OSM mask),
    and the inflow cells found on that conditioned DEM, as run.py does."""
    config.set_case("delhi")
    elevation, cell_size, terrain_source = terrain.load_terrain()
    if conditioned:
        import scenarios

        water_mask = scenarios.fetch_water_mask(elevation, cell_size)
        if not water_mask.any():
            raise RuntimeError("no OSM water mask: the outlet for channel "
                               "conditioning cannot be located")
        saved = config.CHANNEL_CONDITIONING
        config.CHANNEL_CONDITIONING = True
        try:
            elevation, terrain_source, channel = scenarios.condition_terrain(
                elevation, cell_size, terrain_source, water_mask)
        finally:
            config.CHANNEL_CONDITIONING = saved
        if channel is None:
            raise RuntimeError("channel conditioning did not run")
    inflow = river.find_inflow(elevation, cell_size)
    orb_rc = terrain.latlon_to_rc(*ORB_LATLON, *elevation.shape)
    return elevation, cell_size, terrain_source, inflow, orb_rc


def run_once(peak_q, elevation, cell_size, inflow, save_every_s=6 * 3600.0,
            duration_h=DURATION_H):
    times, depths = simulate.run_simulation(
        elevation, cell_size, rain_mm_hr_at, duration_s=duration_h * 3600.0,
        save_every_s=save_every_s, inflow=inflow,
        inflow_m3s_at=lambda t: river_q_at(t, peak_q))
    return times, depths


def orb_stage(depths, elevation, orb_rc):
    peak_depth = max(float(d[orb_rc]) for d in depths)
    return float(elevation[orb_rc]) + peak_depth


def calib_trial(peak_q, save_every_h=24.0, conditioned=False):
    """Importable (for ProcessPoolExecutor on Windows spawn) single trial:
    fresh setup + one run, returns (peak_q, orb_stage_m)."""
    elevation, cell_size, terrain_source, inflow, orb_rc = setup(conditioned)
    _, depths = run_once(peak_q, elevation, cell_size, inflow,
                         save_every_s=save_every_h * 3600.0)
    return peak_q, orb_stage(depths, elevation, orb_rc)


if __name__ == "__main__":
    import sys

    elevation, cell_size, terrain_source, inflow, orb_rc = setup()
    print(f"[backtest] terrain={terrain_source}  ORB cell={orb_rc} "
          f"bed={elevation[orb_rc]:.2f} m  target stage={OBSERVED_ORB_M} m")

    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        lo, hi = 0.0, 20000.0
        for it in range(10):
            mid = (lo + hi) / 2
            _, depths = run_once(mid, elevation, cell_size, inflow,
                                 save_every_s=12 * 3600.0)
            stage = orb_stage(depths, elevation, orb_rc)
            print(f"[calibrate] it{it} peak_q={mid:.0f}  ORB stage="
                  f"{stage:.3f} m  (target {OBSERVED_ORB_M})")
            if abs(stage - OBSERVED_ORB_M) < 0.10:
                print(f"[calibrate] CONVERGED peak_q={mid:.0f}")
                break
            if stage < OBSERVED_ORB_M:
                lo = mid
            else:
                hi = mid
