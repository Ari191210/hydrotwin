"""River inflow for HydroTwin.

The physics domain is a few km across, so a big river's flood arrives from
upstream through the grid edge, not from rain on the grid. This module finds
where the river enters (a case's explicit inflow point, snapped to the
lowest DEM cell on that edge) and turns a discharge in m3/s into a per-cell
source term for OverlandFlow.

SRTM was flown in February 2000, so the DEM already holds the river at its
dry-season surface. Only discharge ABOVE the seasonal median is routed in;
on a normal day that is ~0 and the river adds nothing.
"""

import numpy as np

import config
import terrain

# edge -> (node (row, col) at along-edge index k and inward offset d)
_EDGES = {
    "south": lambda k, d, R, C: (d, k),
    "north": lambda k, d, R, C: (R - 1 - d, k),
    "west": lambda k, d, R, C: (k, d),
    "east": lambda k, d, R, C: (k, C - 1 - d),
}


def find_inflow(elevation, cell_size, point=None):
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
    print(f"[river] {info['name']} enters across the {edge} edge at cell "
          f"{info['rc']} (bed {bed:.1f} m, channel ~{info['width_m']} m, "
          f"{len(nodes)} inflow cells)")
    return info


def excess_from_glofas(discharge):
    """Discharge above the seasonal median over the next two forecast days,
    in m3/s, plus a source label. 0 when the river is at or below normal."""
    if not discharge:
        return 0.0, "no river discharge data"
    days = range(min(2, len(discharge["discharge"])))
    d = max(days, key=lambda i: discharge["discharge"][i]
            - discharge["median"][i])
    q, med = discharge["discharge"][d], discharge["median"][d]
    best = q - med
    tag = "live" if discharge.get("live") else \
        f"cached {discharge['fetched_at'][:10]}"
    return max(best, 0.0), (f"GloFAS {tag}: {q:.0f} m3/s, {max(best, 0):.0f} "
                            f"above the {med:.0f} m3/s seasonal median")


def water_mask(elevation, cell_size, pad_m=0.0):
    """Bool grid (row 0 = south, same orientation as elevation) marking
    permanent river/lake surface, from OSM `natural=water`/`water=river`
    polygons and `waterway=river` centrelines (buffered by one cell plus
    pad_m). False (no mask) on any fetch failure — callers should treat
    that as 'nothing excluded', not 'no water here'."""
    rows, cols = elevation.shape
    mask = np.zeros((rows, cols), dtype=bool)
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
        r = requests.post("https://overpass-api.de/api/interpreter",
                          data={"data": q},
                          headers={"User-Agent": "HydroTwin/1.0 flood-demo"},
                          timeout=(5, 30))
        r.raise_for_status()
        img = Image.new("L", (cols, rows), 0)
        draw = ImageDraw.Draw(img)
        buf_cells = max(1, int(round((cell_size / 2.0 + pad_m) / cell_size)))
        found = False
        for el in r.json().get("elements", []):
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
            print(f"[river] water mask: {int(mask.sum())} cells from OSM")
        else:
            print("[river] no OSM water features in frame -> no mask")
    except Exception as exc:
        print(f"[river] water mask fetch failed ({type(exc).__name__}: "
              f"{exc}) -> no mask")
    return mask
