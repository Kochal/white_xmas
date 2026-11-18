"""Model validation against ERA5-Land.

1. **Bias** (plan §3b): each model's baseline white-Christmas frequency (1995-2014, its own
   grid) against ERA5-Land for the same years aggregated to that grid. Bias maps go to
   ``interim/projections/validation/bias_<model>.nc``, the summary to ``skill.csv``/``.json``.
2. **Hindcast**: does the method itself add skill? Take ERA5-Land's 1961-1990 probability, apply
   each model's own change from 1961-1990 to 1996-2025 (historical + SSP2-4.5), and score the
   result against what ERA5-Land observed in 1996-2025 with the Brier score. The reference is
   "no change" (the 1961-1990 probability). Brier skill score > 0 means the model change moved
   the probability in the right direction by a sensible amount. Per cell the Brier score over
   30 years is ``p² - 2 p f + f`` with ``f`` the observed frequency, so yearly data are not
   needed beyond ``f``.

Scores are cos(lat)-weighted over Northern Hemisphere land 25-75 °N (where Christmas snow
varies), glacier cells excluded.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import numpy as np

from ..paths import DataPaths
from .baseline import NX, NY, era5_window_frequency, load_baseline, target_grid
from .changes import counts_for_window
from .cmip6 import box_mean, load_plan
from .ensemble import project_model
from .settings import ProjPaths, ProjSettings
from .transfer import logodds_change

log = logging.getLogger(__name__)
REGION = (25.0, 75.0)


def _region_weights(lat: np.ndarray, nlon: int) -> np.ndarray:
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, nlon))
    w[(lat < REGION[0]) | (lat > REGION[1])] = 0.0
    return w


def bias_scores(model_f: np.ndarray, era_f: np.ndarray, w: np.ndarray) -> dict:
    """Scores (in percentage points) where both fields are finite and the weight is positive."""
    ok = np.isfinite(model_f) & np.isfinite(era_f) & (w > 0)
    if not ok.any():
        return {}
    m, e, ww = 100 * model_f[ok], 100 * era_f[ok], w[ok]
    d = m - e
    trans = (e > 5) & (e < 95)
    mc, ec = m - np.average(m, weights=ww), e - np.average(e, weights=ww)
    corr = np.sum(ww * mc * ec) / np.sqrt(np.sum(ww * mc**2) * np.sum(ww * ec**2))
    return {
        "cells": int(ok.sum()),
        "mean_model_pct": round(float(np.average(m, weights=ww)), 2),
        "mean_era5_pct": round(float(np.average(e, weights=ww)), 2),
        "bias_pp": round(float(np.average(d, weights=ww)), 2),
        "mae_pp": round(float(np.average(np.abs(d), weights=ww)), 2),
        "mae_transition_pp": round(float(np.average(np.abs(d[trans]), weights=ww[trans])), 2)
        if trans.any()
        else None,
        "corr": round(float(corr), 3),
    }


def brier(p_pct: np.ndarray, f: np.ndarray, w: np.ndarray) -> float:
    """Mean Brier score of probabilities ``p`` (%) against yearly outcomes with frequency ``f``."""
    p = p_pct / 100.0
    ok = np.isfinite(p) & np.isfinite(f) & (w > 0)
    bs = p[ok] ** 2 - 2 * p[ok] * f[ok] + f[ok]
    return float(np.average(bs, weights=w[ok]))


def validate(paths: DataPaths, s: ProjSettings, models: list[str] | None = None) -> dict:
    import xarray as xr

    pp = ProjPaths.from_data(paths)
    pp.validation.mkdir(parents=True, exist_ok=True)
    d = "christmas_day"
    b0, b1 = s.baseline
    era = era5_window_frequency(paths, d, b0, b1)
    era_src = f"ERA5-Land {b0}-{b1}"
    if era is None:
        bl = load_baseline(paths, d, s.obs_window)
        era = bl.p / 100.0
        era_src = f"{bl.source} {bl.window} (cube missing)"
        glacier = bl.glacier
    else:
        glacier = load_baseline(paths, d, s.obs_window).glacier
    era = np.where(glacier, np.nan, era)
    rows = []
    for f in sorted(pp.models.glob("*.nc")):
        if models and f.stem not in models:
            continue
        with xr.open_dataset(f) as ds:
            k = ds["k"].sel(window="baseline", definition=d).values
            n = ds["n"].sel(window="baseline", definition=d).values
            land = ds["land"].values
            lat, lon = ds["lat"].values, ds["lon"].values
        with np.errstate(invalid="ignore", divide="ignore"):
            mf = np.where(land & (n > 0), k / n, np.nan)
        ef, cover = box_mean(era, lat, lon)
        ef = np.where(cover >= 0.5, ef, np.nan)
        sc = bias_scores(mf, ef, _region_weights(lat, len(lon)))
        rows.append({"model": f.stem, "grid": f"{len(lat)}x{len(lon)}", **sc})
        xr.Dataset(
            {
                "model_pct": (("lat", "lon"), 100 * mf),
                "era5_pct": (("lat", "lon"), 100 * ef),
                "bias_pp": (("lat", "lon"), 100 * (mf - ef)),
            },
            coords={"lat": lat, "lon": lon},
            attrs={"reference": era_src},
        ).to_netcdf(pp.validation / f"bias_{f.stem}.nc")
        log.info("bias %s: %s", f.stem, sc)
    out = {
        "reference": era_src,
        "region": f"land {REGION[0]}-{REGION[1]} N, cos-lat weighted",
        "threshold_kg_m2": s.threshold_kg_m2,
        "pool_days": s.pool_days,
        "models": rows,
    }
    _write_table(pp.validation / "skill", rows)
    (pp.validation / "skill.json").write_text(json.dumps(out, indent=1))
    return out


def hindcast(
    paths: DataPaths,
    s: ProjSettings,
    models: list[str] | None = None,
    then: tuple[int, int] = (1961, 1990),
    now: tuple[int, int] = (1996, 2025),
) -> dict:
    """Brier skill of transferring each model's then→now change onto ERA5-Land 'then'."""
    pp = ProjPaths.from_data(paths)
    d = "christmas_day"
    f_then = era5_window_frequency(paths, d, *then)
    f_now = era5_window_frequency(paths, d, *now)
    if f_then is None or f_now is None:
        raise FileNotFoundError("hindcast needs the pipeline's snow cube (interim/snow_cube.zarr)")
    glacier = load_baseline(paths, d, s.obs_window).glacier
    tlat, _ = target_grid()
    w = _region_weights(tlat, NX)
    w[glacier | ~np.isfinite(f_then) | ~np.isfinite(f_now)] = 0.0
    cells = np.nonzero(w > 0)
    wc = w[cells]
    p_then = 100.0 * f_then
    n_then = np.full((NY, NX), then[1] - then[0] + 1, dtype="int16")
    fn = f_now[cells]
    bs_ref = brier(p_then[cells], fn, wc)
    bs_oracle = brier(100.0 * fn, fn, wc)
    plan = load_plan(pp.cmip6)["models"]
    names = [m for m in (models or sorted(plan)) if m not in s.exclude]
    rows, projs = [], []
    hs = ProjSettings(**{**s.__dict__, "definitions": (d,)})
    for m in names:
        try:
            k0, n0, lat, lon = counts_for_window(pp.cmip6, m, "historical", *then, hs)
            k1, n1, *_ = counts_for_window(pp.cmip6, m, "ssp245", *now, hs)
        except FileNotFoundError as e:
            log.warning("hindcast %s skipped: %s", m, e)
            continue
        land = np.isfinite(k0[0]) & (n0[0] > 0) & (n1[0] > 0)
        delta = np.where(land, logodds_change(k0[0], n0[0], k1[0], n1[0]), np.nan)
        _, proj = project_model(delta, lat, lon, p_then, n_then, cells)
        projs.append(proj)
        bs = brier(proj, fn, wc)
        rows.append(
            {"model": m, "brier": round(bs, 5), "bss_vs_no_change": round(1 - bs / bs_ref, 4)}
        )
        log.info("hindcast %s: BS %.5f, BSS %.4f", m, bs, 1 - bs / bs_ref)
    out = {
        "then": list(then),
        "now": list(now),
        "brier_no_change": round(bs_ref, 5),
        "brier_oracle": round(bs_oracle, 5),
        "models": rows,
    }
    if projs:
        med = np.nanmedian(np.stack(projs), axis=0)
        bs = brier(med, fn, wc)
        out["ensemble_median"] = {
            "brier": round(bs, 5),
            "bss_vs_no_change": round(1 - bs / bs_ref, 4),
        }
        out["reliability"] = reliability(med, fn, wc)
        obs_change = np.average(100 * fn - p_then[cells], weights=wc)
        out["mean_change_pp"] = {
            "observed": round(float(obs_change), 2),
            "ensemble_median": round(float(np.average(med - p_then[cells], weights=wc)), 2),
        }
    pp.validation.mkdir(parents=True, exist_ok=True)
    (pp.validation / "hindcast.json").write_text(json.dumps(out, indent=1))
    _write_table(pp.validation / "hindcast", rows)
    return out


def reliability(p_pct: np.ndarray, f: np.ndarray, w: np.ndarray, bins: int = 10) -> list[dict]:
    """Mean forecast vs mean observed frequency in probability bins (reliability diagram)."""
    edges = np.linspace(0, 100, bins + 1)
    idx = np.clip(np.digitize(p_pct, edges) - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        sel = (idx == b) & np.isfinite(p_pct)
        if w[sel].sum() <= 0:
            continue
        out.append(
            {
                "bin": f"{edges[b]:.0f}-{edges[b + 1]:.0f}",
                "forecast_pct": round(float(np.average(p_pct[sel], weights=w[sel])), 1),
                "observed_pct": round(float(100 * np.average(f[sel], weights=w[sel])), 1),
                "weight": round(float(w[sel].sum() / w.sum()), 4),
            }
        )
    return out


def _write_table(stem: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(stem.with_suffix(".csv"), "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        wr.writerows(rows)
