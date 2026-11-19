"""Regional statistics from cell values and sparse region weights. Pure functions, no I/O.

``W[region, cell]`` holds a region's weight per cell (area: cell fraction × cos lat; population:
people in the places whose value cell it is). Cells are flat (``j * nx + i``). A cell counts
only where its value is finite and it is not a glacier cell; regions with no such cell give NaN
here, and the export turns NaN into ``null`` with a flag, never a silent number.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.special import ndtr


def weighted_mean(w: sparse.csr_matrix, values: np.ndarray, usable: np.ndarray) -> np.ndarray:
    """Per-region weighted mean of ``values`` (flat) over cells where ``usable`` is True."""
    ok = usable & np.isfinite(values)
    den = w @ ok.astype("float64")
    num = w @ np.where(ok, values, 0.0).astype("float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def weighted_means_2d(w: sparse.csr_matrix, values: np.ndarray, usable: np.ndarray):
    """``values[k, cell]`` → (num[region, k], den[region, k]) for accumulating over bands."""
    ok = usable & np.isfinite(values)
    num = w @ np.where(ok, values, 0.0).astype("float64").T
    den = w @ ok.astype("float64").T
    return np.asarray(num), np.asarray(den)


def weighted_percentiles(
    w: sparse.csr_matrix, values: np.ndarray, usable: np.ndarray, qs=(5, 95)
) -> np.ndarray:
    """Weighted percentiles per region: the smallest cell value whose cumulative weight share
    reaches q (inverse of the weighted distribution, no interpolation). Shape (len(qs), R)."""
    w = sparse.csr_matrix(w)
    nreg = w.shape[0]
    rows = np.repeat(np.arange(nreg), np.diff(w.indptr))
    cols, wt = w.indices, w.data
    v = values[cols]
    ok = usable[cols] & np.isfinite(v) & (wt > 0)
    rows, v, wt = rows[ok], v[ok], wt[ok]
    out = np.full((len(qs), nreg), np.nan)
    if not len(rows):
        return out
    order = np.lexsort((v, rows))
    rows, v, wt = rows[order], v[order], wt[order]
    cum = np.cumsum(wt)
    starts = np.searchsorted(rows, np.arange(nreg), side="left")
    ends = np.searchsorted(rows, np.arange(nreg), side="right")
    has = ends > starts
    base = np.where(starts > 0, cum[np.maximum(starts - 1, 0)], 0.0)
    total = np.where(has, cum[np.maximum(ends - 1, 0)] - base, 0.0)
    for k, q in enumerate(qs):
        target = base + q / 100.0 * total
        pos = np.searchsorted(cum, target - 1e-12 * np.maximum(total, 1), side="left")
        pos = np.clip(np.minimum(pos, ends - 1), starts, None)
        out[k, has] = v[pos[has]]
    return out


def weighted_extremes(
    frac: sparse.csr_matrix, values: np.ndarray, usable: np.ndarray, min_frac: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    """Min and max of ``values`` over a region's usable cells that lie at least ``min_frac``
    inside it (all usable cells if none does), so a sliver of a neighbouring mountain does not
    set a lowland region's maximum."""
    f = sparse.csr_matrix(frac)
    nreg = f.shape[0]
    lo = np.full(nreg, np.nan)
    hi = np.full(nreg, np.nan)
    for r in range(nreg):
        a, b = f.indptr[r], f.indptr[r + 1]
        cols, fr = f.indices[a:b], f.data[a:b]
        ok = usable[cols] & np.isfinite(values[cols])
        if not ok.any():
            continue
        core = ok & (fr >= min_frac)
        sel = values[cols[core if core.any() else ok]]
        lo[r], hi[r] = float(sel.min()), float(sel.max())
    return lo, hi


def ols_slope_per_decade(series: np.ndarray, years: np.ndarray) -> np.ndarray:
    """OLS slope of ``series[region, year]`` (in %) per decade, over finite years; NaN with
    fewer than 3."""
    y = np.asarray(series, dtype="float64")
    t = np.asarray(years, dtype="float64")[None, :]
    ok = np.isfinite(y)
    n = ok.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        tb = np.where(ok, t, 0).sum(axis=1) / n
        yb = np.where(ok, y, 0).sum(axis=1) / n
        dt = np.where(ok, t - tb[:, None], 0)
        slope = (dt * np.where(ok, y - yb[:, None], 0)).sum(axis=1) / (dt**2).sum(axis=1)
    return np.where(n >= 3, slope * 10.0, np.nan)


def mann_kendall_p(series: np.ndarray, tie_decimals: int = 6) -> np.ndarray:
    """Two-sided Mann-Kendall p per row of ``series[region, year]`` (finite years only), with
    the tie correction. Values are rounded to ``tie_decimals`` first so that equal shares (all
    0 % or all 100 %) count as ties. Constant rows give 1, fewer than 3 years NaN."""
    y = np.round(np.asarray(series, dtype="float64"), tie_decimals)
    nreg, nyears = y.shape
    s = np.zeros(nreg)
    for i in range(nyears - 1):
        d = y[:, i + 1 :] - y[:, i : i + 1]
        s += np.nansum(np.sign(d), axis=1)
    n = np.isfinite(y).sum(axis=1).astype("float64")
    tie = np.zeros(nreg)
    for r in range(nreg):
        v = y[r][np.isfinite(y[r])]
        if len(v):
            _, c = np.unique(v, return_counts=True)
            c = c[c > 1].astype("float64")
            tie[r] = (c * (c - 1) * (2 * c + 5)).sum()
    var = (n * (n - 1) * (2 * n + 5) - tie) / 18.0
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(s > 0, (s - 1) / np.sqrt(var), np.where(s < 0, (s + 1) / np.sqrt(var), 0.0))
        p = 2 * (1 - ndtr(np.abs(z)))
    p = np.where(var > 0, p, 1.0)
    return np.where(n >= 3, p, np.nan)


def benjamini_hochberg(p: np.ndarray, testable: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q) over the ``testable`` entries; NaN elsewhere.

    q_(i) = min over j >= i of m p_(j) / j, capped at 1, with m the number of testable p-values
    (ranked ascending). Controls the expected share of false discoveries among the regions
    called significant at q < alpha (under independence or positive dependence, which is the
    case for neighbouring regions sharing weather).
    """
    p = np.asarray(p, dtype="float64")
    ok = np.asarray(testable, dtype=bool) & np.isfinite(p)
    q = np.full(p.shape, np.nan)
    m = int(ok.sum())
    if m == 0:
        return q
    pv = p[ok]
    order = np.argsort(pv, kind="stable")
    ranked = pv[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    q[ok] = out
    return q


def testable_series(series: np.ndarray, tie_decimals: int = 6) -> np.ndarray:
    """Rows of ``series[region, year]`` that can show a trend: at least 3 finite years and not
    constant (an always-0 % or always-100 % region has Mann-Kendall p = 1 by construction and
    cannot be a false discovery, so it does not count towards the number of tests)."""
    y = np.round(np.asarray(series, dtype="float64"), tie_decimals)
    ok = np.isfinite(y)
    hi = np.where(ok, y, -np.inf).max(axis=1)
    lo = np.where(ok, y, np.inf).min(axis=1)
    return (ok.sum(axis=1) >= 3) & (hi > lo)


def trend_q(series: np.ndarray, trend_p: np.ndarray) -> np.ndarray:
    """BH q-values of the trend tests, per threshold and definition, across the testable
    regions. ``series[t, d, region, year]``, ``trend_p[t, d, region]``."""
    q = np.full(trend_p.shape, np.nan)
    for idx in np.ndindex(trend_p.shape[:-1]):
        q[idx] = benjamini_hochberg(trend_p[idx], testable_series(series[idx]))
    return q


def ensemble_summary(
    model_means: np.ndarray, baseline: np.ndarray, zero_pp: float = 0.05, share: float = 2 / 3
) -> dict[str, np.ndarray]:
    """Across models (rows of ``model_means[model, region]``): p10, p50, p90 (linear
    interpolation, as the map's ensemble), the change of the median against ``baseline``,
    model agreement on the direction of the regional change (decrease, increase, or no change
    within ``zero_pp``; at least ``share`` of the models with a value), and the model count."""
    from ..projections.ensemble import nan_percentiles

    q = nan_percentiles(model_means, (10, 50, 90))
    d = model_means - baseline[None, :]
    valid = np.isfinite(d)
    nval = valid.sum(axis=0)
    neg = (valid & (d < -zero_pp)).sum(axis=0)
    pos = (valid & (d > zero_pp)).sum(axis=0)
    zero = nval - neg - pos
    best = np.maximum(np.maximum(neg, pos), zero)
    return {
        "p10": q[0],
        "p50": q[1],
        "p90": q[2],
        "change": q[1] - baseline,
        "agree": (nval > 0) & (best >= share * nval - 1e-9),
        "n_models": nval,
    }
