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
    import rainfall
    import simulate
    import terrain
    import viewer3d
    import visualize

    elevation, cell_size, terrain_source = terrain.load_terrain()
    rain_at, rain_series, rain_source = rainfall.get_rainfall()

    times, depths = simulate.run_simulation(elevation, cell_size, rain_at)
    simulate.save_checkpoint(times, depths, elevation, cell_size)

    decisions, decision_source = decide.get_decisions(depths, times)
    decisions_path = os.path.join(config.OUTPUT_DIR, "decisions.json")
    with open(decisions_path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in decisions.items() if k != "peak_index"},
                  f, indent=2)

    viewer_path = None
    try:
        viewer_path = viewer3d.make_3d_viewer(
            times, depths, elevation, cell_size, decisions,
            rain_series, rain_source, terrain_source)
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
    return {
        "case": name, "title": case["title"],
        "terrain": terrain_source, "rain": rain_source,
        "rain_total_mm": sum(rain_series),
        "peak_depth_m": float(peak.max()),
        "flooded_cells": int((peak > config.FLOOD_DEPTH_M).sum()),
        "decisions": decision_source,
        "n_zones": len(decisions.get("evacuation_zones", [])),
        "alert": decisions.get("public_alert", ""),
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

    print("\n" + "=" * 64)
    print("HYDROTWIN SUMMARY")
    print("=" * 64)
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
