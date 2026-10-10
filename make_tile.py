"""3D-printable tiles of the Yamuna at Old Delhi, from the model's own grid.

    python make_tile.py [--size-mm 120] [--exaggeration 25] [--stage 208.66]

Writes to outputs/print/:
  terrain.stl      the ground (channel-conditioned DEM)
  flood.stl        the same ground with the model's water surface at the
                   given Old Railway Bridge level laid on top
  water_only.stl   just the water body, for a second colour
  README.txt       scale, exaggeration and print notes

These are for explaining the flood, not for measuring anything: the
vertical scale is exaggerated (the real relief here is about 20 m across
4 km) and water at tabletop scale does not behave like a river.
"""

import os
import struct
import sys

import numpy as np
from scipy.ndimage import zoom

import stagelib

# window of the 150x150 Delhi grid (rows from south, cols from west):
# Majnu ka Tilla side down to Raj Ghat, both banks
R0, R1, C0, C1 = 40, 112, 44, 116
UPSAMPLE = 3                    # smooth the 67 m cells for printing
BASE_MM = 3.0                   # solid base under the lowest ground
WATER_MIN_M = 0.10


def _write_stl(path, tris):
    tris = np.asarray(tris, dtype=np.float32)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    with open(path, "wb") as f:
        f.write(b"HydroTwin tile".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)),
                                         ("a", "<u2")])
        rec["n"], rec["v"] = n, tris
        f.write(rec.tobytes())
    return len(tris)


def _solid(top, bottom, dx, keep=None):
    """Watertight solid between two height fields (mm) on a regular grid.
    keep: bool grid of cells (quads) to include; None = all."""
    rows, cols = top.shape
    ys = np.arange(rows)[:, None] * dx * np.ones((1, cols))
    xs = np.ones((rows, 1)) * np.arange(cols)[None, :] * dx
    P = lambda z: np.stack([xs, ys, z], axis=-1)
    T, B = P(top), P(bottom)
    if keep is None:
        keep = np.ones((rows - 1, cols - 1), bool)
    tris = []
    rr, cc = np.where(keep)
    for r, c in zip(rr, cc):
        a, b, d, e = (r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)
        tris += [(T[a], T[b], T[e]), (T[a], T[e], T[d]),          # top
                 (B[a], B[e], B[b]), (B[a], B[d], B[e])]          # bottom
        for (p, q), (nr, nc) in (((a, b), (r - 1, c)), ((b, e), (r, c + 1)),
                                 ((e, d), (r + 1, c)), ((d, a), (r, c - 1))):
            inside = 0 <= nr < rows - 1 and 0 <= nc < cols - 1 and keep[nr, nc]
            if not inside:                                        # wall
                tris += [(T[p], B[p], B[q]), (T[p], B[q], T[q])]
    return tris


def build(size_mm=120.0, exaggeration=25.0, stage=208.66, dem="srtm",
          out="outputs/print"):
    lib = stagelib.Library(dem)
    depth, q = lib.depth_at_stage(stage)
    ground = lib.elevation[R0:R1, C0:C1].astype(float)
    water = depth[R0:R1, C0:C1].astype(float)
    ground = zoom(ground, UPSAMPLE, order=1)
    water = zoom(water, UPSAMPLE, order=1)
    rows, cols = ground.shape
    span_m = (C1 - C0) * lib.cell
    mm_per_m = size_mm / span_m
    dx = size_mm / (cols - 1)
    zmm = lambda z: BASE_MM + (z - ground.min()) * mm_per_m * exaggeration

    g = zmm(ground)
    wet = water >= WATER_MIN_M
    surf = np.where(wet, zmm(ground + water), g)
    zero = np.zeros_like(g)

    os.makedirs(out, exist_ok=True)
    n1 = _write_stl(os.path.join(out, "terrain.stl"), _solid(g, zero, dx))
    n2 = _write_stl(os.path.join(out, "flood.stl"), _solid(surf, zero, dx))
    keep = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
    n3 = _write_stl(os.path.join(out, "water_only.stl"),
                    _solid(surf + 0.2, g, dx, keep))
    relief = ground.max() - ground.min()
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"HydroTwin printable tiles: Yamuna at Old Delhi\n\n"
            f"Area: {span_m / 1000:.1f} km x {(R1 - R0) * lib.cell / 1000:.1f}"
            f" km, north at the +Y edge.\n"
            f"Print size: {size_mm:.0f} x {size_mm * rows / cols:.0f} mm, "
            f"{g.max():.1f} mm tall (flood.stl: {surf.max():.1f} mm).\n"
            f"Horizontal scale 1:{1000 / mm_per_m:,.0f}.\n"
            f"Vertical exaggeration x{exaggeration:g} (real relief "
            f"{relief:.0f} m would be {relief * mm_per_m:.2f} mm).\n"
            f"Water: model surface at {stage} m at the Old Railway Bridge "
            f"(steady, river only, about {q:,.0f} m3/s in the model), "
            f"{lib.source}, river bed conditioned.\n\n"
            f"terrain.stl     ground only\n"
            f"flood.stl       ground + water surface, one piece\n"
            f"water_only.stl  the water body alone, for a second colour "
            f"(sits on terrain.stl)\n\n"
            f"Print notes: 0.2 mm layers, no supports, 15% infill. For a "
            f"two-colour look on a one-colour printer, print flood.stl and "
            f"paint the raised water blue, or print terrain.stl and "
            f"water_only.stl separately.\n\n"
            f"This is a model for explaining the flood. It is not to "
            f"scale vertically, and it is not a measurement.\n")
    print(f"[tile] {out}: terrain {n1:,} tris, flood {n2:,}, water {n3:,}; "
          f"{size_mm:.0f} mm wide, x{exaggeration:g} vertical, "
          f"{g.max():.1f} mm tall; wet {wet.mean() * 100:.0f}% of tile")


if __name__ == "__main__":
    a = sys.argv[1:]
    kw = {}
    for flag, key in (("--size-mm", "size_mm"), ("--exaggeration",
                      "exaggeration"), ("--stage", "stage")):
        if flag in a:
            kw[key] = float(a[a.index(flag) + 1])
    build(**kw)
