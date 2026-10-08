"""Print the georeferencing tags of the FABDEM tile (no assumptions)."""
import sys

import numpy as np
import tifffile

path = sys.argv[1] if len(sys.argv) > 1 else "assets/dem/N28E077_FABDEM_V1-2.tif"
with tifffile.TiffFile(path) as tf:
    page = tf.pages[0]
    print("shape", page.shape, "dtype", page.dtype, "compression", page.compression)
    for tag in page.tags.values():
        v = tag.value
        s = repr(v)
        print(f"  {tag.code} {tag.name}: {s[:300]}")
    print("geotiff_metadata:", tf.geotiff_metadata)
    a = page.asarray()
print("array", a.shape, a.dtype, "min", np.nanmin(a), "max", np.nanmax(a),
      "nan", int(np.isnan(a).sum()) if a.dtype.kind == "f" else 0,
      "== -9999:", int((a == -9999).sum()))
