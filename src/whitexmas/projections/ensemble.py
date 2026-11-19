"""Regrid every model's log-odds change to the 0.1° grid, apply it to the ERA5-Land baseline,
and summarise across models.

Output ``interim/projections/projections.zarr`` (dims ``definition, gwl, lat, lon``):

- ``p10``, ``p50``, ``p90``: 10th, 50th, 90th percentile of the projected probability (%)
- ``change``: ``p50`` minus the baseline (percentage points)
- ``agree``: at least two thirds of the models agree on the direction of the change of their
  projected probability (decrease, increase, or no change: less than ``NO_CHANGE_PP``)
- ``n_models``: models with a value in the cell
- ``baseline[definition, lat, lon]``, ``glacier[lat, lon]``

Only land cells of the baseline get values; everything else is NaN.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from ..paths import DataPaths
from .baseline import NX, NY, load_baseline, target_grid
from .changes import ESTIMATOR, GOOD_LAND_SOURCES
from .regrid import bilinear, fill_nearest
from .settings import ProjPaths, ProjSettings
from .transfer import apply_change

log = logging.getLogger(__name__)
NO_CHANGE_PP = 0.5
"""A model "agrees on no change" in a cell when its projected probability differs from today's
ERA5-Land probability by less than this many percentage points (decision S4 (b), 2026-11-19).

The vote is on the model's projected probability, not on its log-odds change: a change of
less than half a percentage point, or one that cannot show (a decline from 0 %, a rise from
100 %), is "no change". With the earlier rule
(|delta| < 1e-6) the bilinear regrid mixed exact zeros with tiny non-zero values, so places
where every model projects today's 0 % were hatched as "models disagree". The same threshold
applies to every definition, warming level, layer and point tile."""


def nan_percentiles(x: np.ndarray, qs) -> np.ndarray:
    """``np.nanpercentile(x, qs, axis=0)`` (linear interpolation), vectorised.

    numpy falls back to a Python loop over columns when NaNs are present, which takes minutes
    for millions of cells; sorting once and indexing is a few seconds.
    """
    xs = np.sort(x, axis=0)  # NaN sorts last
    n = np.isfinite(xs).sum(axis=0)
    out = np.full((len(qs), x.shape[1]), np.nan, dtype="float64")
    ok = n > 0
    for i, q in enumerate(qs):
        pos = q / 100.0 * (n[ok] - 1)
        lo = np.floor(pos).astype(int)
        hi = np.minimum(lo + 1, n[ok] - 1)
        cols = np.nonzero(ok)[0]
        a, b = xs[lo, cols], xs[hi, cols]
        out[i, ok] = a + (b - a) * (pos - lo)
    return out


def agreement(
    change_pp: np.ndarray, share: float = 2 / 3, no_change_pp: float = NO_CHANGE_PP
) -> np.ndarray:
    """``change_pp[model, cell]``: each model's projected probability minus today's, in pp.
    True where at least ``share`` of the models with a value agree on the direction: decrease
    (≤ −``no_change_pp``), increase (≥ ``no_change_pp``) or no change (in between)."""
    valid = np.isfinite(change_pp)
    nval = valid.sum(axis=0)
    neg = (valid & (change_pp <= -no_change_pp)).sum(axis=0)
    pos = (valid & (change_pp >= no_change_pp)).sum(axis=0)
    zero = nval - neg - pos
    best = np.maximum(np.maximum(neg, pos), zero)
    return (nval > 0) & (best >= share * nval - 1e-9)


def project_model(
    delta: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    p_obs: np.ndarray,
    n_obs: np.ndarray,
    cells: tuple[np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """One model: regridded delta and projected probability at the given target cells."""
    tlat, tlon = target_grid()
    filled = fill_nearest(delta)
    reg = bilinear(filled, lat, lon, tlat, tlon)[cells]
    return reg.astype("float32"), apply_change(p_obs[cells], n_obs[cells], reg).astype("float32")


def build_ensemble(
    paths: DataPaths,
    s: ProjSettings,
    models: list[str] | None = None,
    definitions: list[str] | None = None,
) -> Path:
    import xarray as xr

    pp = ProjPaths.from_data(paths)
    files = sorted(pp.models.glob("*.nc"))
    if models:
        files = [f for f in files if f.stem in models]
    from .validation import dropped_models, selection_mismatch

    # manual exclusions add to the automatic selection, never replace it
    exclude = set(s.exclude) | set(dropped_models(pp.validation))
    for diff in selection_mismatch(pp.validation, s):
        log.warning("model selection was made with other settings (%s); re-run validate", diff)
    if exclude:
        log.info("excluding models: %s", ", ".join(sorted(exclude)))
    files = [f for f in files if f.stem not in exclude]
    if not files:
        raise FileNotFoundError(f"no per-model results in {pp.models}")
    stale, land_sources = [], {}
    for f in files:
        with xr.open_dataset(f) as ds:
            if ds.attrs.get("estimator") != ESTIMATOR:
                stale.append(f.stem)
            land_sources[f.stem] = ds.attrs.get("era5_land_source")
    if stale:
        # older files smoothed each window with its own length: a spurious change of +-0.4 in
        # every never- or always-white cell (docs/projections.md, Method step 4)
        raise ValueError(
            f"per-model changes in {pp.models} were not made with the {ESTIMATOR!r} estimator "
            f"({', '.join(stale)}); re-run `whitexmas projections changes`"
        )
    names = [f.stem for f in files]
    defs = list(definitions or s.definitions)
    gwls = list(s.gwls)
    shape = (len(defs), len(gwls), NY, NX)
    out = {k: np.full(shape, np.nan, dtype="float32") for k in ("p10", "p50", "p90", "change")}
    agree = np.zeros(shape, dtype=bool)
    nmod = np.zeros(shape, dtype="int8")
    base = np.full((len(defs), NY, NX), np.nan, dtype="float32")
    glacier = np.zeros((NY, NX), dtype=bool)
    sources = set()
    thresholds = set()
    for di, d in enumerate(defs):
        b = load_baseline(paths, d, s.obs_window)
        if di == 0 and not b.placeholder:
            bad = {m: v for m, v in land_sources.items() if v not in GOOD_LAND_SOURCES}
            if bad:
                # a model without sftlf whose land mask came from the placeholder (or from no
                # mask at all) would mix ocean cells into a real ensemble
                raise ValueError(
                    "per-model land masks not from sftlf or the ERA5-Land indicators: "
                    + ", ".join(f"{m} ({v})" for m, v in sorted(bad.items()))
                    + "; re-run `whitexmas projections changes`"
                )
        sources.add(b.source)
        thresholds.add((b.threshold_id, b.threshold_cm))
        glacier |= b.glacier
        cells = np.nonzero(np.isfinite(b.p) & (b.n > 0))
        base[di] = b.p
        for gi, g in enumerate(gwls):
            proj = np.full((len(files), len(cells[0])), np.nan, dtype="float32")
            for mi, f in enumerate(files):
                with xr.open_dataset(f) as ds:
                    if d not in ds["definition"].values:
                        continue
                    delta = ds["delta"].sel(gwl=g, definition=d).values
                    lat, lon = ds["lat"].values, ds["lon"].values
                if not np.isfinite(delta).any():
                    continue
                _, proj[mi] = project_model(delta, lat, lon, b.p, b.n, cells)
            q = nan_percentiles(proj, (10, 50, 90))
            for k, v in zip(("p10", "p50", "p90"), q, strict=True):
                out[k][di, gi][cells] = v
            out["change"][di, gi][cells] = q[1] - b.p[cells]
            agree[di, gi][cells] = agreement(proj - b.p[cells][None, :])
            nmod[di, gi][cells] = np.isfinite(proj).sum(axis=0)
            log.info("ensemble %s +%s °C: %d models, %d cells", d, g, len(files), len(cells[0]))
    tlat, tlon = target_grid()
    ds = xr.Dataset(
        {
            **{k: (("definition", "gwl", "lat", "lon"), v) for k, v in out.items()},
            "agree": (("definition", "gwl", "lat", "lon"), agree),
            "n_models": (("definition", "gwl", "lat", "lon"), nmod),
            "baseline": (("definition", "lat", "lon"), base),
            "glacier": (("lat", "lon"), glacier),
        },
        coords={"definition": defs, "gwl": gwls, "lat": tlat, "lon": tlon},
        attrs={
            "models": json.dumps(names),
            "baseline_source": ",".join(sorted(sources)),
            # the observed threshold the projections apply to (contract v1.5: default only)
            "baseline_threshold": json.dumps(sorted(thresholds, key=str)[0])
            if thresholds
            else "null",
            "placeholder": any(src != "indicators" for src in sources),
            # the estimator is part of the settings so consumers that fingerprint them (admin1)
            # rebuild after an estimator change
            "settings": json.dumps({**s.as_attrs(), "estimator": ESTIMATOR}),
        },
    )
    for k in ("p10", "p50", "p90", "change", "baseline"):
        ds[k].attrs["units"] = "pp" if k == "change" else "%"
    target = pp.ensemble
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.zarr")
    enc = {v: {"chunks": (1, 1, 601, 600)} for v in (*out, "agree", "n_models")}
    ds.to_zarr(tmp, mode="w", encoding=enc, consolidated=True)
    import shutil

    if target.exists():
        shutil.rmtree(target)
    tmp.rename(target)
    log.info("wrote %s (%d models: %s)", target, len(names), ", ".join(names))
    return target


class _quiet:
    def __enter__(self):
        import warnings

        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", category=RuntimeWarning)

    def __exit__(self, *exc):
        return self._w.__exit__(*exc)
