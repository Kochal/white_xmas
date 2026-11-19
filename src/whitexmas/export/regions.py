"""regions.json: area-weighted (cos lat) country statistics from Natural Earth admin-0 1:10m.

Key: the ISO 3166 alpha-3 code, taken from ``ISO_A3``, else ``ISO_A3_EH`` (France and Norway are
-99 in ``ISO_A3``), else Natural Earth's own ``ADM0_A3`` (Kosovo, Somaliland, N. Cyprus, …).
Natural Earth splits a few countries into several features that share that key (Kazakhstan and
the leased Baikonur area; Australia and its small island territories; France and Clipperton;
Brazil and the Brazilian Island). Those parts are dissolved into one row, named after the part
with the most land cells, so ``iso_a3`` is unique in regions.json.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)
NE_ZIP = "ne_10m_admin_0_countries.zip"


def read_countries(zip_path: Path) -> list[dict]:
    import pyogrio
    import shapely

    src = f"/vsizip/{zip_path.as_posix()}/ne_10m_admin_0_countries.shp"
    meta, _, geoms, fields = pyogrio.raw.read(
        src, columns=["ISO_A3", "ISO_A3_EH", "ADM0_A3", "NAME"]
    )
    cols = dict(zip(meta["fields"], fields, strict=True))
    out = []
    for k, wkb in enumerate(geoms):
        iso = cols["ISO_A3"][k]
        if not iso or iso == "-99":
            iso = cols["ISO_A3_EH"][k]
        if not iso or iso == "-99":
            iso = cols["ADM0_A3"][k]
        out.append({"iso_a3": iso, "name": cols["NAME"][k], "geom": shapely.from_wkb(wkb)})
    return out


def rasterize_countries(countries: list[dict], ny: int = 1801, nx: int = 3600, res: float = 0.1):
    """Country index per cell (-1 = none); a cell belongs to the polygon holding its centre."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    transform = from_origin(-180.0 - res / 2, 90.0 + res / 2, res, res)
    shapes = [(c["geom"], k) for k, c in enumerate(countries) if c["geom"] is not None]
    return rasterize(shapes, out_shape=(ny, nx), transform=transform, fill=-1, dtype="int32")


def regional_means(
    country_idx: np.ndarray,
    p_then: np.ndarray,
    p_now: np.ndarray,
    glacier: np.ndarray,
    lat: np.ndarray,
    n_regions: int,
):
    """cos(lat)-weighted means per region over non-glacier cells valid in both windows."""
    w = np.cos(np.radians(lat))[:, None] * np.ones_like(p_then, dtype="float64")
    ok = np.isfinite(p_then) & np.isfinite(p_now) & ~glacier & (country_idx >= 0)
    idx = country_idx[ok]
    ws = np.bincount(idx, weights=w[ok], minlength=n_regions)
    then = np.bincount(idx, weights=(w * np.nan_to_num(p_then))[ok], minlength=n_regions)
    now = np.bincount(idx, weights=(w * np.nan_to_num(p_now))[ok], minlength=n_regions)
    with np.errstate(invalid="ignore", divide="ignore"):
        return then / ws, now / ws, ws


def build_regions(
    ext_dir: Path,
    p_then: np.ndarray,
    p_now: np.ndarray,
    glacier: np.ndarray,
    lat: np.ndarray,
    definition: str,
    windows: dict[str, str],
    extras: list[tuple[str, str, np.ndarray, np.ndarray]] | None = None,
) -> dict:
    """``extras``: (then field, now field, p_then, p_now) for other thresholds (contract v1.5),
    averaged the same way and appended after ``change``."""
    extras = extras or []
    countries = read_countries(ext_dir / NE_ZIP)
    feature_idx = rasterize_countries(countries, *p_then.shape)
    keys = sorted({c["iso_a3"] for c in countries})
    group_of = np.array([keys.index(c["iso_a3"]) for c in countries] + [-1], dtype="int32")
    idx = group_of[feature_idx]  # feature -1 (no country) maps to the trailing -1
    then, now, ws = regional_means(idx, p_then, p_now, glacier, lat, len(keys))
    extra_means = [
        regional_means(idx, e_then, e_now, glacier, lat, len(keys))[:2]
        for _, _, e_then, e_now in extras
    ]
    # name each group after its feature with the most cells
    counts = np.bincount(feature_idx[feature_idx >= 0], minlength=len(countries))
    rows = []
    for g, key in enumerate(keys):
        if ws[g] <= 0:
            continue
        members = [k for k, c in enumerate(countries) if c["iso_a3"] == key]
        name = countries[max(members, key=lambda k: counts[k])]["name"]
        a, b = round(float(then[g]), 1), round(float(now[g]), 1)
        row = [key, name, a, b, round(b - a, 1)]
        for e_then, e_now in extra_means:
            row += [round(float(e_then[g]), 1), round(float(e_now[g]), 1)]
        rows.append(row)
    rows.sort(key=lambda r: r[1])
    log.info("regions: %d countries with land cells", len(rows))
    return {
        "definition": definition,
        "windows": windows,
        "fields": ["iso_a3", "name", "p_then", "p_now", "change"]
        + [f for f_then, f_now, _, _ in extras for f in (f_then, f_now)],
        "attribution": "Borders: Natural Earth (public domain)",
        "rows": rows,
    }
