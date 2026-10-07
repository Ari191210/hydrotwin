"""Rainfall forcing for HydroTwin.

Primary: Open-Meteo hourly precipitation forecast for the basin (no API key).
The built-in synthetic design storm is only ever a labelled what-if
scenario; it never stands in for the forecast.
"""

import math

import config

# Design storm, mm/hr per simulated hour: builds, peaks, tapers.
SYNTHETIC_STORM_MM_HR = [5.0, 18.0, 42.0, 55.0, 28.0, 12.0, 6.0, 3.0]


DESIGN_SOURCE = "design storm (synthetic, not a forecast)"


def get_rainfall():
    """Return {"series": [mm/hr per hour] or None, "source": label}.

    series is the live forecast's wettest window as issued, even when it is
    dry: "no flood expected" is a correct answer. It is None only when the
    forecast could not be fetched. Never raises.
    """
    hours_needed = max(1, math.ceil(config.SIM_DURATION_HR))
    try:
        series = _fetch_open_meteo(hours_needed)
        total = sum(series)
        print(f"[rainfall] Open-Meteo forecast, wettest {hours_needed} h "
              f"window: {[round(r, 1) for r in series]} | total {total:.1f} mm"
              + (" (below the flood-demo threshold; the design storm is "
                 "offered as a labelled what-if)"
                 if total < config.MIN_DEMO_RAIN_MM else ""))
        return {"series": series, "source": "Open-Meteo live forecast"}
    except Exception as exc:
        print(f"[rainfall] Open-Meteo failed ({type(exc).__name__}: {exc}) "
              f"-> no forecast; only the design storm what-if is available")
        return {"series": None, "source": "forecast unavailable"}


def design_storm():
    hours_needed = max(1, math.ceil(config.SIM_DURATION_HR))
    return _synthetic_storm(hours_needed)


def _fetch_open_meteo(hours_needed):
    import requests

    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config.BASIN_LAT,
            "longitude": config.BASIN_LON,
            "hourly": "precipitation",
            "forecast_days": 2,
            "timezone": "UTC",
        },
        timeout=(5, config.OPEN_METEO_TIMEOUT_S),
    )
    r.raise_for_status()
    values = r.json()["hourly"]["precipitation"]
    values = [float(v) if v is not None else 0.0 for v in values]
    if len(values) < hours_needed:
        raise ValueError(f"forecast too short: {len(values)} h")
    # Use the wettest contiguous window in the forecast so the demo shows the
    # storm the forecast actually contains, not whatever the next N hours are.
    best_start, best_total = 0, -1.0
    for i in range(len(values) - hours_needed + 1):
        total = sum(values[i:i + hours_needed])
        if total > best_total:
            best_start, best_total = i, total
    return values[best_start:best_start + hours_needed]


def _synthetic_storm(hours_needed):
    series = list(SYNTHETIC_STORM_MM_HR)
    while len(series) < hours_needed:
        series.append(max(series[-1] * 0.5, 1.0))
    return series[:hours_needed]
