"""Per model: white-Christmas counts in the baseline and in each warming-level window, and the
change in log-odds, all on the model's own grid.

Output per model: ``interim/projections/models/<model>.nc`` with

- ``k[window, definition, lat, lon]``: white years (fractional when days are pooled)
- ``n[window, definition, lat, lon]``: valid years
- ``delta[gwl, definition, lat, lon]``: log-odds change from the baseline (NaN off land)
- ``land_pct[lat, lon]``: land fraction used for the land mask

``window`` is ``baseline`` followed by the warming levels ("1.5", "2.0", "3.0").
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .cmip6 import box_fraction, land_fraction_pct, load_plan, load_window
from .frequency import season_cube, white_fraction, window_counts
from .settings import ProjPaths, ProjSettings
from .transfer import logodds_change

log = logging.getLogger(__name__)
# Recorded in every per-model file; files with another (or no) estimator are recomputed.
# "jeffreys-common-n": both windows smoothed with m = min(n_base, n_fut) (transfer.py).
ESTIMATOR = "jeffreys-common-n"

# ``era5_land_source`` of a per-model file: where the land mask came from for a model without a
# matching sftlf (the ERA5-Land baseline's source: "indicators", a placeholder id, or "none"
# when none was available), or SFTLF when the model's own land fraction was used.
SFTLF = "sftlf"
NO_ERA5_LAND = "none"
GOOD_LAND_SOURCES = ("indicators", SFTLF)


def land_source_rank(source: str | None) -> int:
    """2 = real ERA5-Land mask, 1 = placeholder, 0 = none or unknown."""
    if source == "indicators":
        return 2
    if source and source not in (NO_ERA5_LAND, SFTLF):
        return 1
    return 0


def counts_for_window(
    cmip6_root: Path, model: str, experiment: str, y0: int, y1: int, s: ProjSettings
):
    """k, n per definition for seasons y0..y1. Returns (k, n, lat, lon), k/n (def, lat, lon)."""
    f = load_window(cmip6_root, model, experiment, y0, y1)
    years, cube = season_cube(f.values, f.times)
    ks, ns = [], []
    for d in s.definitions:
        frac = white_fraction(cube, d, s.threshold_kg_m2, s.pool_days)
        k, n = window_counts(frac, years, y0, y1)
        ks.append(k.astype("float32"))
        ns.append(n.astype("int16"))
    return np.stack(ks), np.stack(ns), f.lat, f.lon


def model_land_pct(pp: ProjPaths, model: str, lat, lon, era5_land: np.ndarray | None):
    """(land fraction in % or None, whether the model needs the ERA5-Land fallback)."""
    pct = land_fraction_pct(pp.cmip6, model, lat, lon)
    if pct is not None:
        return pct, False
    if era5_land is not None:
        log.info("%s: no matching sftlf, land fraction from the ERA5-Land land mask", model)
        return box_fraction(era5_land, lat, lon), True
    log.warning("%s: no matching sftlf and no ERA5-Land mask: land = cells with data", model)
    return None, True


def model_land(
    pp: ProjPaths,
    model: str,
    lat: np.ndarray,
    lon: np.ndarray,
    n_base: np.ndarray,
    s: ProjSettings,
    era5_land: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray | None, bool]:
    """Land mask on the model grid: cells with baseline data and a land fraction of at least
    ``s.land_min_pct`` (from ``sftlf``, or the ERA5-Land mask where ``sftlf`` is missing).
    Many models report snw over the ocean too (sea ice), so the fraction test matters.
    Returns (land, land_pct, uses_era5_land)."""
    land_pct, uses_era5 = model_land_pct(pp, model, lat, lon, era5_land)
    land = np.asarray(n_base) > 0
    if land_pct is not None:
        land &= land_pct >= s.land_min_pct
    return land, land_pct, uses_era5


def masked_delta(kb, nb, kf, nf, land: np.ndarray) -> np.ndarray:
    """Log-odds change, NaN off land and wherever either window has no valid year."""
    d = logodds_change(kb, nb, kf, nf)
    return np.where(land & (nf > 0) & (nb > 0), d, np.nan).astype("float32")


def window_change(
    pp: ProjPaths,
    model: str,
    base: tuple[str, int, int],
    fut: tuple[str, int, int],
    s: ProjSettings,
    era5_land: np.ndarray | None = None,
) -> dict:
    """The production change computation for arbitrary windows ``(experiment, y0, y1)``:
    counts, land mask and masked log-odds change, shaped (definition, lat, lon). Used by
    :func:`compute_model`, the hindcast and the sensitivity script alike."""
    kb, nb, lat, lon = counts_for_window(pp.cmip6, model, *base, s)
    kf, nf, *_ = counts_for_window(pp.cmip6, model, *fut, s)
    land, land_pct, _ = model_land(pp, model, lat, lon, nb[0], s, era5_land)
    return {
        "kb": kb, "nb": nb, "kf": kf, "nf": nf, "lat": lat, "lon": lon,
        "land": land, "land_pct": land_pct, "delta": masked_delta(kb, nb, kf, nf, land),
    }  # fmt: skip


def compute_model(
    pp: ProjPaths,
    model: str,
    s: ProjSettings,
    era5_land: np.ndarray | None = None,
    era5_land_source: str = NO_ERA5_LAND,
) -> Path:
    import xarray as xr

    plan = load_plan(pp.cmip6)["models"][model]
    b0, b1 = s.baseline
    kb, nb, lat, lon = counts_for_window(pp.cmip6, model, s.baseline_experiment, b0, b1, s)
    if nb.max() < (b1 - b0 + 1):
        log.warning("%s: baseline has only %d of %d years", model, nb.max(), b1 - b0 + 1)
    land, land_pct, uses_era5 = model_land(pp, model, lat, lon, nb[0], s, era5_land)
    windows = ["baseline"]
    k_all, n_all, deltas, wattrs = [kb], [nb], [], {}
    for g in s.gwls:
        w = plan["windows"].get(str(g))
        if w is None:
            log.warning("%s: no window for +%s °C", model, g)
            k_all.append(np.full_like(kb, np.nan))
            n_all.append(np.zeros_like(nb))
            deltas.append(np.full_like(kb, np.nan))
        else:
            k, n, *_ = counts_for_window(pp.cmip6, model, w["experiment"], w["start"], w["end"], s)
            k_all.append(k)
            n_all.append(n)
            deltas.append(masked_delta(kb, nb, k, n, land))
            wattrs[f"window_{g}"] = f"{w['experiment']} {w['start']}-{w['end']}"
        windows.append(str(g))
    ds = xr.Dataset(
        {
            "k": (("window", "definition", "lat", "lon"), np.stack(k_all)),
            "n": (("window", "definition", "lat", "lon"), np.stack(n_all)),
            "delta": (("gwl", "definition", "lat", "lon"), np.stack(deltas)),
            "land": (("lat", "lon"), land),
        },
        coords={
            "window": windows,
            "gwl": list(s.gwls),
            "definition": list(s.definitions),
            "lat": lat,
            "lon": lon,
        },
        attrs={
            "model": model,
            "member": plan["member"],
            "baseline": f"{s.baseline_experiment} {b0}-{b1}",
            "estimator": ESTIMATOR,
            # where the land mask came from: SFTLF, or the ERA5-Land source (cli._reuse_file)
            "era5_land_source": era5_land_source if uses_era5 else SFTLF,
            **wattrs,
            **{f"setting_{k}": str(v) for k, v in s.as_attrs().items()},
        },
    )
    if land_pct is not None:
        ds["land_pct"] = (("lat", "lon"), land_pct.astype("float32"))
    pp.models.mkdir(parents=True, exist_ok=True)
    out = pp.models / f"{model}.nc"
    tmp = out.with_suffix(".tmp.nc")
    enc = {v: {"zlib": True, "complevel": 4} for v in ("k", "n", "delta")}
    ds.to_netcdf(tmp, encoding=enc)
    tmp.replace(out)
    log.info("%s: wrote %s", model, out)
    return out


def models_ready(pp: ProjPaths, first_year: int = 1996) -> list[str]:
    """Models whose snow files from ``first_year`` on are all downloaded (plan vs manifest)."""
    import json

    plan = load_plan(pp.cmip6)
    done = set()
    mf = pp.cmip6 / "manifest.jsonl"
    if mf.exists():
        done = {
            json.loads(x)["source_file"]
            for x in mf.read_text(encoding="utf-8").splitlines()
            if x.strip()
        }
    ready = []
    for model in plan["models"]:
        need = [
            f["file"]
            for f in plan["files"]
            if f["model"] == model and f["variable"] == "snw" and f.get("end", 9999) >= first_year
        ]
        if need and all(f in done for f in need):
            ready.append(model)
    return ready
