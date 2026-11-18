"""The observed ERA5-Land baseline that the model changes are applied to.

Preferred source: the pipeline's ``interim/indicators.zarr`` (probability and number of valid
years for the 1996-2025 window, per definition). Until that exists, a **placeholder** for
development only: the legacy GeoTIFF from the old notebook (any-hour rule, 2015-2024, 0-90 °N,
ocean stored as 0 %). Outputs built from the placeholder say so in their attributes and must not
be published.

Grid: ERA5-Land 0.1°, north-up, lat 90 … -90 (1801 rows), lon -180 … 179.9 (3600 columns).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..paths import DataPaths

log = logging.getLogger(__name__)

NY, NX = 1801, 3600
LEGACY_TIF = Path(
    r"C:\Users\AlexanderKoch\TransparentEarth\lx3\scripts\white_christmas"
    r"\white_christmas_probability_pct_2015_2024.tif"
)


def target_grid() -> tuple[np.ndarray, np.ndarray]:
    return 90.0 - 0.1 * np.arange(NY), -180.0 + 0.1 * np.arange(NX)


@dataclass
class Baseline:
    p: np.ndarray  # (NY, NX) float32 %, NaN = ocean / nodata
    n: np.ndarray  # (NY, NX) int16 years behind p
    land: np.ndarray  # (NY, NX) bool
    glacier: np.ndarray  # (NY, NX) bool
    source: str  # "indicators" or "placeholder-legacy-geotiff"
    window: str

    @property
    def placeholder(self) -> bool:
        return self.source != "indicators"


def load_baseline(paths: DataPaths, definition: str, window: str = "1996_2025") -> Baseline:
    if paths.indicators.exists():
        return _from_indicators(paths.indicators, definition, window)
    log.warning("indicators.zarr not found: using the legacy GeoTIFF PLACEHOLDER baseline")
    return _from_legacy(LEGACY_TIF)


def _from_indicators(path: Path, definition: str, window: str) -> Baseline:
    import zarr

    z = zarr.open_group(str(path), mode="r")
    defs = json.loads(z.attrs["definitions"])
    wins = [w["id"] for w in json.loads(z.attrs["windows"])]
    di, wi = defs.index(definition), wins.index(window)
    p = np.asarray(z["probability"][di, wi], dtype="float32")
    n = np.asarray(z["n_valid"][di, wi], dtype="int16")
    land = np.asarray(z["land"][:], dtype=bool)
    glacier = np.asarray(z["glacier"][:], dtype=bool)
    return Baseline(p, n, land, glacier, "indicators", window)


def _from_legacy(tif: Path) -> Baseline:
    import rasterio

    with rasterio.open(tif) as r:
        top = r.read(1).astype("float32")  # 901 rows, 90 .. 0 °N
    p = np.full((NY, NX), np.nan, dtype="float32")
    p[: top.shape[0]] = top
    land = np.isfinite(p)
    n = np.where(land, 10, 0).astype("int16")
    return Baseline(p, n, land, np.zeros((NY, NX), bool), "placeholder-legacy-geotiff", "2015_2024")


def era5_window_frequency(
    paths: DataPaths, definition: str, start: int, end: int, threshold_cm: float = 1.0
) -> np.ndarray | None:
    """ERA5-Land white-Christmas frequency (0-1) for ``start..end`` from the pipeline's snow
    cube, for validating the models. None when the cube does not exist yet."""
    if not paths.cube.exists():
        return None
    import zarr

    from ..definitions import white

    z = zarr.open_group(str(paths.cube), mode="r")
    years = np.asarray(z["year"][:])
    sel = np.where((years >= start) & (years <= end))[0]
    if len(sel) == 0:
        return None
    cube = z["snow_depth_cm"]
    out = np.full((NY, NX), np.nan, dtype="float32")
    band = 150
    for j0 in range(0, NY, band):
        j1 = min(NY, j0 + band)
        block = np.asarray(cube[int(sel[0]) : int(sel[-1]) + 1, :, j0:j1, :])
        w = white(block, definition, threshold_cm)
        with np.errstate(invalid="ignore"):
            valid = np.isfinite(w).sum(axis=0)
            out[j0:j1] = np.where(valid > 0, np.nansum(w, axis=0) / np.maximum(valid, 1), np.nan)
    return out
