"""HydroTwin entry point.

    python run.py              # runs all three demo cases
    python run.py delhi        # runs one case (rishikesh | delhi | hue)

Pipeline per case: terrain -> rainfall -> physics simulation ->
Claude evacuation decisions -> 3D viewer + interactive map + animation.
Every external dependency (DEM download, Open-Meteo, Anthropic API) has an
offline fallback, so this always completes.
"""

import json
import os
import sys
import time

import numpy as np

import config


def run_case(name):
    t0 = time.time()
    case = config.set_case(name)
    print("\n" + "=" * 64)
    print(f"CASE: {name} — {case['title']}")
    print(f"  ({config.BASIN_LAT}, {config.BASIN_LON}) | "
          f"grid {config.GRID_ROWS}x{config.GRID_COLS} | "
          f"storm {config.SIM_DURATION_HR} h")
    print("=" * 64)

    import decide
    import imagery
    import rainfall
    import scenarios as scen
    import simulate
    import terrain
    import viewer3d
    import visualize

    import flooddata

    elevation, cell_size, terrain_source = terrain.load_terrain()
    config.POIS = scen.resolve_pois(config.POIS, elevation.shape)
    sat = imagery.get_imagery()
    water_mask = scen.fetch_water_mask(elevation, cell_size)
    # river cases only: make the DEM channel hydraulically continuous
    elevation, terrain_source, channel = scen.condition_terrain(
        elevation, cell_size, terrain_source, water_mask)
    rain = rainfall.get_rainfall()
    discharge = flooddata.get_river_discharge()
    inflow, q_in, river_label = scen.river_inflow(elevation, cell_size,
                                                  discharge)
    # river cases only (both None otherwise): what the river occupies at
    # bankfull, and the river already flowing at today's routed discharge
    footprint = scen.river_footprint(elevation, cell_size, inflow, discharge,
                                     channel)
    initial = scen.river_warm_start(elevation, cell_size, inflow, q_in,
                                    channel)
    # river channel, its bankfull footprint and the inflow cells: rendered,
    # but never counted as flooding
    exclude = scen.exclude_mask(water_mask, elevation.shape, inflow, q_in,
                                footprint)

    # The default scenario is the forecast as issued (the only one that may
    # call Claude); the rest are labelled what-ifs.
    scenarios = scen.run_all(scen.plan(rain), elevation, cell_size,
                             inflow, q_in, exclude=exclude, initial=initial)
    # Delhi only: the saved July 2023 backtest run as one more scenario
    # (read from disk, nothing simulated; None for every other case)
    try:
        import replay
        past = replay.scenario(elevation, cell_size, exclude)
    except Exception as exc:
        past = None
        print(f"[replay] July 2023 replay SKIPPED "
              f"({type(exc).__name__}: {exc})")
    if past is not None:
        scenarios.append(past)

    default = next(s for s in scenarios if s["is_default"])
    rain_source = default["rain_source"]
    times, depths = default["times"], default["depths"]
    decisions, decision_source = default["decisions"], default["decision_source"]
    rain_series = default["rain_series"]
    simulate.save_checkpoint(times, depths, elevation, cell_size)

    decisions_path = os.path.join(config.OUTPUT_DIR, "decisions.json")
    with open(decisions_path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in decisions.items() if k != "peak_index"},
                  f, indent=2)

    viewer_path = None
    try:
        viewer_path = viewer3d.make_3d_viewer(
            scenarios, elevation, cell_size, terrain_source,
            discharge=discharge, river=river_label, imagery=sat,
            water_mask=exclude)
    except Exception as exc:
        print(f"[viewer3d] 3D viewer failed ({type(exc).__name__}: {exc}) "
              f"— 2D map + animation still produced")

    map_path = None
    try:
        map_path = visualize.make_folium_map(times, depths, elevation,
                                             cell_size, decisions)
    except Exception as exc:
        print(f"[visualize] Interactive map failed "
              f"({type(exc).__name__}: {exc}) — animation is the fallback")
    gif_path, mp4_path = visualize.make_animation(times, depths, elevation,
                                                  cell_size, decisions)

    peak = depths[decisions["peak_index"]]
    land_peak = decide.land_depth(peak, exclude)   # channel water excluded
    flooded_km2 = float((land_peak > config.FLOOD_DEPTH_M).sum()) \
        * cell_size * cell_size / 1e6
    return {
        "case": name, "title": case["title"],
        "terrain": terrain_source, "rain": rain_source,
        "rain_total_mm": sum(rain_series),
        "peak_depth_m": float(land_peak.max()),
        "flooded_cells": int((land_peak > config.FLOOD_DEPTH_M).sum()),
        "flooded_km2": flooded_km2,
        "people_est": int(flooded_km2 * config.POP_DENSITY_KM2),
        "pop_density": config.POP_DENSITY_KM2,
        "decisions": decision_source,
        "n_zones": len(decisions.get("evacuation_zones", [])),
        "alert": decisions.get("public_alert", ""),
        "elevation": elevation, "cell_size": cell_size, "peak_grid": peak,
        "imagery": sat,
        "calm": not any(z["priority"] in ("immediate", "high")
                        for z in decisions.get("evacuation_zones", [])),
        "replay_grid": next((np.maximum.reduce(s["depths"])
                             for s in scenarios if s.get("replay")), None),
        "outputs": {"3D viewer": viewer_path, "2D map": map_path,
                    "GIF": gif_path, "MP4": mp4_path,
                    "decisions": decisions_path},
        "seconds": time.time() - t0,
    }


def main():
    args = [a.lower() for a in sys.argv[1:]]
    cases = args if args else config.DEFAULT_CASES
    for name in cases:
        if name not in config.CASES:
            print(f"Unknown case '{name}'. Available: "
                  f"{', '.join(config.CASES)}")
            sys.exit(1)

    print("HydroTwin — physics-informed flood prediction demo")
    print(f"Running case(s): {', '.join(cases)}")

    results = []
    for name in cases:
        try:
            results.append(run_case(name))
        except Exception as exc:
            print(f"\n[run] CASE '{name}' FAILED "
                  f"({type(exc).__name__}: {exc}) — continuing with the rest")

    hub_path = None
    if results:
        try:
            import hub
            hub_path = hub.make_hub(results)
            try:
                import doorstep
                doorstep.build()
            except Exception as exc:
                print(f"[doorstep] page not built ({type(exc).__name__}: "
                      f"{exc}) - run stagelib.py build srtm first")
        except Exception as exc:
            print(f"[hub] Landing page failed ({type(exc).__name__}: {exc}) "
                  f"— per-case viewers unaffected")

    print("\n" + "=" * 64)
    print("HYDROTWIN SUMMARY")
    print("=" * 64)
    if hub_path:
        print(f"\n  START HERE: {os.path.abspath(hub_path)}")
    for r in results:
        print(f"\n  {r['case']} — {r['title']}  ({r['seconds']:.0f} s)")
        print(f"    terrain {r['terrain']} | rain {r['rain']} "
              f"({r['rain_total_mm']:.0f} mm)")
        print(f"    peak depth {r['peak_depth_m']:.2f} m | "
              f"{r['flooded_cells']} cells flooded | "
              f"{r['n_zones']} zones flagged ({r['decisions']})")
        print(f"    ALERT: {r['alert']}")
        for label, p in r["outputs"].items():
            if p:
                print(f"      {label:10s}: {os.path.abspath(p)}")
    if not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
