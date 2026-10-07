"""Decision layer for HydroTwin.

Summarizes the peak flood state into named zones, asks claude-sonnet-5 for
evacuation decisions as strict JSON, and falls back to a rule-based planner
if the API key is missing, the call fails, or the JSON can't be parsed.
"""

import json
import os
import re

import numpy as np

import config


# ---------------------------------------------------------------- zones ----

def zone_name(zr, zc):
    """Zone band names: letter A = north edge, number 1 = west edge."""
    return f"{chr(ord('A') + (config.ZONE_DIV - 1 - zr))}{zc + 1}"


def summarize_flood(depths, times):
    """Build a compact text + structured summary of the peak flood state."""
    peak_idx = int(np.argmax([d.sum() for d in depths]))
    peak = depths[peak_idx]
    rows, cols = peak.shape
    rband = rows // config.ZONE_DIV
    cband = cols // config.ZONE_DIV

    zones = []
    for zr in range(config.ZONE_DIV):
        for zc in range(config.ZONE_DIV):
            block = peak[zr * rband:(zr + 1) * rband, zc * cband:(zc + 1) * cband]
            zones.append({
                "zone": zone_name(zr, zc),
                "max_depth_m": round(float(block.max()), 2),
                "pct_flooded": round(100.0 * float(
                    (block > config.FLOOD_DEPTH_M).mean()), 1),
                "pct_severe": round(100.0 * float(
                    (block > config.SEVERE_DEPTH_M).mean()), 1),
            })

    pois = []
    for poi in config.POIS:
        zr = min(poi["row"] // rband, config.ZONE_DIV - 1)
        zc = min(poi["col"] // cband, config.ZONE_DIV - 1)
        pois.append({**poi, "zone": zone_name(zr, zc),
                     "depth_here_m": round(float(peak[poi["row"], poi["col"]]), 2)})

    flooded = [z for z in zones if z["pct_flooded"] > 0 or z["max_depth_m"]
               > config.FLOOD_DEPTH_M]
    lines = [
        f"Flood simulation peak at t={times[peak_idx] / 3600.0:.1f} h. "
        f"Grid is divided into {config.ZONE_DIV}x{config.ZONE_DIV} zones "
        f"(A=north row, 1=west column).",
        f"Depth thresholds: flooded > {config.FLOOD_DEPTH_M} m, "
        f"severe > {config.SEVERE_DEPTH_M} m.",
        "Zones with flooding: " + (json.dumps(flooded) if flooded else "none"),
        "Points of interest: " + json.dumps(pois),
    ]
    return "\n".join(lines), zones, pois, peak_idx


# ---------------------------------------------------------------- claude ----

PROMPT = """You are a flood emergency decision system. Based on the flood \
summary below, produce evacuation decisions.

{summary}

Respond with ONLY a JSON object, no markdown, no prose, exactly this shape:
{{
  "evacuation_zones": [{{"zone": "<zone id>", "priority": "immediate|high|monitor", "reason": "<short reason>"}}],
  "safe_routes": [{{"from_zone": "<zone id>", "route_desc": "<short route description>"}}],
  "public_alert": "<one-sentence plain-language warning for the public>"
}}
Only include zones that actually need action. Consider the points of interest \
(hospitals and schools raise priority; flooded roads constrain routes)."""


def get_decisions(depths, times, allow_claude=True, quiet=False):
    """Return (decisions_dict, source_label). Never raises.

    allow_claude=False forces the (instant, offline) rule-based planner —
    used for the non-default what-if storm scenarios.
    """
    summary_text, zones, pois, peak_idx = summarize_flood(depths, times)
    if not quiet:
        print("[decide] Flood summary:\n" + summary_text)

    decisions = None
    if allow_claude and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            decisions = _ask_claude(summary_text)
            source = f"Claude ({config.CLAUDE_MODEL})"
        except Exception as exc:
            print(f"[decide] Claude call failed ({type(exc).__name__}: {exc}) "
                  f"-> rule-based fallback")
    elif allow_claude and not quiet:
        print("[decide] ANTHROPIC_API_KEY not set -> rule-based fallback")

    if decisions is None:
        decisions = _rule_based(zones, pois)
        source = "rule-based fallback"

    if not quiet:
        print(f"[decide] Decisions from: {source}")
    rows, cols = depths[0].shape
    return {**decisions, "zone_stats": zones, "pois": pois,
            "peak_index": peak_idx, "source": source,
            "route_vectors": compute_route_vectors(
                decisions["evacuation_zones"], zones, rows, cols)}, source


def compute_route_vectors(evac_zones, zone_stats, rows, cols):
    """Grid-coordinate arrows from each urgent zone toward its driest
    neighbour, for 3D route rendering. Independent of who wrote the
    decisions (Claude routes stay as prose; arrows come from the data)."""
    by_depth = {z["zone"]: z for z in zone_stats}
    rband, cband = rows // config.ZONE_DIV, cols // config.ZONE_DIV
    vectors = []
    for e in evac_zones:
        if e.get("priority") not in ("immediate", "high"):
            continue
        try:  # zone names may come from Claude; skip any malformed one
            target = _driest_neighbor(e["zone"], by_depth)
            if not target:
                continue
            fr, fc = _zone_rc(e["zone"])
            tr, tc = _zone_rc(target)
        except (KeyError, ValueError, IndexError):
            continue
        vectors.append({
            "priority": e["priority"],
            "from_rc": [int((fr + 0.5) * rband), int((fc + 0.5) * cband)],
            "to_rc": [int((tr + 0.5) * rband), int((tc + 0.5) * cband)],
        })
    return vectors


def _ask_claude(summary_text):
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user",
                   "content": PROMPT.format(summary=summary_text)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    decisions = _parse_json(text)
    for key in ("evacuation_zones", "safe_routes", "public_alert"):
        if key not in decisions:
            raise ValueError(f"response JSON missing key '{key}'")
    return decisions


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # strip md fences
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)  # first {...} block
        if not match:
            raise
        return json.loads(match.group(0))


# ------------------------------------------------------------ rule-based ----

def _rule_based(zones, pois):
    poi_zones = {p["zone"]: p for p in pois}
    evac, routes = [], []
    by_depth = {z["zone"]: z for z in zones}

    for z in sorted(zones, key=lambda z: -z["max_depth_m"]):
        priority = None
        if z["pct_severe"] > 2.0 or z["max_depth_m"] > 2 * config.SEVERE_DEPTH_M:
            priority = "immediate"
        elif z["pct_flooded"] > 5.0 or z["max_depth_m"] > config.SEVERE_DEPTH_M:
            priority = "high"
        elif z["max_depth_m"] > config.FLOOD_DEPTH_M:
            priority = "monitor"
        if priority is None:
            continue
        reason = (f"max depth {z['max_depth_m']} m, "
                  f"{z['pct_flooded']}% of zone above {config.FLOOD_DEPTH_M} m")
        if z["zone"] in poi_zones:
            p = poi_zones[z["zone"]]
            reason += f"; contains {p['name']} ({p['type']})"
        # a hospital/school only escalates a zone when water is AT it, not
        # when one low cell elsewhere in the zone holds a puddle
        if priority == "monitor" and any(
                q["zone"] == z["zone"] and q["type"] in ("hospital", "school")
                and q["depth_here_m"] > config.FLOOD_DEPTH_M for q in pois):
            priority = "high"
        evac.append({"zone": z["zone"], "priority": priority, "reason": reason})

    for e in evac:
        if e["priority"] == "monitor":
            continue
        neighbor = _driest_neighbor(e["zone"], by_depth)
        if neighbor:
            routes.append({
                "from_zone": e["zone"],
                "route_desc": f"Move {_direction(e['zone'], neighbor)} to zone "
                              f"{neighbor} (max depth "
                              f"{by_depth[neighbor]['max_depth_m']} m)"})

    acting = [e for e in evac if e["priority"] != "monitor"]
    if acting:
        worst = acting[0]
        alert = (f"Flooding up to {by_depth[worst['zone']]['max_depth_m']} m is "
                 f"expected in zone {worst['zone']} and surrounding areas — "
                 f"residents in affected zones should move to higher ground now.")
    elif evac:
        names = ", ".join(e["zone"] for e in evac)
        alert = (f"Localised ponding up to "
                 f"{by_depth[evac[0]['zone']]['max_depth_m']} m in low spots of zone(s) {names}; no evacuation needed. "
                 f"Monitor for updated forecasts.")
    else:
        alert = ("Minor ponding only; no evacuation needed, but stay alert for "
                 "updated forecasts.")
    return {"evacuation_zones": evac, "safe_routes": routes,
            "public_alert": alert}


def _zone_rc(name):
    letter, num = name[0], int(name[1:])
    zr = config.ZONE_DIV - 1 - (ord(letter) - ord("A"))
    return zr, num - 1


def _driest_neighbor(name, by_depth):
    zr, zc = _zone_rc(name)
    best, best_depth = None, float("inf")
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = zr + dr, zc + dc
        if 0 <= nr < config.ZONE_DIV and 0 <= nc < config.ZONE_DIV:
            n = zone_name(nr, nc)
            if by_depth[n]["max_depth_m"] < best_depth:
                best, best_depth = n, by_depth[n]["max_depth_m"]
    return best


def _direction(from_zone, to_zone):
    fr, fc = _zone_rc(from_zone)
    tr, tc = _zone_rc(to_zone)
    if tr > fr:
        return "north"
    if tr < fr:
        return "south"
    return "east" if tc > fc else "west"
