"""Terrain loading for HydroTwin.

Order of attempts:
  1. OpenTopography SRTM (only if OPENTOPO_API_KEY is set in the env)
  2. AWS Terrain Tiles (terrarium encoding, no key needed)
  3. Synthetic river valley (always works, fully offline)

Every loader returns (elevation, cell_size_m, source_label) where elevation is a
(GRID_ROWS, GRID_COLS) float array with row 0 = SOUTH edge (Landlab convention).
"""

import io
import math
import os

import numpy as np

import config


def load_terrain():
    """Return (elevation_2d, cell_size_m, source_label). Never raises."""
    loaders = []
    if os.environ.get("OPENTOPO_API_KEY"):
        loaders.append(("OpenTopography SRTMGL1", _from_opentopography))
    loaders.append(("AWS Terrain Tiles (SRTM)", _from_aws_terrain_tiles))

    for label, loader in loaders:
        try:
            elev, cell = loader()
            _sanity_check(elev)
            elev = _fill_noise_pits(elev)
            print(f"[terrain] Using real DEM: {label} "
                  f"({elev.shape[0]}x{elev.shape[1]} cells, {cell:.1f} m/cell, "
                  f"elev {elev.min():.0f}-{elev.max():.0f} m)")
            return elev, cell, label
        except Exception as exc:  # any failure -> next source, never block
            print(f"[terrain] {label} failed ({type(exc).__name__}: {exc}) "
                  f"-> trying next source")

    elev, cell = _synthetic_valley()
    print(f"[terrain] Using SYNTHETIC terrain (river valley, "
          f"{elev.shape[0]}x{elev.shape[1]} cells, {cell:.1f} m/cell)")
    return elev, cell, "synthetic river valley"


def _fill_noise_pits(elev):
    """Light smoothing of real DEMs. Raw SRTM at ~30 m is full of single-cell
    pits that trap water as speckle; a small gaussian keeps the valleys but
    lets overland flow coalesce into channels."""
    from scipy.ndimage import gaussian_filter

    return gaussian_filter(elev, sigma=1.2)


def _sanity_check(elev):
    if elev.shape != (config.GRID_ROWS, config.GRID_COLS):
        raise ValueError(f"bad shape {elev.shape}")
    if not np.isfinite(elev).all():
        raise ValueError("non-finite elevations")
    if elev.max() - elev.min() < 1.0:
        raise ValueError("terrain is flat (ocean tile or nodata)")
    if elev.min() < -500 or elev.max() > 9000:
        raise ValueError(f"implausible elevation range {elev.min()}..{elev.max()}")


def _from_opentopography():
    import requests

    half_deg = (config.GRID_ROWS * config.CELL_SIZE_M / 2.0) / 111_320.0
    url = "https://portal.opentopography.org/API/globaldem"
    params = {
        "demtype": "SRTMGL1",
        "south": config.BASIN_LAT - half_deg,
        "north": config.BASIN_LAT + half_deg,
        "west": config.BASIN_LON - half_deg,
        "east": config.BASIN_LON + half_deg,
        "outputFormat": "AAIGrid",
        "API_Key": os.environ["OPENTOPO_API_KEY"],
    }
    r = requests.get(url, params=params, timeout=(5, 20))
    r.raise_for_status()
    header, grid = _parse_aaigrid(r.text)
    elev = _center_crop(grid, config.GRID_ROWS, config.GRID_COLS)
    elev = np.flipud(elev)  # AAIGrid row 0 = north; Landlab wants row 0 = south
    return elev.astype(float), header.get("cellsize_m", 30.0)


def _parse_aaigrid(text):
    lines = text.strip().splitlines()
    header, data_start = {}, 0
    for i, line in enumerate(lines):
        parts = line.split()
        if len(parts) == 2 and parts[0].lower() in (
                "ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "nodata_value"):
            header[parts[0].lower()] = float(parts[1])
            data_start = i + 1
        else:
            break
    grid = np.loadtxt(lines[data_start:])
    nodata = header.get("nodata_value")
    if nodata is not None:
        grid = np.where(grid == nodata, np.nan, grid)
        grid = np.nan_to_num(grid, nan=np.nanmedian(grid))
    # cellsize is in degrees for SRTM; convert at basin latitude
    if "cellsize" in header:
        header["cellsize_m"] = header["cellsize"] * 111_320.0 * math.cos(
            math.radians(config.BASIN_LAT))
    return header, grid


def _from_aws_terrain_tiles(zoom=12):
    import requests
    from PIL import Image

    n = 2 ** zoom
    lat_r = math.radians(config.BASIN_LAT)
    xt = int((config.BASIN_LON + 180.0) / 360.0 * n)
    yt = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi)
             / 2.0 * n)
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{xt}/{yt}.png"
    r = requests.get(url, timeout=(5, 20))
    r.raise_for_status()
    rgb = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=float)
    elev = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
    elev = _center_crop(elev, config.GRID_ROWS, config.GRID_COLS)
    elev = np.flipud(elev)  # tile row 0 = north
    cell = 156_543.03392 * math.cos(lat_r) / n  # metres per pixel at this zoom
    return elev, cell


def _center_crop(a, rows, cols):
    if a.shape[0] < rows or a.shape[1] < cols:
        raise ValueError(f"source grid {a.shape} smaller than requested {rows}x{cols}")
    r0 = (a.shape[0] - rows) // 2
    c0 = (a.shape[1] - cols) // 2
    return a[r0:r0 + rows, c0:c0 + cols].copy()


def _synthetic_valley():
    """Sloping plane + carved meandering river channel + smooth noise."""
    from scipy.ndimage import gaussian_filter

    rows, cols, cell = config.GRID_ROWS, config.GRID_COLS, config.CELL_SIZE_M
    rng = np.random.default_rng(42)

    yy = np.arange(rows, dtype=float)[:, None]
    xx = np.arange(cols, dtype=float)[None, :]

    z = 40.0 * (yy / (rows - 1)) * np.ones((rows, cols))  # drains toward south (row 0)

    channel_center = cols / 2.0 + (cols / 6.0) * np.sin(
        2.0 * np.pi * 2.0 * yy[:, 0] / rows)
    dist = np.abs(xx - channel_center[:, None])            # cells from channel
    z -= 8.0 * np.exp(-((dist / 5.0) ** 2))                # carve the channel
    z += 20.0 * (dist / cols) ** 1.5                       # valley walls

    z += gaussian_filter(rng.normal(0.0, 1.0, (rows, cols)), sigma=3) * 2.0
    z -= z.min()
    return z, cell
