"""Live river-discharge data for HydroTwin.

Source: Open-Meteo Flood API (Copernicus GloFAS river discharge forecast).
No API key. Last successful responses are cached per case so the demo can
show last-known live data (clearly timestamped) with no internet.
"""

import json
import os
from datetime import datetime, timezone

import config

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "assets", "glofas_cache.json")


def get_river_discharge():
    """Return a dict for the active case, or None if never fetched.

    {days: [iso..], discharge: [m3/s..], median: [m3/s..],
     today: float, pct_of_median: float, fetched_at: iso, live: bool}
    """
    data = _fetch_live()
    if data is not None:
        _cache_put(data)
        data["live"] = True
        print(f"[flooddata] GloFAS live: {data['today']:.0f} m3/s today "
              f"({data['pct_of_median']:+.0f}% vs seasonal median), "
              f"7-day trend {data['discharge'][0]:.0f} -> "
              f"{data['discharge'][-1]:.0f} m3/s")
        return data

    cached = _cache_get()
    if cached is not None:
        cached["live"] = False
        print(f"[flooddata] GloFAS offline -> cached data from "
              f"{cached['fetched_at'][:10]}")
        return cached

    print("[flooddata] GloFAS unavailable and no cache -> discharge "
          "panel omitted")
    return None


def _fetch_live():
    """GloFAS cells are ~5 km; the river channel may sit one cell over.
    Sample a 3x3 neighbourhood in one request and keep the strongest cell —
    that's the river."""
    try:
        import requests

        offs = (-0.05, 0.0, 0.05)
        lats = [config.BASIN_LAT + a for a in offs for _ in offs]
        lons = [config.BASIN_LON + b for _ in offs for b in offs]
        r = requests.get(
            "https://flood-api.open-meteo.com/v1/flood",
            params={"latitude": ",".join(f"{v:.4f}" for v in lats),
                    "longitude": ",".join(f"{v:.4f}" for v in lons),
                    "daily": "river_discharge,river_discharge_median",
                    "forecast_days": 7},
            timeout=(5, 20))
        r.raise_for_status()
        cells = r.json()
        if isinstance(cells, dict):
            cells = [cells]
        best = max(cells, key=lambda c: (c["daily"]["river_discharge"][0]
                                         or 0.0))
        daily = best["daily"]
        discharge = [float(v) if v is not None else 0.0
                     for v in daily["river_discharge"]]
        median = [float(v) if v is not None else 0.0
                  for v in daily["river_discharge_median"]]
        today, med = discharge[0], median[0]
        if today < 5.0:   # no resolvable river near this point
            print(f"[flooddata] no GloFAS river cell near basin "
                  f"(best {today:.1f} m3/s) -> panel omitted")
            return None
        return {
            "days": daily["time"],
            "discharge": [round(v, 1) for v in discharge],
            "median": [round(v, 1) for v in median],
            "today": round(today, 1),
            "pct_of_median": round((today / med - 1.0) * 100.0, 1)
                if med > 0 else 0.0,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        print(f"[flooddata] fetch failed ({type(exc).__name__}: {exc})")
        return None


def _cache_get():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f).get(config.ACTIVE_CASE)
        if data and data.get("today", 0) >= 5.0:
            return data
        return None
    except Exception:
        return None


def _cache_put(data):
    try:
        cache = {}
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
        cache[config.ACTIVE_CASE] = data
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as exc:
        print(f"[flooddata] cache write failed ({type(exc).__name__})")
