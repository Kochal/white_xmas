"""Cloud Optimized GeoTIFFs (Float32, NaN nodata, overviews, EPSG:4326) for open data."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def write_cog(path: Path, data: np.ndarray, res: float = 0.1, tags: dict | None = None) -> int:
    """Write a 2-D grid whose cell centres are lon -180 + res*i, lat 90 - res*j."""
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(data, dtype="float32")
    profile = {
        "driver": "COG",
        "width": arr.shape[1],
        "height": arr.shape[0],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-180.0 - res / 2, 90.0 + res / 2, res, res),
        "nodata": float("nan"),
        "compress": "DEFLATE",
        "predictor": 3,
        "blocksize": 512,
        "overview_resampling": "average",
        "BIGTIFF": "IF_SAFER",
    }
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(arr, 1)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
    tmp.replace(path)
    return path.stat().st_size
