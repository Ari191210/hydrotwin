"""Live river-discharge data for HydroTwin.

Source: Open-Meteo Flood API (Copernicus GloFAS river discharge forecast).
No API key. Last successful responses are cached per case so the demo can
show last-known live data (clearly timestamped) with no internet.

"Seasonal median" is a real climatology: the median GloFAS discharge for
the same +/-15-day calendar window over CLIM_YEARS of historical data at the
same cell. (The API's own river_discharge_median is the median of the
forecast ensemble members, which tracks the forecast itself, so it can't say
whether the river is high.) Climatologies are cached per cell.
"""

import json
import os
from datetime import datetime, timezone

import config

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(_HERE, "assets", "glofas_cache.json")
CLIM_PATH = os.path.join(_HERE, "assets", "glofas_clim.json")
CLIM_YEARS = (1995, 2024)
CLIM_HALF_WINDOW_D = 15


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


def _fetch_live(lat=None, lon=None):
    """GloFAS cells are ~5 km; the river channel may sit one cell over.
    Sample a 3x3 neighbourhood in one request and keep the strongest cell —
    that's the river. lat/lon default to the active basin, but can be passed
    explicitly (so callers needn't mutate global config)."""
    try:
        import requests

        lat = config.BASIN_LAT if lat is None else lat
        lon = config.BASIN_LON if lon is None else lon
        offs = (-0.05, 0.0, 0.05)
        lats = [lat + a for a in offs for _ in offs]
        lons = [lon + b for _ in offs for b in offs]
        r = requests.get(
            "https://flood-api.open-meteo.com/v1/flood",
            params={"latitude": ",".join(f"{v:.4f}" for v in lats),
                    "longitude": ",".join(f"{v:.4f}" for v in lons),
                    "daily": "river_discharge",
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
        today = discharge[0]
        if today < 5.0:   # no resolvable river near this point
            print(f"[flooddata] no GloFAS river cell near basin "
                  f"(best {today:.1f} m3/s) -> panel omitted")
            return None
        median = seasonal_median(best["latitude"], best["longitude"],
                                 daily["time"])
        if median is None:
            print("[flooddata] no seasonal climatology -> discharge shown "
                  "without a 'vs normal' comparison")
            median = [0.0] * len(discharge)
        med = median[0]
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


def seasonal_median(lat, lon, days):
    """Median historical discharge (CLIM_YEARS) within +/-CLIM_HALF_WINDOW_D
    calendar days of each ISO date in `days`, at the GloFAS cell nearest
    lat/lon. None if the history can't be fetched or cached."""
    key = f"{lat:.3f},{lon:.3f}"
    clim = _clim_load().get(key)
    if clim is None:
        try:
            import requests

            r = requests.get(
                "https://flood-api.open-meteo.com/v1/flood",
                params={"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
                        "daily": "river_discharge",
                        "start_date": f"{CLIM_YEARS[0]}-01-01",
                        "end_date": f"{CLIM_YEARS[1]}-12-31"},
                timeout=(5, 40))
            r.raise_for_status()
            d = r.json()["daily"]
            by_doy = [[] for _ in range(366)]
            for t, v in zip(d["time"], d["river_discharge"]):
                if v is not None:
                    by_doy[_doy(t)].append(float(v))
            clim = []
            for doy in range(366):
                window = [v for k in range(-CLIM_HALF_WINDOW_D,
                                           CLIM_HALF_WINDOW_D + 1)
                          for v in by_doy[(doy + k) % 366]]
                clim.append(round(float(_median(window)), 1)
                            if window else 0.0)
            store = _clim_load()
            store[key] = clim
            with open(CLIM_PATH, "w", encoding="utf-8") as f:
                json.dump(store, f)
            print(f"[flooddata] built {CLIM_YEARS[0]}-{CLIM_YEARS[1]} "
                  f"seasonal climatology for GloFAS cell {key}")
        except Exception as exc:
            print(f"[flooddata] climatology fetch failed "
                  f"({type(exc).__name__}: {exc})")
            return None
    return [clim[_doy(t)] for t in days]


def _doy(iso):
    """0-based day of year on a 366-day calendar (Feb 29 = index 59)."""
    m, d = int(iso[5:7]), int(iso[8:10])
    return sum((31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[:m - 1]) + d - 1


def _median(vals):
    vals = sorted(vals)
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def _clim_load():
    try:
        with open(CLIM_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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
