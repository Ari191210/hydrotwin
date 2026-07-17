"""HydroTwin entry point.

    python run.py

Runs the full pipeline: terrain -> rainfall -> physics simulation ->
Claude evacuation decisions -> interactive map + animation.
Every external dependency (DEM download, Open-Meteo, Anthropic API) has an
offline fallback, so this always completes.
"""

import json
import os
import time

import config


def main():
    t0 = time.time()
    print("=" * 64)
    print("HydroTwin — physics-informed flood prediction demo")
    print(f"Basin: {config.BASIN_LAT}, {config.BASIN_LON} | "
          f"grid {config.GRID_ROWS}x{config.GRID_COLS} | "
          f"storm {config.SIM_DURATION_HR} h")
    print("=" * 64)

    # Phase 1 — terrain
    print("\n--- Phase 1: terrain " + "-" * 40)
    import terrain
    elevation, cell_size, terrain_source = terrain.load_terrain()

    # Phase 2 — rainfall forcing
    print("\n--- Phase 2: rainfall " + "-" * 39)
    import rainfall
    rain_at, rain_series, rain_source = rainfall.get_rainfall()

    # Phase 1+2 — physics simulation
    print("\n--- Simulation: Landlab OverlandFlow " + "-" * 24)
    import simulate
    times, depths = simulate.run_simulation(elevation, cell_size, rain_at)
    simulate.save_checkpoint(times, depths, elevation, cell_size)

    # Phase 3 — decisions
    print("\n--- Phase 3: evacuation decisions " + "-" * 27)
    import decide
    decisions, decision_source = decide.get_decisions(depths, times)
    decisions_path = os.path.join(config.OUTPUT_DIR, "decisions.json")
    with open(decisions_path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in decisions.items() if k != "peak_index"},
                  f, indent=2)

    # Phase 4 — visualization
    print("\n--- Phase 4: visualization " + "-" * 34)
    import visualize
    map_path = None
    try:
        map_path = visualize.make_folium_map(times, depths, elevation,
                                             cell_size, decisions)
    except Exception as exc:
        print(f"[visualize] Interactive map failed "
              f"({type(exc).__name__}: {exc}) — animation is the fallback")
    gif_path, mp4_path = visualize.make_animation(times, depths, elevation,
                                                  cell_size, decisions)

    # Summary
    peak = depths[decisions["peak_index"]]
    n_evac = len(decisions.get("evacuation_zones", []))
    print("\n" + "=" * 64)
    print("HYDROTWIN SUMMARY")
    print("=" * 64)
    print(f"  Terrain source   : {terrain_source}")
    print(f"  Rainfall source  : {rain_source} "
          f"(total {sum(rain_series):.1f} mm)")
    print(f"  Peak flood depth : {peak.max():.2f} m "
          f"({int((peak > config.FLOOD_DEPTH_M).sum())} cells "
          f"> {config.FLOOD_DEPTH_M} m)")
    print(f"  Decisions source : {decision_source} "
          f"({n_evac} zones flagged)")
    print(f"  Public alert     : {decisions.get('public_alert', '')}")
    print("\n  Outputs:")
    for label, p in (("Interactive map", map_path),
                     ("Animation (GIF)", gif_path),
                     ("Animation (MP4)", mp4_path),
                     ("Decisions JSON", decisions_path),
                     ("Depth grids", os.path.join(config.OUTPUT_DIR,
                                                  "depths.npz"))):
        if p:
            print(f"    {label:16s}: {os.path.abspath(p)}")
    print(f"\n  Done in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
