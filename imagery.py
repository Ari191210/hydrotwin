"""Satellite imagery draped over the 3D terrain.

Fetches Esri World Imagery tiles for exactly the Web-Mercator window the
terrain loader crops (same centre, same pixel origin), stitches them at a
higher zoom, and caches the result in assets/imagery/ so presets build
offline after the first run. Returns None on any failure; the viewer then
falls back to the shaded-relief texture.
"""

import io
import math
import os

import config
import terrain

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_HERE, "assets", "imagery")
TILE_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
ATTRIBUTION = "Esri World Imagery (Esri, Maxar, Earthstar Geographics)"
MAX_PX = 2048        # longest side of the stitched image
MAX_ZOOM = 18


def get_imagery(rows=None, cols=None):
    """PIL RGB image, north-up, covering the active terrain grid; or None."""
    from PIL import Image

    rows = rows or config.GRID_ROWS
    cols = cols or config.GRID_COLS
    zoom = config.TERRAIN_ZOOM
    k = 0
    while k < 6 and zoom + k < MAX_ZOOM and \
            max(rows, cols) * 2 ** (k + 1) <= MAX_PX:
        k += 1
    key = (f"{config.BASIN_LAT:.4f}_{config.BASIN_LON:.4f}_z{zoom}"
           f"_{rows}x{cols}_k{k}")
    path = os.path.join(CACHE_DIR, key + ".jpg")
    if os.path.exists(path):
        return Image.open(path).convert("RGB")

    try:
        import requests

        cx, cy = terrain._mercator_px(config.BASIN_LAT, config.BASIN_LON,
                                      zoom)
        x0, y0 = int(cx - cols / 2), int(cy - rows / 2)
        s = 2 ** k
        px0, py0 = x0 * s, y0 * s
        w, h = cols * s, rows * s
        zt = zoom + k
        tx0, tx1 = px0 // 256, (px0 + w - 1) // 256
        ty0, ty1 = py0 // 256, (py0 + h - 1) // 256
        mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256,
                                   (ty1 - ty0 + 1) * 256))
        sess = requests.Session()
        sess.headers["User-Agent"] = "HydroTwin/1.0 flood-demo"
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                r = sess.get(TILE_URL.format(z=zt, y=ty, x=tx),
                             timeout=(5, 20))
                r.raise_for_status()
                tile = Image.open(io.BytesIO(r.content)).convert("RGB")
                mosaic.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))
        img = mosaic.crop((px0 - tx0 * 256, py0 - ty0 * 256,
                           px0 - tx0 * 256 + w, py0 - ty0 * 256 + h))
        os.makedirs(CACHE_DIR, exist_ok=True)
        img.save(path, quality=88)
        print(f"[imagery] {ATTRIBUTION}: {w}x{h} px at zoom {zt} "
              f"({(tx1 - tx0 + 1) * (ty1 - ty0 + 1)} tiles, "
              f"{terrain.cell_size_m() / s:.1f} m/px)")
        return img
    except Exception as exc:
        print(f"[imagery] satellite fetch failed ({type(exc).__name__}: "
              f"{exc}) -> shaded relief")
        return None
