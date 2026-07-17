"""Rainfall forcing for HydroTwin.

Primary: Open-Meteo hourly precipitation forecast for the basin (no API key).
Fallback: built-in synthetic design storm (rising then tapering hyetograph).
The fallback is also used when the live forecast is too dry to demo a flood.
"""

import math

import config

# Design storm, mm/hr per simulated hour: builds, peaks, tapers.
SYNTHETIC_STORM_MM_HR = [5.0, 18.0, 42.0, 55.0, 28.0, 12.0, 6.0, 3.0]


def get_rainfall():
    """Return (rain_mm_hr_at, hourly_series_mm_hr, source_label).

    rain_mm_hr_at is a callable t_seconds -> mm/hr (piecewise-constant hourly).
    Never raises; falls back to the synthetic storm on any failure.
    """
    hours_needed = max(1, math.ceil(config.SIM_DURATION_HR))
    series, source = None, None

    try:
        series = _fetch_open_meteo(hours_needed)
        total = sum(series)
        if total < config.MIN_DEMO_RAIN_MM:
            print(f"[rainfall] Open-Meteo forecast is too dry for a flood demo "
                  f"({total:.1f} mm over {hours_needed} h < "
                  f"{config.MIN_DEMO_RAIN_MM} mm) -> using synthetic design storm")
            series = None
        else:
            source = "Open-Meteo live forecast"
    except Exception as exc:
        print(f"[rainfall] Open-Meteo failed ({type(exc).__name__}: {exc}) "
              f"-> using synthetic design storm")

    if series is None:
        series = _synthetic_storm(hours_needed)
        source = "synthetic design storm"

    series = [r * config.RAIN_MULTIPLIER for r in series]
    print(f"[rainfall] Source: {source} | hourly mm/hr: "
          f"{[round(r, 1) for r in series]} | total {sum(series):.1f} mm")

    def rain_mm_hr_at(t_seconds):
        idx = min(int(t_seconds // 3600.0), len(series) - 1)
        return series[idx]

    return rain_mm_hr_at, series, source


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
