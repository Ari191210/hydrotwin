"""July 2023 replay scenario for the Delhi page.

Turns the saved backtest run (assets/backtest_delhi_2023_conditioned.npz,
written by backtest_conditioned.py, described in BACKTEST_PREREG.md) into one
more viewer scenario. Nothing is simulated here: the frames, the forcing and
the nine site results are read from the file.

Everything the page says about the result is derived from the file's site
fields, so it stays true if the file is regenerated. The page must not claim
more than BACKTEST_PREREG.md does: the river inflow was calibrated to the
Old Railway Bridge level, one site floods from the river, and the other
"flooded" sites are rain pooled in closed terrain dips.
"""

import datetime
import os

import numpy as np

import config
import decide

_HERE = os.path.dirname(os.path.abspath(__file__))
NPZ = os.path.join(_HERE, "assets", "backtest_delhi_2023_conditioned.npz")
CASE = "delhi"
LABEL = "July 2023"
ELEV_TOL_M = 0.01          # npz elevation is float32; the live DEM is float64

REQUIRED = ("times", "depths", "elevation", "cell_size", "peak_q",
            "orb_observed_m", "rain_mm_hr", "river_q_m3s", "rain_daily_mm",
            "rain_start_date", "flood_depth_m", "radius_m", "site_names",
            "site_groups", "site_observed", "site_modelled",
            "site_max_depth_m", "site_max_depth_rain_only_m")

# Display order. The titles are the only hard-coded wording about outcomes;
# which site lands in which category is computed in _category().
CATEGORIES = [
    ("river", "ok", "Flooded by the river in the model (dry with the river "
                    "switched off): matches 2023"),
    ("pooled", "warn", "Water in the model is pooled rain, not the river "
                       "(same depth with the river switched off): not "
                       "counted"),
    ("missed", "bad", "Missed: flooded in 2023, dry in the model (the "
                      "elevation data puts the ground too high)"),
    ("drain", "off", "Dry in the model: the real cause was a failed drain, "
                     "which is not modelled"),
    ("false_pooled", "bad", "False alarm: pooled rain in the model, stayed "
                            "dry in 2023"),
    ("false_river", "bad", "False alarm: river water in the model, stayed "
                           "dry in 2023"),
    ("dry_ok", "ok", "Correctly dry"),
]
MAIN_GROUP = "A"       # the pre-registered headline group (overbank sites)
DRAIN_GROUP = "C"      # flooded in 2023 through a failed drain regulator


def _category(observed, modelled, rain_only_m, group, flood_m):
    """Outcome category of one site, from the file's fields only."""
    obs, mod = observed == "flooded", modelled == "flooded"
    pooled = rain_only_m >= flood_m      # just as wet with the river off
    if mod and obs:
        return "pooled" if pooled else "river"
    if mod:
        return "false_pooled" if pooled else "false_river"
    if obs:
        return "drain" if group == DRAIN_GROUP else "missed"
    return "dry_ok"


def _skip(reason):
    print(f"[replay] July 2023 replay SKIPPED: {reason}")
    return None


def _day(date, with_month=True):
    return f"{date.day} {date.strftime('%B') if with_month else ''}".strip()


def scenario(elevation, cell_size, exclude=None, path=NPZ):
    """Viewer scenario dict (same keys as scenarios.run_all entries, plus
    "replay") for the active case, or None when the case has no replay, the
    file is missing, or its grid is not the grid being rendered.

    exclude: the live scenarios.exclude_mask() grid, so the replay's zones,
    alert and stats use the same exclusion as every other scenario."""
    if config.ACTIVE_CASE != CASE:
        return None
    if not os.path.exists(path):
        return _skip(f"{path} not found")
    try:
        z = np.load(path, allow_pickle=False)
        missing = [k for k in REQUIRED if k not in z.files]
        if missing:
            return _skip(f"file lacks {', '.join(missing)}")
        z = {k: z[k] for k in REQUIRED}
    except Exception as exc:
        return _skip(f"cannot read {path} ({type(exc).__name__}: {exc})")

    # ---- the saved run must be on the grid this page draws
    if z["elevation"].shape != elevation.shape:
        return _skip(f"grid {z['elevation'].shape} is not the page's "
                     f"{elevation.shape}")
    if not np.isclose(float(z["cell_size"]), cell_size, rtol=1e-6):
        return _skip(f"cell size {float(z['cell_size']):.3f} m is not the "
                     f"page's {cell_size:.3f} m")
    dz = float(np.abs(z["elevation"].astype(float) - elevation).max())
    if dz > ELEV_TOL_M:
        return _skip(f"elevation differs from the page's terrain by up to "
                     f"{dz:.2f} m (was the saved run made on the same "
                     f"conditioned DEM?)")
    depths = [np.asarray(d, dtype=np.float32) for d in z["depths"]]
    times = [float(t) for t in z["times"]]
    if len(depths) != len(times) or len(times) < 2:
        return _skip("times and depths do not line up")

    # ---- forcing, as saved
    daily = [float(v) for v in z["rain_daily_mm"]]
    rain_hr = [float(v) for v in z["rain_mm_hr"]]
    river_q = [float(v) for v in z["river_q_m3s"]]
    inflow = [river_q[min(int(round(t / 3600.0)), len(river_q) - 1)]
              for t in times]
    peak_q = float(z["peak_q"])
    peak_frame = int(np.argmax(inflow))
    start = datetime.date.fromisoformat(str(z["rain_start_date"]))
    last = start + datetime.timedelta(days=len(daily) - 1)
    peak_day = start + datetime.timedelta(seconds=times[peak_frame])
    span = (f"{_day(start, start.month != last.month)} to {_day(last)} "
            f"{last.year}")
    orb = float(z["orb_observed_m"])

    # ---- site results, derived
    flood_m = float(z["flood_depth_m"])
    sites = []
    for i, name in enumerate(z["site_names"]):
        depth = float(z["site_max_depth_m"][i])
        rain_only = float(z["site_max_depth_rain_only_m"][i])
        group = str(z["site_groups"][i])
        observed = str(z["site_observed"][i])
        modelled = str(z["site_modelled"][i])
        sites.append({
            "name": str(name), "group": group, "observed": observed,
            "modelled": modelled, "depthM": round(depth, 2),
            "rainOnlyM": round(rain_only, 2),
            "cat": _category(observed, modelled, rain_only, group, flood_m),
            "model": f"{depth:.1f} m" if modelled == "flooded" else "dry"})
    cats = [{"key": key, "tone": tone, "title": title,
             "sites": [s for s in sites if s["cat"] == key]}
            for key, tone, title in CATEGORIES]
    cats = [c for c in cats if c["sites"]]

    main = [s for s in sites if s["group"] == MAIN_GROUP]
    a_rule = sum(s["observed"] == "flooded" and s["modelled"] == "flooded"
                 for s in main)
    a_river = sum(s["cat"] == "river" for s in main)
    false_alarms = sum(s["cat"] in ("false_pooled", "false_river")
                       for s in sites)
    if (a_rule, len(main), false_alarms, a_river) != (2, 3, 1, 1):
        print(f"[replay] !!! site results differ from BACKTEST_PREREG.md "
              f"(expected 2 of 3, 1 false alarm, 1 river hit; file gives "
              f"{a_rule} of {len(main)}, {false_alarms}, {a_river}) - the "
              f"page shows the file's numbers !!!")
    summary = (
        f"By the rule fixed before the test: {a_rule} of {len(main)} main "
        f"sites flooded as in {start.year}, and {false_alarms} false "
        f"alarm{'' if false_alarms == 1 else 's'}. Counting only flooding "
        f"from the river: {a_river} of {len(main)}.")

    # ---- decisions: the rule-based planner, with the live exclusion
    names = [p["name"] for p in config.POIS]
    if names != [s["name"] for s in sites]:
        print("[replay] note: the page's points of interest are not the "
              "backtest's sites (names or order differ); the results block "
              "still lists the backtest's sites")
    decisions, source = decide.get_decisions(
        depths, times, allow_claude=False, quiet=True, exclude=exclude)
    # the planner writes forecast-tense text ("is expected ... move now");
    # on a replay of a past event that reads as a live instruction
    zstats = decisions.get("zone_stats", [])
    worst = max(zstats, key=lambda z: z["max_depth_m"]) if zstats else None
    decisions["public_alert"] = (
        (f"In this replay the deepest modelled water outside the river is "
         f"{worst['max_depth_m']} m, in zone {worst['zone']}. " if worst
         else "")
        + "Zones and depths here include rain pooled in low ground, which "
          "the model cannot drain.")

    rain_source = (f"Open-Meteo weather archive, daily totals {span}, "
                   f"spread evenly over each day")
    info = {
        "start": start.isoformat(),
        "span": span,
        "rainDaily": daily,
        "inflow": [round(q, 1) for q in inflow],
        "inflowPeak": peak_q,
        "peakFrame": peak_frame,
        "title": f"REPLAY: {span.upper()}",
        "banner": (
            f"Not a forecast. River inflow was calibrated so the level at "
            f"the Old Railway Bridge matches the recorded {orb:.2f} m, so "
            f"that match is not a result. Rain is from the weather "
            f"archive."),
        "alertHead": f"REPLAY OF {last.strftime('%B').upper()} {last.year}: "
                     f"NOT A LIVE ALERT",
        "heading": f"{last.strftime('%B')} {last.year} check: "
                   f"{len(sites)} sites",
        "summary": summary,
        "cats": cats,
        "sites": sites,
        "notes": [
            f"The {len(sites)} sites were chosen before the test. A site "
            f"counts as flooded when water reaches {flood_m:.1f} m within "
            f"{float(z['radius_m']):.0f} m of it.",
            f"The model has no drains, so {len(daily)} days of rain pool "
            f"in low ground. The alert, zones and flooded area on this "
            f"replay include that pooled rain.",
            "This run uses the river bed as deepened for the live page, a "
            "change made after the first test. The site results were the "
            "same before it."],
        "riverSource": (
            f"calibrated inflow, not a measurement: one peak of "
            f"{peak_q:,.0f} m³/s above the dry-season baseline on "
            f"{_day(peak_day)}, set to match the Old Railway Bridge level"),
    }
    print(f"[replay] {LABEL}: {len(times)} saved frames over "
          f"{times[-1] / 3600.0:.0f} h, rain {sum(daily):.0f} mm, river peak "
          f"+{peak_q:.0f} m3/s (calibrated). {summary}")
    return {"label": LABEL, "mult": 1.0, "whatif": False,
            "is_default": False, "rain_source": rain_source,
            "rain_series": rain_hr[:int(round(times[-1] / 3600.0))],
            "times": times, "depths": depths,
            "decisions": decisions, "decision_source": source,
            "replay": info}
