"""Reading the downloaded CMIP6 subsets (``$WHITEXMAS_DATA/cmip6``).

Layout written by ``scripts/projections/cmip6_download.py``::

    cmip6/plan.json                         models, members, warming-level windows, files
    cmip6/snw/<model>/snw_day_<model>_<exp>_<member>_<grid>_<start>-<end>_xmas.nc
    cmip6/sftlf/<model>/sftlf_fx_<model>_<exp>_<member>_<grid>.nc
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_YEARS = re.compile(r"_(\d{4})\d*-(\d{4})\d*_xmas\.nc$")


@dataclass
class ModelField:
    times: list  # cftime datetimes
    values: np.ndarray  # (time, lat, lon) float32, kg m-2
    lat: np.ndarray
    lon: np.ndarray


def load_plan(cmip6_root: Path) -> dict:
    return json.loads((cmip6_root / "plan.json").read_text(encoding="utf-8"))


def snw_files(
    cmip6_root: Path, model: str, experiment: str, grid: str | None = None
) -> list[tuple[int, int, Path]]:
    """(first year, last year, path) of a model's subsets, optionally for one grid label."""
    out = []
    for p in sorted((cmip6_root / "snw" / model).glob(f"snw_day_{model}_{experiment}_*_xmas.nc")):
        m = _YEARS.search(p.name)
        if m and (grid is None or p.name.split("_")[5] == grid):
            out.append((int(m[1]), int(m[2]), p))
    return out


def model_grid(cmip6_root: Path, model: str, experiment: str) -> str:
    """Grid label to use: the scenario's (some models publish historical on two grids)."""
    for exp in (experiment, "ssp245", "historical"):
        grids = sorted({p.name.split("_")[5] for *_, p in snw_files(cmip6_root, model, exp)})
        if grids:
            return grids[0]
    raise FileNotFoundError(f"no snw files for {model}")


def load_window(cmip6_root: Path, model: str, experiment: str, y0: int, y1: int) -> ModelField:
    """Daily snw for Christmas seasons ``y0..y1`` (11 Dec of y to 8 Jan of y+1).

    Days up to 31 Dec 2014 come from ``historical``, later days from ``experiment``. The split
    is on the calendar date, not the season, so the 2014 season keeps its 1-8 Jan 2015 days
    (which live in the scenario files); a ``historical`` window that reaches 2014 reads them
    from ``ssp245``.
    """
    import xarray as xr

    coder = xr.coders.CFDatetimeCoder(use_cftime=True)
    times, vals, lat, lon = [], [], None, None
    grid = model_grid(cmip6_root, model, "ssp245")
    scenario = "ssp245" if experiment == "historical" else experiment
    for exp in ("historical", scenario):
        if exp == scenario and y1 < 2014:
            continue
        for a, b, path in snw_files(cmip6_root, model, exp, grid):
            if b < y0 or a > y1 + 1:
                continue
            with xr.open_dataset(path, decode_times=coder) as ds:
                t = ds["time"].values
                syear = np.array([d.year if d.month == 12 else d.year - 1 for d in t])
                cal_ok = np.array([d.year <= 2014 for d in t])
                if exp != "historical":
                    cal_ok = ~cal_ok
                sel = (syear >= y0) & (syear <= y1) & cal_ok
                if not sel.any():
                    continue
                times.extend(t[sel])
                vals.append(ds["snw"].values[sel].astype("float32"))
                if lat is None:
                    lat, lon = ds["lat"].values, ds["lon"].values
    if not vals:
        raise FileNotFoundError(f"no snw for {model} {experiment} {y0}-{y1}")
    order = np.argsort([t.toordinal() + t.hour / 24 for t in times], kind="stable")
    values = np.concatenate(vals)[order]
    times = [times[i] for i in order]
    return ModelField(times, values, lat, lon)


def land_fraction_pct(cmip6_root: Path, model: str, lat: np.ndarray, lon: np.ndarray):
    """Land fraction (%) on the model grid from ``sftlf``, or None when it is missing or its
    grid does not match the snow grid."""
    import xarray as xr

    files = sorted((cmip6_root / "sftlf" / model).glob("sftlf_*.nc"))
    if not files:
        return None
    with xr.open_dataset(files[0]) as ds:
        a = ds["sftlf"]
        if a.shape != (len(lat), len(lon)):
            return None
        if not (
            np.allclose(a["lat"].values, lat, atol=1e-3)
            and np.allclose(a["lon"].values, lon, atol=1e-3)
        ):
            return None
        v = a.values.astype("float32")
    return v * 100.0 if np.nanmax(v) <= 1.0 + 1e-6 else v


def box_mean(values: np.ndarray, mlat: np.ndarray, mlon: np.ndarray):
    """Aggregate a fine 0.1° global grid (ERA5-Land layout) onto a model grid.

    Each fine cell goes to the model cell whose centre is nearest (so model cell edges are the
    midpoints between centres). Returns the mean of the finite fine values per model cell and
    the share of fine cells that are finite (0-1)."""
    values = np.asarray(values, dtype="float64")
    ny, nx = values.shape
    flat = 90.0 - 0.1 * np.arange(ny)
    flon = np.mod(-180.0 + 0.1 * np.arange(nx), 360.0)
    iy = _nearest_index(mlat, flat, periodic=False)
    ix = _nearest_index(np.mod(mlon, 360.0), flon, periodic=True)
    cells = (iy[:, None] * len(mlon) + ix[None, :]).ravel()
    size = len(mlat) * len(mlon)
    ok = np.isfinite(values).ravel()
    tot = np.bincount(cells, minlength=size)
    cnt = np.bincount(cells, weights=ok.astype("float64"), minlength=size)
    s = np.bincount(cells, weights=np.where(ok, values.ravel(), 0.0), minlength=size)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, s / cnt, np.nan)
        cover = cnt / tot
    shape = (len(mlat), len(mlon))
    return mean.reshape(shape), cover.reshape(shape)


def box_fraction(mask: np.ndarray, mlat: np.ndarray, mlon: np.ndarray) -> np.ndarray:
    """Share (%) of a fine boolean mask in each model cell (land fraction without sftlf)."""
    return 100.0 * box_mean(np.asarray(mask, dtype="float64"), mlat, mlon)[0]


def _nearest_index(centres: np.ndarray, x: np.ndarray, periodic: bool) -> np.ndarray:
    """Index of the nearest model centre for every fine coordinate."""
    c = np.asarray(centres, dtype="float64")
    if periodic:
        d = np.abs(((x[:, None] - c[None, :]) + 180.0) % 360.0 - 180.0)
    else:
        d = np.abs(x[:, None] - c[None, :])
    return d.argmin(axis=1)
