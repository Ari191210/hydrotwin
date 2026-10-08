"""River inflow for HydroTwin.

The physics domain is a few km across, so a big river's flood arrives from
upstream through the grid edge, not from rain on the grid. This module finds
where the river enters (a case's explicit inflow point, snapped to the
lowest DEM cell on that edge) and turns a discharge in m3/s into a per-cell
source term for OverlandFlow.

SRTM was flown in February 2000, so the DEM already holds the river at its
dry-season surface. Only discharge ABOVE that dry-season baseline (the
February median of the GloFAS history) is routed in. What the river
occupies at an ordinary annual high flow is its own footprint, not flooding
(riverstate.bankfull_footprint).
"""

import heapq
import os

import numpy as np

import config
import terrain

_HERE = os.path.dirname(os.path.abspath(__file__))
MASK_CACHE_DIR = os.path.join(_HERE, "assets", "masks")
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter",
                 "https://maps.mail.ru/osm/tools/overpass/api/interpreter")


def _mask_cache_path(rows, cols, pad_m=0.0):
    """assets/masks/<lat>_<lon>_z<zoom>_<rows>x<cols>_pad<m>.npy for the
    active case (same key scheme as imagery.py)."""
    key = (f"{config.BASIN_LAT:.4f}_{config.BASIN_LON:.4f}"
           f"_z{config.TERRAIN_ZOOM}_{rows}x{cols}_pad{pad_m:g}")
    return os.path.join(MASK_CACHE_DIR, key + ".npy")

# edge -> (node (row, col) at along-edge index k and inward offset d)
_EDGES = {
    "south": lambda k, d, R, C: (d, k),
    "north": lambda k, d, R, C: (R - 1 - d, k),
    "west": lambda k, d, R, C: (k, d),
    "east": lambda k, d, R, C: (k, C - 1 - d),
}


def find_inflow(elevation, cell_size, point=None, quiet=False):
    """Locate the river inflow span for the active case.

    Returns {"name", "edge", "rc", "bed_m", "width_m", "nodes", "closed"}
    or None when the case has no inflow point (live locations, or a point
    outside the grid). `nodes` are core-node ids that receive the inflow;
    `closed` are boundary nodes across the channel, closed so injected
    water cannot drain straight back out of the upstream edge.
    """
    point = point or config.INFLOW
    if not point:
        return None
    R, C = elevation.shape
    rc = terrain.latlon_to_rc(point["lat"], point["lon"], R, C)
    if rc is None:
        print(f"[river] inflow point {point} is outside the grid -> no inflow")
        return None
    r, c = rc
    edge = min((("south", r), ("north", R - 1 - r), ("west", c),
                ("east", C - 1 - c)), key=lambda e: e[1])[0]
    at = _EDGES[edge]
    n_along = C if edge in ("south", "north") else R
    k0 = c if edge in ("south", "north") else r

    # snap to the channel bed on the first interior line
    line = np.array([elevation[at(k, 1, R, C)] for k in range(n_along)])
    w = max(1, int(config.INFLOW_SEARCH_M / cell_size))
    lo, hi = max(1, k0 - w), min(n_along - 1, k0 + w + 1)
    kb = lo + int(np.argmin(line[lo:hi]))
    bed = float(line[kb])

    # channel span: contiguous cells within INFLOW_CHANNEL_DZ_M of the bed
    a = b = kb
    while (b - a + 1) < config.INFLOW_MAX_CELLS:
        grew = False
        if a - 1 >= 1 and line[a - 1] <= bed + config.INFLOW_CHANNEL_DZ_M:
            a -= 1
            grew = True
        if (b - a + 1) < config.INFLOW_MAX_CELLS and b + 1 <= n_along - 2 \
                and line[b + 1] <= bed + config.INFLOW_CHANNEL_DZ_M:
            b += 1
            grew = True
        if not grew:
            break

    def nid(k, d):
        rr, cc = at(k, d, R, C)
        return rr * C + cc

    nodes = [nid(k, d) for d in range(1, config.INFLOW_DEPTH_ROWS + 1)
             for k in range(a, b + 1)]
    closed = [nid(k, 0) for k in range(max(0, a - 3), min(n_along, b + 4))]
    info = {"name": point.get("name", "river"), "edge": edge,
            "rc": at(kb, 1, R, C), "bed_m": round(bed, 1),
            "width_m": round((b - a + 1) * cell_size),
            "nodes": nodes, "closed": closed}
    if not quiet:
        print(f"[river] {info['name']} enters across the {edge} edge at cell "
              f"{info['rc']} (bed {bed:.1f} m, channel ~{info['width_m']} m, "
              f"{len(nodes)} inflow cells)")
    return info


# ---- Channel conditioning ("breaching") ---------------------------------
# A surface DEM is not a river bed: along the Yamuna it holds bars, noise
# over water, and decks/embankments, so the mapped channel climbs and falls
# by metres and small flows pond behind the highs like a bathtub. Standard
# fix (stream burning / breaching): trace the thalweg through the DEM and
# cut it down to a non-increasing bed. Cells are only ever lowered.

def rc_to_latlon(row, col, rows=None, cols=None):
    """Lat/lon of the centre of grid cell (row, col); inverse of
    terrain.latlon_to_rc for the active basin window."""
    import math

    rows = rows or config.GRID_ROWS
    cols = cols or config.GRID_COLS
    zoom = config.TERRAIN_ZOOM
    cx, cy = terrain._mercator_px(config.BASIN_LAT, config.BASIN_LON, zoom)
    x0, y0 = int(cx - cols / 2), int(cy - rows / 2)
    px, py = x0 + col + 0.5, y0 + (rows - 1 - row) + 0.5
    n = 2 ** zoom * 256.0
    lon = px / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * py / n))))
    return lat, lon


def _find_outlet(elevation, cell_size, start, in_edge, water_mask):
    """Boundary cell (row, col) where the river leaves the grid, plus the
    rule used. The OSM water mask says WHICH edge stretch (the mapped river
    connected to the inflow, at its crossing farthest from the inflow); the
    DEM then picks the bed cell there, exactly as find_inflow does."""
    from scipy import ndimage

    R, C = elevation.shape
    n_along = {"south": C, "north": C, "west": R, "east": R}
    w = max(1, int(config.INFLOW_SEARCH_M / cell_size))

    def snap(edge, k0):
        at = _EDGES[edge]
        lo, hi = max(1, k0 - w), min(n_along[edge] - 1, k0 + w + 1)
        line = np.array([elevation[at(k, 0, R, C)] for k in range(lo, hi)])
        return at(lo + int(np.argmin(line)), 0, R, C)

    if water_mask is not None and np.asarray(water_mask).any():
        lab, n = ndimage.label(np.asarray(water_mask, bool),
                               structure=np.ones((3, 3)))
        rr, cc = np.nonzero(lab)
        d = np.hypot(rr - start[0], cc - start[1])
        comp = int(lab[rr[np.argmin(d)], cc[np.argmin(d)]])
        best = None
        for edge in _EDGES:
            if edge == in_edge:
                continue
            at = _EDGES[edge]
            ks = [k for k in range(1, n_along[edge] - 1)
                  if lab[at(k, 0, R, C)] == comp]
            if not ks:
                continue
            k0 = ks[len(ks) // 2]
            r0, c0 = at(k0, 0, R, C)
            far = float(np.hypot(r0 - start[0], c0 - start[1]))
            if best is None or far > best[0]:
                best = (far, edge, k0)
        if best is not None:
            _, edge, k0 = best
            return snap(edge, k0), (
                f"OSM river crosses the {edge} edge near index {k0}; "
                f"snapped to the lowest DEM cell within "
                f"{config.INFLOW_SEARCH_M:.0f} m")
        why = "the mapped river never reaches another grid edge"
    else:
        why = "no OSM water mask available"
    opposite = {"north": "south", "south": "north",
                "west": "east", "east": "west"}[in_edge]
    at = _EDGES[opposite]
    line = np.array([elevation[at(k, 0, R, C)]
                     for k in range(1, n_along[opposite] - 1)])
    return at(1 + int(np.argmin(line)), 0, R, C), (
        f"FALLBACK ({why}): lowest DEM cell on the opposite ({opposite}) "
        f"edge")


def _thalweg(elevation, cell_size, start, outlet):
    """Least-cost path start -> outlet over the DEM. Step cost = metres
    climbed + CHANNEL_PATH_DIST_WEIGHT x metres travelled. 4-connected,
    because OverlandFlow only moves water across orthogonal links; interior
    cells plus the outlet only, so it cannot leave by another edge."""
    R, C = elevation.shape
    step = config.CHANNEL_PATH_DIST_WEIGHT * cell_size
    z = elevation
    dist = np.full((R, C), np.inf)
    prev = {}
    dist[start] = 0.0
    heap = [(0.0, start)]
    while heap:
        d, (r, c) = heapq.heappop(heap)
        if d > dist[r, c]:
            continue
        if (r, c) == outlet:
            break
        for a, b in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if not (0 <= a < R and 0 <= b < C):
                continue
            if (a in (0, R - 1) or b in (0, C - 1)) and (a, b) != outlet:
                continue
            nd = d + max(0.0, float(z[a, b] - z[r, c])) + step
            if nd < dist[a, b]:
                dist[a, b] = nd
                prev[(a, b)] = (r, c)
                heapq.heappush(heap, (nd, (a, b)))
    if outlet not in prev:
        return None
    path = [outlet]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


def condition_channel(elevation, cell_size, water_mask=None, point=None,
                      quiet=False):
    """Hydro-condition the river channel of a case that has an inflow point.

    1. thalweg = least-cost DEM path from the inflow bed cell to the outlet
       (outlet located with the OSM water mask, see _find_outlet);
    2. bed level along it = running minimum from the inflow downstream
       (less CHANNEL_MIN_SLOPE x distance), i.e. the smallest lowering-only
       change that makes the bed non-increasing;
    3. every cell within half the inflow width of the path is cut to the
       level of its nearest path cell. Cells are only lowered, never raised.

    Returns (elevation, diagnostics). When the case has no inflow point the
    SAME array object comes back with diagnostics None (a true no-op).
    """
    info = find_inflow(elevation, cell_size, point, quiet=True)
    if info is None:
        return elevation, None
    from scipy import ndimage
    from scipy.signal import find_peaks

    R, C = elevation.shape
    start = tuple(int(v) for v in info["rc"])
    outlet, rule = _find_outlet(elevation, cell_size, start, info["edge"],
                                water_mask)
    outlet = tuple(int(v) for v in outlet)
    path = _thalweg(elevation, cell_size, start, outlet)
    if path is None:
        print(f"[river] channel conditioning: no path {start} -> {outlet}; "
              f"terrain left unconditioned")
        return elevation, None

    pr = np.array([p[0] for p in path])
    pc = np.array([p[1] for p in path])
    bed = elevation[pr, pc].astype(float)
    level = np.empty_like(bed)
    level[0] = bed[0]
    drop = config.CHANNEL_MIN_SLOPE * cell_size
    for i in range(1, len(bed)):
        level[i] = min(bed[i], level[i - 1] - drop)

    # carve the channel width: nearest-path-cell lookup, lower only
    n_wide = max(1, int(round(info["width_m"] / cell_size)))
    radius = (n_wide - 1) / 2.0
    lvl_grid = np.full((R, C), np.inf)
    lvl_grid[pr, pc] = level
    on_path = np.zeros((R, C), bool)
    on_path[pr, pc] = True
    dist, (ir, ic) = ndimage.distance_transform_edt(~on_path,
                                                    return_indices=True)
    corridor = dist <= radius + 1e-9
    target = np.where(corridor, lvl_grid[ir, ic], np.inf)
    out = np.minimum(elevation, target)
    lowering = elevation - out
    changed = lowering > 0.0

    # sills: prominent local highs of the original bed that stood above the
    # enforced level (what the water had to climb over)
    excess = bed - level
    peaks, props = find_peaks(bed, prominence=config.CHANNEL_SILL_MIN_M)
    sills = []
    for i, prom in zip(peaks, props["prominences"]):
        if excess[i] < config.CHANNEL_SILL_MIN_M:
            continue
        lat, lon = rc_to_latlon(int(pr[i]), int(pc[i]), R, C)
        sills.append({"path_index": int(i), "rc": (int(pr[i]), int(pc[i])),
                      "lat": round(lat, 5), "lon": round(lon, 5),
                      "bed_before_m": round(float(bed[i]), 2),
                      "bed_after_m": round(float(level[i]), 2),
                      "height_m": round(float(excess[i]), 2),
                      "prominence_m": round(float(prom), 2)})
    sills.sort(key=lambda s: -s["height_m"])

    diag = {
        "inflow_rc": start, "outlet_rc": outlet, "outlet_rule": rule,
        "path": [(int(r), int(c)) for r, c in path],
        "path_length_m": round((len(path) - 1) * cell_size),
        "bed_before_m": bed, "bed_after_m": level,
        "width_cells": n_wide, "corridor": corridor,
        "cells_changed": int(changed.sum()),
        "cells_changed_gt_10cm": int((lowering > 0.10).sum()),
        "max_lowering_m": float(lowering.max()),
        "mean_lowering_m": float(lowering[changed].mean()) if changed.any()
        else 0.0,
        "volume_removed_m3": float(lowering.sum() * cell_size * cell_size),
        "sills": sills,
    }
    if not quiet:
        print(f"[river] channel conditioning: thalweg {start} -> {outlet}, "
              f"{len(path)} cells ({diag['path_length_m'] / 1000:.1f} km); "
              f"outlet: {rule}")
        print(f"[river] channel conditioning: bed {bed[0]:.1f} m -> "
              f"{level[-1]:.1f} m, {n_wide} cells wide; lowered "
              f"{diag['cells_changed']} cells (max {diag['max_lowering_m']:.2f}"
              f" m, mean {diag['mean_lowering_m']:.2f} m); "
              f"{len(sills)} sills removed, highest "
              + (f"{sills[0]['height_m']:.2f} m at {sills[0]['rc']}"
                 if sills else "none"))
        after = find_inflow(out, cell_size, point, quiet=True)
        if after is None or after["nodes"] != info["nodes"]:
            print("[river] !!! channel conditioning changed the inflow "
                  "cells find_inflow selects !!!")
    return out, diag


def excess_from_glofas(discharge):
    """Discharge to route, in m3/s, plus a source label: the highest GloFAS
    forecast of the next two days ABOVE THE DEM BASELINE (q_dem_baseline,
    the February median; see flooddata.river_stats). 0 when the river is at
    or below its dry-season flow.

    If the GloFAS history (and so the baseline) is unavailable, falls back
    to the old rule, discharge above the seasonal median for the date, and
    the label says so."""
    if not discharge:
        return 0.0, "no river discharge data"
    days = range(min(2, len(discharge["discharge"])))
    tag = "live" if discharge.get("live") else \
        f"cached {discharge['fetched_at'][:10]}"
    base = discharge.get("q_dem_baseline")
    if base is None:
        d = max(days, key=lambda i: discharge["discharge"][i]
                - discharge["median"][i])
        q, med = discharge["discharge"][d], discharge["median"][d]
        best = max(q - med, 0.0)
        return best, (f"GloFAS {tag}: {q:.0f} m3/s, {best:.0f} above the "
                      f"{med:.0f} m3/s seasonal median (no dry-season "
                      f"baseline available)")
    q = max(discharge["discharge"][i] for i in days)
    best = max(q - base, 0.0)
    return best, (f"GloFAS {tag}: {q:.0f} m3/s, {best:.0f} above the "
                  f"{base:.0f} m3/s dry-season (DEM) baseline")


def water_mask(elevation, cell_size, pad_m=0.0):
    """Bool grid (row 0 = south, same orientation as elevation) marking
    permanent river/lake surface, from OSM `natural=water`/`water=river`
    polygons and `waterway=river` centrelines (buffered by one cell plus
    pad_m). False (no mask) on any fetch failure — callers should treat
    that as 'nothing excluded', not 'no water here'."""
    rows, cols = elevation.shape
    mask = np.zeros((rows, cols), dtype=bool)
    # A successful, non-empty mask is cached on disk (assets/masks/), so a
    # flaky Overpass cannot silently change the alerts between builds.
    path = _mask_cache_path(rows, cols, pad_m)
    if os.path.exists(path):
        try:
            cached = np.load(path)
            if cached.shape == (rows, cols) and cached.any():
                print(f"[river] water mask: {int(cached.sum())} cells from "
                      f"OSM (cached {os.path.basename(path)})")
                return cached.astype(bool)
            print(f"[river] cached water mask {path} is empty or the wrong "
                  f"shape -> refetching")
        except Exception as exc:
            print(f"[river] cached water mask unreadable "
                  f"({type(exc).__name__}: {exc}) -> refetching")
    try:
        import requests
        from PIL import Image, ImageDraw

        half_lat = rows * cell_size / 2.0 / 111_320.0
        half_lon = cols * cell_size / 2.0 / (
            111_320.0 * np.cos(np.radians(config.BASIN_LAT)))
        s, n = config.BASIN_LAT - half_lat, config.BASIN_LAT + half_lat
        w, e = config.BASIN_LON - half_lon, config.BASIN_LON + half_lon
        q = (f'[out:json][timeout:25];('
             f'way["natural"="water"]({s},{w},{n},{e});'
             f'way["water"="river"]({s},{w},{n},{e});'
             f'way["waterway"="river"]({s},{w},{n},{e});'
             f');out geom;')
        elements, last_exc = None, None
        for url in OVERPASS_URLS:      # same query; mirrors only on failure
            try:
                r = requests.post(url, data={"data": q},
                                  headers={"User-Agent":
                                           "HydroTwin/1.0 flood-demo"},
                                  timeout=(5, 30))
                r.raise_for_status()
                elements = r.json().get("elements", [])
                if elements:
                    break
            except Exception as exc:
                last_exc = exc
        if elements is None:
            raise last_exc
        img = Image.new("L", (cols, rows), 0)
        draw = ImageDraw.Draw(img)
        buf_cells = max(1, int(round((cell_size / 2.0 + pad_m) / cell_size)))
        found = False
        for el in elements:
            geom = el.get("geometry")
            if not geom:
                continue
            pts = [terrain.latlon_to_rc(p["lat"], p["lon"], rows, cols)
                   for p in geom]
            pts = [(c, rows - 1 - row) for row, c in
                   (p for p in pts if p is not None)]   # PIL y-down -> north-up row
            if len(pts) < 2:
                continue
            found = True
            if el.get("tags", {}).get("waterway") == "river" and \
                    el.get("tags", {}).get("natural") != "water":
                draw.line(pts, fill=255, width=buf_cells * 2)
            else:
                draw.polygon(pts, fill=255)
        if found:
            mask = np.flipud(np.asarray(img, dtype=bool))  # back to row-0=south
            print(f"[river] water mask: {int(mask.sum())} cells from OSM "
                  f"(fetched live)")
            if mask.any():
                try:
                    os.makedirs(MASK_CACHE_DIR, exist_ok=True)
                    np.save(path, mask)
                    print(f"[river] water mask cached -> {path}")
                except Exception as exc:
                    print(f"[river] could not cache the water mask "
                          f"({type(exc).__name__}: {exc})")
        else:
            print("[river] no OSM water features in frame -> no mask")
    except Exception as exc:
        print(f"[river] water mask fetch failed ({type(exc).__name__}: "
              f"{exc}) -> no mask")
    return mask
