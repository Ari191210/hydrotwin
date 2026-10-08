"""Scenario planning shared by run.py (static presets) and engine.py (live).

The default scenario is always the forecast as issued (x1). Anything else is
a labelled what-if. When the forecast is too dry to show a flood, the
design storm is offered as a what-if; it never replaces the forecast.
"""

import time

import numpy as np

import config
import decide
import rainfall
import river
import simulate
import terrain


def resolve_pois(pois, shape):
    """Snap lat/lon POIs to grid cells; pass row/col POIs through."""
    out = []
    for p in pois:
        if "row" in p:
            out.append(dict(p))
            continue
        rc = terrain.latlon_to_rc(p["lat"], p["lon"], *shape)
        if rc is None:
            print(f"[scenarios] POI {p['name']} is outside the grid -> skipped")
            continue
        out.append({**p, "row": rc[0], "col": rc[1]})
    return out


def plan(rain):
    """rain: rainfall.get_rainfall() dict -> list of scenario specs."""
    design = rainfall.design_storm()
    if rain["series"] is None:              # no forecast at all
        return [
            _spec("Design storm", 1.0, design, rainfall.DESIGN_SOURCE,
                  whatif=True, default=True),
            _spec("Design ×2", 2.0, design, rainfall.DESIGN_SOURCE,
                  whatif=True),
        ]
    fc = rain["series"]
    specs = [_spec("Forecast", 1.0, fc, rain["source"], default=True)]
    if sum(fc) >= config.MIN_DEMO_RAIN_MM:
        specs += [_spec(f"×{m:g}", m, fc, rain["source"], whatif=True)
                  for m in config.WHATIF_MULTIPLIERS if m != 1.0]
    else:
        specs += [_spec("Design storm", 1.0, design, rainfall.DESIGN_SOURCE,
                        whatif=True),
                  _spec("Design ×2", 2.0, design, rainfall.DESIGN_SOURCE,
                        whatif=True)]
    return specs


def _spec(label, mult, base, source, whatif=False, default=False):
    return {"label": label, "mult": mult,
            "rain_series": [r * mult for r in base], "rain_source": source,
            "whatif": whatif, "is_default": default}


def river_inflow(elevation, cell_size, discharge):
    """(inflow_info, q_m3s, label). inflow_info is None when the river is not
    modelled at this location."""
    info = river.find_inflow(elevation, cell_size)
    if info is None:
        return None, 0.0, "not modelled at this location (rain only)"
    q, label = river.excess_from_glofas(discharge)
    info["q_m3s"] = round(q, 1)
    return info, q, label


def fetch_water_mask(elevation, cell_size, tries=3):
    """river.water_mask with retries: Overpass 504s often, and an empty mask
    silently makes the river channel count as flooded land again."""
    for i in range(tries):
        mask = river.water_mask(elevation, cell_size)
        if mask.any():
            return mask
        # empty = 504, or a 200 with no elements (Overpass's own timeout);
        # indistinguishable from "no water here", so retry either way
        if i < tries - 1:
            print(f"[scenarios] empty water mask -> retry {i + 2}/{tries}")
            time.sleep(3 * (i + 1))
    print("[scenarios] !!! NO WATER MASK after "
          f"{tries} tries (Overpass down, or no water mapped here): any "
          "river/lake cells WILL COUNT AS FLOODED in the stats, zones and "
          "alert !!!")
    return mask


CONDITIONED_TAG = " + river channel conditioned"


def condition_terrain(elevation, cell_size, terrain_source, water_mask=None):
    """(elevation, terrain_source, diagnostics) with the river channel
    hydro-conditioned (river.condition_channel). A strict no-op, returning
    the same array and label and diagnostics None, when the case has no
    inflow point or config.CHANNEL_CONDITIONING is off."""
    if not config.CHANNEL_CONDITIONING or not config.INFLOW:
        return elevation, terrain_source, None
    conditioned, diag = river.condition_channel(elevation, cell_size,
                                                water_mask)
    if diag is None:
        return elevation, terrain_source, None
    # appended, not prepended: callers test terrain_source.startswith(...)
    return conditioned, terrain_source + CONDITIONED_TAG, diag


def exclude_mask(water_mask, shape, inflow=None, q_m3s=0.0):
    """Bool grid (row 0 = south) of cells that never count as flooding:
    permanent water plus, while the river is being routed in, the cells the
    inflow is injected into."""
    ex = (np.zeros(shape, bool) if water_mask is None
          else np.array(water_mask, dtype=bool))
    if inflow and q_m3s:
        ex.flat[inflow["nodes"]] = True       # node id = row * cols + col
    return ex


def run_all(specs, elevation, cell_size, inflow=None, q_m3s=0.0, say=None,
            exclude=None):
    """Run physics + decisions for every spec; returns viewer scenarios.
    exclude: exclude_mask() grid, kept out of every decision figure."""
    out = []
    for i, s in enumerate(specs):
        if say:
            say(f"running physics {i + 1}/{len(specs)} ({s['label']})",
                52 + int(38 * i / len(specs)))
        print(f"[scenario] {s['label']}: {s['rain_source']} "
              f"(total {sum(s['rain_series']):.0f} mm"
              f"{', river +%.0f m3/s' % q_m3s if inflow and q_m3s else ''}"
              f"{' - default' if s['is_default'] else ''})")
        series = s["rain_series"]
        times, depths = simulate.run_simulation(
            elevation, cell_size,
            lambda t, sr=series: sr[min(int(t // 3600), len(sr) - 1)],
            inflow=inflow, inflow_m3s_at=(lambda t: q_m3s) if q_m3s else None)
        decisions, source = decide.get_decisions(
            depths, times, allow_claude=s["is_default"],
            quiet=not s["is_default"], exclude=exclude)
        out.append({**s, "times": times, "depths": depths,
                    "decisions": decisions, "decision_source": source})
    return out
