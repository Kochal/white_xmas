"""Probability, change, trend and significance from yearly white/green series.

All functions take float32 arrays shaped ``(year, ...)`` with 1 = white, 0 = green and
NaN = unknown, and return arrays shaped ``(...)``. NaN stays NaN throughout.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr


def probability(w: np.ndarray, min_valid: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Share of white years in %, and the number of valid years.

    Probability is NaN where fewer than ``min_valid`` years have data.
    """
    valid = ~np.isnan(w)
    n = valid.sum(axis=0).astype("int16")
    s = np.where(valid, w, 0).sum(axis=0, dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(n >= max(min_valid, 1), 100.0 * s / n, np.nan)
    return p.astype("float32"), n


def ols_trend_pp_per_decade(w: np.ndarray, years: np.ndarray) -> np.ndarray:
    """OLS slope of the 0/1 series against year, in percentage points per decade.

    Uses only the valid years of each cell; NaN where fewer than 3 valid years.
    """
    years = np.asarray(years, dtype="float64").reshape((-1,) + (1,) * (w.ndim - 1))
    valid = ~np.isnan(w)
    n = valid.sum(axis=0)
    x = np.where(valid, w, 0.0).astype("float64")
    t = np.where(valid, years, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        tbar = t.sum(axis=0) / n
        xbar = x.sum(axis=0) / n
        dt = np.where(valid, years - tbar, 0.0)
        sxy = (dt * (x - xbar)).sum(axis=0)
        sxx = (dt**2).sum(axis=0)
        slope = sxy / sxx * 100.0 * 10.0
    return np.where(n >= 3, slope, np.nan).astype("float32")


def mann_kendall_p(w: np.ndarray) -> np.ndarray:
    """Two-sided Mann-Kendall p-value per cell for 0/1 series (ties corrected).

    Equivalent to ``pymannkendall.original_test`` on the valid years of each cell, vectorised.
    Constant series give p = 1; cells with fewer than 3 valid years give NaN.
    """
    n_years = w.shape[0]
    flat = w.reshape(n_years, -1).astype("float32")
    valid = ~np.isnan(flat)
    s = np.zeros(flat.shape[1], dtype="float64")
    for i in range(n_years - 1):
        d = flat[i + 1 :] - flat[i]  # NaN where either is missing
        s += np.nansum(np.sign(d), axis=0)
    n = valid.sum(axis=0).astype("float64")
    ones = np.where(valid, flat, 0).sum(axis=0).astype("float64")
    zeros = n - ones
    # ties correction for binary data: two tie groups of size n0 and n1
    tie = zeros * (zeros - 1) * (2 * zeros + 5) + ones * (ones - 1) * (2 * ones + 5)
    var = (n * (n - 1) * (2 * n + 5) - tie) / 18.0
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(s > 0, (s - 1) / np.sqrt(var), np.where(s < 0, (s + 1) / np.sqrt(var), 0))
        p = 2 * (1 - ndtr(np.abs(z)))
    p = np.where(var > 0, p, 1.0)
    p = np.where(n >= 3, p, np.nan)
    return p.reshape(w.shape[1:]).astype("float64")


def glacier_flag(
    any_white: np.ndarray, glacier_fraction: np.ndarray, min_fraction: float = 0.5
) -> np.ndarray:
    """Glacier cells: inside the glacier mask and white (any day) in every valid year."""
    valid = ~np.isnan(any_white)
    n = valid.sum(axis=0)
    always = (np.where(valid, any_white, 1.0) == 1.0).all(axis=0) & (n > 0)
    frac = np.nan_to_num(glacier_fraction, nan=0.0)
    return always & (frac >= min_fraction)


# --------------------------------------------------------------------------- pipeline step
INDICATORS_VERSION = 1


def min_valid_years(n_years: int, fraction: float = 0.8) -> int:
    return int(np.ceil(fraction * n_years))


def compute_band(
    cube_cm: np.ndarray,
    years: np.ndarray,
    glacier_fraction: np.ndarray,
    definitions: list[str],
    windows: list,
    change_pair: tuple[str, str],
    threshold_cm: float,
    glacier_min_fraction: float = 0.5,
    require_always_white: bool = True,
    min_valid_fraction: float = 0.8,
) -> dict[str, np.ndarray]:
    """All indicators for a block of cells. ``cube_cm`` is (year, day, *cells)."""
    from .definitions import white

    years = np.asarray(years)
    cells = cube_cm.shape[2:]
    nd, nw = len(definitions), len(windows)
    out = {
        "probability": np.full((nd, nw, *cells), np.nan, "float32"),
        "n_valid": np.zeros((nd, nw, *cells), "int16"),
        "change": np.full((nd, *cells), np.nan, "float32"),
        "trend": np.full((nd, *cells), np.nan, "float32"),
        "trend_p": np.full((nd, *cells), np.nan, "float32"),
    }
    full = next(w for w in windows if w.kind == "full")
    wid = [w.id for w in windows]
    land = (cube_cm != -1).any(axis=(0, 1))
    for di, d in enumerate(definitions):
        w = white(cube_cm, d, threshold_cm)
        for wi, win in enumerate(windows):
            sel = (years >= win.start) & (years <= win.end)
            p, n = probability(w[sel], min_valid_years(win.n_years, min_valid_fraction))
            out["probability"][di, wi], out["n_valid"][di, wi] = p, n
        a, b = wid.index(change_pair[0]), wid.index(change_pair[1])
        out["change"][di] = out["probability"][di, b] - out["probability"][di, a]
        sel = (years >= full.start) & (years <= full.end)
        wl = w[sel][:, land]  # only land cells: Mann-Kendall is the slow part
        tr = np.full(cells, np.nan, "float32")
        pv = np.full(cells, np.nan, "float32")
        tr[land] = ols_trend_pp_per_decade(wl, years[sel])
        pv[land] = mann_kendall_p(wl)
        enough = out["n_valid"][di, wid.index(full.id)] >= min_valid_years(
            full.n_years, min_valid_fraction
        )
        out["trend"][di] = np.where(enough, tr, np.nan)
        out["trend_p"][di] = np.where(enough, pv, np.nan)
    any_w = white(cube_cm, "any_day", threshold_cm)
    sel = (years >= full.start) & (years <= full.end)
    if require_always_white:
        out["glacier"] = glacier_flag(any_w[sel], glacier_fraction, glacier_min_fraction)
    else:
        out["glacier"] = (np.nan_to_num(glacier_fraction) >= glacier_min_fraction) & land
    out["land"] = land
    return out


def fingerprint(cfg, cube_fp: str) -> str:
    import hashlib

    h = hashlib.sha256(cube_fp.encode())
    h.update(
        cfg.section_hash(
            "years", "threshold_cm", "definitions", "windows", "trend", "glacier"
        ).encode()
    )
    h.update(f"ind{INDICATORS_VERSION}".encode())
    return h.hexdigest()[:16]


def compute_all(cfg, paths, force: bool = False, band: int = 50):
    """Stream over latitude bands of the cube and write ``indicators.zarr``."""
    import json
    import logging
    import shutil
    import warnings

    import zarr
    from zarr.codecs import BloscCodec

    log = logging.getLogger(__name__)
    src = zarr.open_group(str(paths.cube), mode="r")
    cube_fp = str(src.attrs.get("input_fingerprint", ""))
    fp = fingerprint(cfg, cube_fp)
    out = paths.indicators
    if out.exists() and not force:
        try:
            if zarr.open_group(str(out), mode="r").attrs.get("fingerprint") == fp:
                log.info("indicators up to date (%s); skipping", fp)
                return out
        except Exception:  # noqa: BLE001
            pass

    cube = src["snow_depth_cm"]
    years = src["year"][:]
    cy = [int(y) for y in years]
    if cy[0] > cfg.first_year or cy[-1] < cfg.last_year:
        raise ValueError(
            f"cube covers {cy[0]}-{cy[-1]}, config wants {cfg.first_year}-{cfg.last_year}"
        )
    keep = (years >= cfg.first_year) & (years <= cfg.last_year)
    years = years[keep]
    ny, nx = cube.shape[2:]
    glac = src["glacier_fraction"] if "glacier_fraction" in src else None
    defs, wins = cfg.definition_ids, cfg.windows()
    g = cfg.glacier

    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    root = zarr.open_group(str(tmp), mode="w")
    comp = BloscCodec(cname="zstd", clevel=5, shuffle="bitshuffle")
    ch = (500, 500)

    def arr(name, shape, dtype, fill, dims, **attrs):
        z = root.create_array(
            name,
            shape=shape,
            chunks=(*shape[:-2], *ch),
            dtype=dtype,
            fill_value=fill,
            compressors=comp,
            dimension_names=dims,
        )
        z.attrs.update(attrs)
        return z

    nd, nw = len(defs), len(wins)
    z = {
        "probability": arr(
            "probability",
            (nd, nw, ny, nx),
            "float32",
            np.nan,
            ["definition", "window", "lat", "lon"],
            units="%",
        ),
        "n_valid": arr(
            "n_valid",
            (nd, nw, ny, nx),
            "int16",
            0,
            ["definition", "window", "lat", "lon"],
            units="years",
        ),
        "change": arr(
            "change",
            (nd, ny, nx),
            "float32",
            np.nan,
            ["definition", "lat", "lon"],
            units="pp",
            **{"from": cfg.change_pair[0], "to": cfg.change_pair[1]},
        ),
        "trend": arr(
            "trend",
            (nd, ny, nx),
            "float32",
            np.nan,
            ["definition", "lat", "lon"],
            units="pp/decade",
            method="OLS on 0/1 yearly series",
            window=cfg.full_window().id,
        ),
        "trend_p": arr(
            "trend_p",
            (nd, ny, nx),
            "float32",
            np.nan,
            ["definition", "lat", "lon"],
            units="1",
            method="Mann-Kendall two-sided, ties corrected",
        ),
        "glacier": arr("glacier", (ny, nx), "bool", False, ["lat", "lon"]),
        "land": arr("land", (ny, nx), "bool", False, ["lat", "lon"]),
    }
    for j0 in range(0, ny, band):
        j1 = min(ny, j0 + band)
        block = cube[:, :, j0:j1, :][keep]
        gf = glac[j0:j1, :] if glac is not None else np.zeros((j1 - j0, nx), "float32")
        res = compute_band(
            block,
            years,
            gf,
            defs,
            wins,
            cfg.change_pair,
            cfg.threshold_cm,
            float(g.get("min_fraction", 0.5)),
            bool(g.get("require_always_white", True)),
            float(cfg.raw.get("min_valid_fraction", 0.8)),
        )
        for k, v in res.items():
            z[k][..., j0:j1, :] = v
        log.info("indicators: rows %d-%d of %d", j0, j1, ny)

    for name, vals in [("lat", src["lat"][:]), ("lon", src["lon"][:])]:
        a = root.create_array(name, data=vals, chunks=vals.shape, dimension_names=[name])
        a.attrs["units"] = "degrees_north" if name == "lat" else "degrees_east"
    root.attrs.update(
        {
            "fingerprint": fp,
            "definitions": json.dumps(defs),
            "windows": json.dumps([w.as_dict() for w in wins]),
            "threshold_cm": cfg.threshold_cm,
            "years": json.dumps([int(years[0]), int(years[-1])]),
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        zarr.consolidate_metadata(str(tmp))
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    log.info("indicators written to %s", out)
    return out
