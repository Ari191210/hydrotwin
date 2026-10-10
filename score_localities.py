"""Score the stage-indexed lookup against PREREG_LOCALITIES.md.

    python score_localities.py [srtm|fabdem ...] [--stage 208.66]
"""

import json
import math
import sys

import numpy as np

import config
import localities
import stagelib
import terrain

THRESH = 0.30
RADIUS_M = 250.0
RECORD_M = 208.66


def site_depths(lib, depth):
    """{name: (max depth within the radius outside the river mask, rc)}."""
    config.set_case("delhi")
    k = max(1, math.ceil(RADIUS_M / lib.cell))
    rows, cols = depth.shape
    out = {}
    for name, lat, lon, label, src in localities.LOCALITIES:
        r, c = terrain.latlon_to_rc(lat, lon, rows, cols)
        sl = (slice(max(0, r - k), r + k + 1), slice(max(0, c - k), c + k + 1))
        land = ~lib.mask[sl]
        out[name] = (float(depth[sl][land].max()) if land.any() else 0.0,
                     (r, c), float(lib.elevation_raw[sl][land].min())
                     if land.any() else float("nan"))
    return out


def score(dem, stage=RECORD_M, quiet=False):
    lib = stagelib.Library(dem)
    depth, q = lib.depth_at_stage(stage)
    d = site_depths(lib, depth)
    res = {"dem": dem, "source": lib.source, "stage_m": stage,
           "discharge_m3s": round(q), "rows": []}
    tally = {"model": [0, 0, 0], "bathtub": [0, 0, 0]}   # hit, miss, false
    for name, lat, lon, label, src in localities.LOCALITIES:
        maxd, rc, low = d[name]
        model = maxd >= THRESH
        tub = low < stage
        res["rows"].append({"name": name, "label": label, "source": src,
                            "depth_m": round(maxd, 2), "model": bool(model),
                            "lowest_ground_m": round(low, 1),
                            "bathtub": bool(tub)})
        for key, pred in (("model", model), ("bathtub", tub)):
            if label == "river":
                tally[key][0 if pred else 1] += 1
            elif label == "dry" and pred:
                tally[key][2] += 1
    for key, (h, m, f) in tally.items():
        res[key] = {"hits": h, "misses": m, "false_alarms": f,
                    "csi": round(h / (h + m + f), 2) if h + m + f else None}
    if not quiet:
        print(f"\n== {dem}: {lib.source}")
        print(f"   level {stage} m at the Old Railway Bridge <-> steady "
              f"discharge about {q:.0f} m3/s (library range "
              f"{lib.stage[0]:.2f}-{lib.stage[-1]:.2f} m, "
              f"{int((~lib.converged).sum())} runs not steady)")
        print(f"   {'locality':24s} {'2023':6s} {'model':>8s} {'depth m':>8s} "
              f"{'low ground':>10s} {'bathtub':>8s}")
        for r in res["rows"]:
            print(f"   {r['name']:24s} {r['label']:6s} "
                  f"{'FLOOD' if r['model'] else 'dry':>8s} "
                  f"{r['depth_m']:8.2f} {r['lowest_ground_m']:10.1f} "
                  f"{'FLOOD' if r['bathtub'] else 'dry':>8s}")
        for key in ("model", "bathtub"):
            t = res[key]
            print(f"   {key:8s}: hits {t['hits']}/7, false alarms "
                  f"{t['false_alarms']}/10, CSI {t['csi']}")
    return res


if __name__ == "__main__":
    args = sys.argv[1:]
    stage = RECORD_M
    if "--stage" in args:
        i = args.index("--stage")
        stage = float(args[i + 1])
        del args[i:i + 2]
    out = [score(d, stage) for d in (args or ["srtm", "fabdem"])]
    with open("outputs/locality_scores.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
