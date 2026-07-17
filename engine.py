"""Callable HydroTwin pipeline for the live server.

simulate_location(lat, lon, ...) runs the full terrain -> rainfall ->
physics -> decisions chain for ANY point on Earth and returns the rendered
3D viewer HTML plus a compact summary. Results are cached by rounded
coordinate so repeat locations are instant.

The global config is process-wide, so a module lock serializes simulations
(the Flask dev server may handle requests concurrently).
"""

import math
import threading
import time
from datetime import datetime, timezone

import numpy as np

import config
import decide
import flooddata
import rainfall
import simulate
import terrain
import viewer3d

_LOCK = threading.Lock()
_CACHE = {}          # key -> {"html":..., "summary":...}
_CACHE_MAX = 24


def cache_key(lat, lon):
    return f"{round(lat, 2)},{round(lon, 2)}"


def get_cached(lat, lon):
    return _CACHE.get(cache_key(lat, lon))


def simulate_location(lat, lon, title=None, pop_density=None,
                      progress=None):
    """Run the whole pipeline for (lat, lon). Returns a dict with
    'html' (the viewer) and 'summary'. `progress(stage, pct)` is an
    optional callback for the live job UI. Never raises for expected
    failures — falls back through terrain/rain/decision layers."""
    def say(stage, pct):
        if progress:
            progress(stage, pct)

    key = cache_key(lat, lon)
    cached = _CACHE.get(key)
    if cached:
        say("cached", 100)
        return cached

    with _LOCK:
        cached = _CACHE.get(key)          # re-check inside the lock
        if cached:
            return cached

        title = title or f"{lat:.3f}, {lon:.3f}"
        pop_density = pop_density if pop_density is not None else 3000
        name = "loc_" + key.replace(",", "_").replace("-", "m") \
                            .replace(".", "p")

        say("locating basin", 5)
        config.set_live_location(lat, lon, title, [], pop_density, name)

        say("fetching terrain", 12)
        elevation, cell_size, terrain_source = terrain.load_terrain()

        say("placing points of interest", 30)
        pois = _fetch_pois(lat, lon, elevation, cell_size)
        config.POIS = pois

        say("reading live rainfall", 40)
        _, base_series, rain_source = rainfall.get_rainfall()

        say("reading live river discharge", 48)
        discharge = flooddata.get_river_discharge()

        scenarios = []
        n = len(config.WHATIF_MULTIPLIERS)
        for i, mult in enumerate(config.WHATIF_MULTIPLIERS):
            say(f"running physics {i + 1}/{n} (storm x{mult:g})",
                52 + int(38 * i / n))
            series = [r * mult for r in base_series]
            is_default = (mult == config.RAIN_MULTIPLIER)
            times, depths = simulate.run_simulation(
                elevation, cell_size,
                lambda t, s=series: s[min(int(t // 3600), len(s) - 1)])
            decisions, decision_source = decide.get_decisions(
                depths, times, allow_claude=is_default, quiet=True)
            scenarios.append({
                "mult": mult, "times": times, "depths": depths,
                "rain_series": series, "decisions": decisions,
                "decision_source": decision_source,
                "is_default": is_default})

        say("rendering 3D scene", 92)
        issued_at = datetime.now(timezone.utc).isoformat()
        html = viewer3d.make_3d_viewer(
            scenarios, elevation, cell_size, rain_source, terrain_source,
            discharge=discharge, live=True, issued_at=issued_at, write=False)

        default = next(s for s in scenarios if s["is_default"])
        peak = default["depths"][default["decisions"]["peak_index"]]
        flooded_km2 = float((peak > config.FLOOD_DEPTH_M).sum()) \
            * cell_size * cell_size / 1e6
        summary = {
            "lat": lat, "lon": lon, "title": title,
            "terrain": terrain_source, "rain": rain_source,
            "peak_depth_m": round(float(peak.max()), 2),
            "flooded_km2": round(flooded_km2, 2),
            "people_est": int(flooded_km2 * pop_density),
            "n_zones": len(default["decisions"].get("evacuation_zones", [])),
            "alert": default["decisions"].get("public_alert", ""),
            "discharge": discharge["today"] if discharge else None,
            "issued_at": issued_at,
            "elev_range": [round(float(elevation.min())),
                           round(float(elevation.max()))],
        }
        result = {"html": html, "summary": summary}

        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = result
        say("done", 100)
        return result


def _fetch_pois(lat, lon, elevation, cell_size):
    """Real nearby hospitals/schools/bridges from OpenStreetMap Overpass,
    snapped to grid coords. Synthetic fallback on any failure so the
    decision layer always has points to reason about."""
    rows, cols = elevation.shape
    half_lat = rows * cell_size / 2.0 / 111_320.0
    half_lon = cols * cell_size / 2.0 / (
        111_320.0 * math.cos(math.radians(lat)))
    south, north = lat - half_lat, lat + half_lat
    west, east = lon - half_lon, lon + half_lon

    def to_rc(plat, plon):
        row = int((plat - south) / (north - south) * (rows - 1))   # 0 = south
        col = int((plon - west) / (east - west) * (cols - 1))
        return max(0, min(rows - 1, row)), max(0, min(cols - 1, col))

    try:
        import requests

        q = f"""[out:json][timeout:12];(
          node["amenity"="hospital"]({south},{west},{north},{east});
          node["amenity"="school"]({south},{west},{north},{east});
          node["amenity"="clinic"]({south},{west},{north},{east});
          way["bridge"="yes"]({south},{west},{north},{east});
        );out center 40;"""
        r = requests.post("https://overpass-api.de/api/interpreter",
                          data={"data": q},
                          headers={"User-Agent": "HydroTwin/1.0 flood-demo",
                                   "Accept": "application/json"},
                          timeout=(5, 18))
        r.raise_for_status()
        elems = r.json().get("elements", [])
        picked, seen = [], set()
        order = {"hospital": 0, "clinic": 1, "school": 2}
        elems.sort(key=lambda e: order.get(
            e.get("tags", {}).get("amenity"), 3))
        for e in elems:
            tags = e.get("tags", {})
            plat = e.get("lat") or e.get("center", {}).get("lat")
            plon = e.get("lon") or e.get("center", {}).get("lon")
            if plat is None or plon is None:
                continue
            amenity = tags.get("amenity")
            ptype = ("hospital" if amenity in ("hospital", "clinic")
                     else "school" if amenity == "school"
                     else "road")
            nm = tags.get("name") or {
                "hospital": "Hospital", "school": "School",
                "road": "Bridge"}[ptype]
            row, col = to_rc(plat, plon)
            if (row, col) in seen:
                continue
            seen.add((row, col))
            picked.append({"name": nm[:34], "type": ptype,
                           "row": row, "col": col})
            if len(picked) >= 5:
                break
        if picked:
            print(f"[engine] OSM POIs: {len(picked)} real features near "
                  f"{lat:.3f},{lon:.3f}")
            return picked
    except Exception as exc:
        print(f"[engine] Overpass POI fetch failed "
              f"({type(exc).__name__}: {exc}) -> synthetic POIs")

    return [
        {"name": "District Hospital", "type": "hospital",
         "row": int(rows * 0.4), "col": int(cols * 0.45)},
        {"name": "Community School", "type": "school",
         "row": int(rows * 0.6), "col": int(cols * 0.58)},
        {"name": "River Bridge", "type": "road",
         "row": int(rows * 0.3), "col": int(cols * 0.5)},
        {"name": "Main Road Junction", "type": "road",
         "row": int(rows * 0.7), "col": int(cols * 0.35)},
    ]


_COND_CACHE = {}          # key -> (timestamp, payload)
_COND_TTL = 20.0          # seconds; upstream data changes far slower than this


def current_conditions(lat, lon):
    """Live conditions readout (current rainfall + river discharge). Cached
    for a few seconds so frequent UI polls return instantly and never
    outrun the upstream fetch — the fix for UI/data speed mismatch. Never
    blocks long, never raises."""
    key = cache_key(lat, lon)
    hit = _COND_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _COND_TTL:
        fresh = dict(hit[1])
        fresh["server_time"] = datetime.now(timezone.utc).isoformat()
        return fresh

    out = {"server_time": datetime.now(timezone.utc).isoformat(),
           "lat": lat, "lon": lon, "rain_now_mm_hr": None,
           "weather_time": None, "discharge_m3s": None,
           "discharge_pct": None}
    try:
        import requests

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon,
                    "current": "precipitation,rain,weather_code",
                    "forecast_days": 1, "timezone": "UTC"},
            timeout=(4, 8))
        r.raise_for_status()
        cur = r.json().get("current", {})
        out["rain_now_mm_hr"] = cur.get("precipitation")
        out["weather_time"] = cur.get("time")
    except Exception:
        pass
    try:
        d = flooddata._fetch_live(lat, lon)   # explicit coords, no global race
        if d:
            out["discharge_m3s"] = d["today"]
            out["discharge_pct"] = d["pct_of_median"]
    except Exception:
        pass
    _COND_CACHE[key] = (time.time(), out)
    return out
