"""Statistics for the station check: how well ERA5-Land's thresholds match station frequencies.

Notation, per station s and whole-cm ERA5-Land threshold T:

- ``obs_s``: share of usable years with observed SNWD ≥ 1 cm on 25 December (%);
- ``mod_s(T)``: share of the same years with ERA5-Land ≥ T cm (%);
- ``bias_s(T) = mod_s(T) − obs_s`` in percentage points (pp).

Group statistics are means over stations (each station counts once, whatever its record length).
Uncertainty comes from a *two-way bootstrap*: 10° × 10° blocks of stations and calendar years are
resampled together, so neither neighbouring stations nor stations sharing the same Christmas
weather count as independent evidence. Thresholds:

- ``best_whole``: the whole-cm T with the smallest |mean bias| (ties: smaller MAE), the rule that
  chose the shipped 5 cm (D-17);
- ``t_star``: the (fractional) T at which the mean bias crosses zero, by linear interpolation
  between whole-cm thresholds. ERA5-Land depths are stored in whole cm, so a fractional T* is a
  summary of where the crossing lies, not a threshold the pipeline can apply.

Each station's own bias has sampling noise: with n years, its standard error is
SE_s = sd(d_y)/√n for the yearly differences d_y = [ERA5-Land white] − [station white] ∈ {−1, 0, 1}.
``spread`` separates the real between-station spread of the bias (τ) from that noise
(method of moments: τ² = var(bias_s) − mean(SE_s²)).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np

BLOCK_DEG = 10.0
CV_BLOCK_DEG = 10.0


def block_of(r: dict, deg: float = BLOCK_DEG) -> tuple[int, int]:
    return math.floor(r["lat"] / deg), math.floor(r["lon"] / deg)


def bias(r: dict, t: int) -> float:
    return r["model_pct"][t] - r["obs_pct"]


def biases(rows: Sequence[dict], t: int) -> np.ndarray:
    return np.array([bias(r, t) for r in rows], dtype=float)


def station_se(r: dict, t: int) -> float:
    """Standard error (pp) of one station's bias at T from its yearly contingency table."""
    h, mi, fa, cn = r["table"][t]
    n = h + mi + fa + cn
    if n < 2:
        return float("nan")
    mean = (fa - mi) / n
    var = ((fa + mi) / n - mean * mean) * n / (n - 1)
    return 100 * math.sqrt(max(var, 0.0) / n)


def mcnemar_p(r: dict, t: int) -> float:
    """Exact two-sided McNemar test of 'ERA5-Land and the station are white equally often'."""
    _, mi, fa, _ = r["table"][t]
    k, n = min(mi, fa), mi + fa
    if n == 0:
        return 1.0
    from scipy.stats import binom

    return float(min(1.0, 2 * binom.cdf(k, n, 0.5)))


def best_whole(rows: Sequence[dict], thresholds: Sequence[int]) -> int:
    """Whole-cm T with the smallest |mean bias| across ``rows`` (ties: smallest MAE, then T)."""
    score = []
    for t in thresholds:
        d = biases(rows, t)
        score.append((abs(d.mean()), np.abs(d).mean(), t))
    return min(score)[2]


def t_star(mean_bias: dict[int, float]) -> float:
    """Fractional T where the mean bias crosses zero (linear between whole cm).

    Returns −inf if the bias is already ≤ 0 at the smallest T, +inf if still > 0 at the largest.
    """
    ts = sorted(mean_bias)
    if mean_bias[ts[0]] <= 0:
        return -math.inf
    for a, b in zip(ts, ts[1:], strict=False):
        ba, bb = mean_bias[a], mean_bias[b]
        if ba > 0 >= bb:
            return a + (b - a) * ba / (ba - bb)
    return math.inf


def mean_bias_by_t(rows: Sequence[dict], thresholds: Sequence[int]) -> dict[int, float]:
    return {t: float(biases(rows, t).mean()) for t in thresholds}


def _resample(rows: Sequence[dict], rng: np.random.Generator, deg: float) -> list[dict]:
    blocks: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in rows:
        blocks[block_of(r, deg)].append(r)
    keys = list(blocks)
    pick = rng.integers(0, len(keys), len(keys))
    return [r for k in pick for r in blocks[keys[k]]]


def _percentile_ci(vals: np.ndarray) -> tuple[float, float]:
    # No interpolation, so resamples without a crossing (±inf) give an open interval, not nan.
    lo, hi = np.quantile(vals, [0.025, 0.975], method="inverted_cdf")
    return float(lo), float(hi)


def block_bootstrap(
    rows: Sequence[dict],
    stat: Callable[[Sequence[dict]], float],
    n_boot: int = 1000,
    seed: int = 0,
    deg: float = BLOCK_DEG,
) -> tuple[float, float]:
    """95 % percentile interval of any ``stat``, resampling station blocks only (slow path)."""
    if len(rows) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    vals = np.array([stat(_resample(rows, rng, deg)) for _ in range(n_boot)], dtype=float)
    vals = vals[~np.isnan(vals)]
    return _percentile_ci(vals) if len(vals) else (float("nan"), float("nan"))


def period(rows: Sequence[dict]) -> tuple[int, int]:
    """First and last calendar year with a usable station-year in ``rows``."""
    ys = [y for r in rows for y in (r["yearly"]["years"][:1] + r["yearly"]["years"][-1:])]
    return min(ys), max(ys)


def year_weights(n_boot: int, seed: int, span: tuple[int, int]) -> np.ndarray:
    """(n_boot, years) multinomial counts: the calendar years of ``span`` drawn with replacement."""
    n = span[1] - span[0] + 1
    return np.random.default_rng(seed + 7919).multinomial(n, np.full(n, 1 / n), size=n_boot)


def _year_cube(
    rows: Sequence[dict], thresholds: Sequence[int], span: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    """D[s, y, t] = [ERA5-Land ≥ t] − [station white] per station-year (0 where unused), V[s, y]."""
    ny = span[1] - span[0] + 1
    d = np.zeros((len(rows), ny, len(thresholds)))
    v = np.zeros((len(rows), ny))
    tt = np.array(thresholds)
    for k, r in enumerate(rows):
        yr = r["yearly"]
        idx = np.array(yr["years"], dtype=int) - span[0]
        o = np.array(yr["obs"], dtype=float)
        m = np.array(yr["model"], dtype=float)
        d[k, idx] = (m[:, None] >= tt[None, :]) - o[:, None]
        v[k, idx] = 1
    return d, v


def boot_mean_bias(
    rows: Sequence[dict],
    thresholds: Sequence[int],
    n_boot: int = 1000,
    seed: int = 0,
    deg: float | None = BLOCK_DEG,
    years: bool = True,
    yw: np.ndarray | None = None,
    span: tuple[int, int] | None = None,
) -> np.ndarray:
    """(n_boot, len(thresholds)) mean biases (pp) of bootstrap resamples.

    Two-way by default: ``deg``° × ``deg``° blocks of stations *and* calendar years are drawn with
    replacement, so neither neighbouring stations nor stations sharing the same Christmas weather
    count as independent. ``deg=None`` keeps every station (years only); ``years=False`` keeps
    every year (blocks only, also the fallback for rows without yearly data). ``yw`` and ``span``
    pass year draws to share between calls (the regions of one resample see the same years).
    """
    rng = np.random.default_rng(seed)
    n = len(rows)
    if deg is None:
        cnt = np.ones((n_boot, n))
    else:
        keys = sorted({block_of(r, deg) for r in rows})
        kidx = np.array([keys.index(block_of(r, deg)) for r in rows])
        pick = rng.integers(0, len(keys), (n_boot, len(keys)))
        per_block = np.zeros((n_boot, len(keys)))
        np.add.at(per_block, (np.arange(n_boot)[:, None], pick), 1)
        cnt = per_block[:, kidx]
    if not years or not all("yearly" in r for r in rows):
        b = np.array([[bias(r, t) for t in thresholds] for r in rows])  # (s, t)
        return (cnt @ b) / cnt.sum(axis=1)[:, None]
    span = span or period(rows)
    d, v = _year_cube(rows, thresholds, span)
    w = yw if yw is not None else year_weights(n_boot, seed, span)
    num = np.einsum("by,syt->bst", w, d)
    den = np.einsum("by,sy->bs", w, v)
    ok = den > 0  # a station whose years were all left out of this resample drops out
    sb = np.where(ok[..., None], num / np.where(ok, den, 1)[..., None], 0.0)
    c = cnt * ok
    return 100 * np.einsum("bs,bst->bt", c, sb) / c.sum(axis=1)[:, None]


def ci_methods(rows: Sequence[dict], t: int, n_boot: int = 1000, seed: int = 0) -> dict:
    """95 % interval of the mean bias at T under different resampling schemes (for the report)."""
    schemes = {
        "5° blocks": {"deg": 5.0, "years": False},
        "10° blocks": {"deg": 10.0, "years": False},
        "20° blocks": {"deg": 20.0, "years": False},
        "years only": {"deg": None, "years": True},
        "years × 5° blocks": {"deg": 5.0, "years": True},
        "years × 10° blocks (used)": {"deg": 10.0, "years": True},
    }
    return {
        name: _percentile_ci(boot_mean_bias(rows, [t], n_boot, seed, **kw)[:, 0])
        for name, kw in schemes.items()
    }


def contingency(rows: Sequence[dict], t: int) -> dict:
    """Pooled station-year contingency at T and the usual scores."""
    h = mi = fa = cn = 0
    for r in rows:
        a, b, c, d = r["table"][t]
        h, mi, fa, cn = h + a, mi + b, fa + c, cn + d
    n = h + mi + fa + cn
    out = {"hits": h, "misses": mi, "false_alarms": fa, "correct_negatives": cn, "n": n}
    nan = float("nan")
    out["hit_rate"] = h / (h + mi) if h + mi else nan  # POD
    out["false_alarm_ratio"] = fa / (h + fa) if h + fa else nan  # FAR
    out["false_alarm_rate"] = fa / (fa + cn) if fa + cn else nan  # POFD
    out["accuracy"] = (h + cn) / n if n else nan
    exp = ((h + mi) * (h + fa) + (cn + mi) * (cn + fa)) / n if n else nan
    out["heidke"] = (h + cn - exp) / (n - exp) if n and n != exp else nan
    return out


def spread(rows: Sequence[dict], t: int) -> dict:
    """Observed station-to-station spread of the bias vs what sampling noise alone gives."""
    d = biases(rows, t)
    se = np.array([station_se(r, t) for r in rows])
    ok = np.isfinite(se)
    if ok.sum() < 3:
        return {}
    d, se = d[ok], se[ok]
    var_d = float(d.var(ddof=1))
    noise = float((se**2).mean())
    return {
        "sd_bias_pp": math.sqrt(var_d),
        "rms_se_pp": math.sqrt(noise),
        "tau_pp": math.sqrt(max(var_d - noise, 0.0)),
        "mae_pp": float(np.abs(d).mean()),
        "mae_noise_only_pp": float(np.sqrt(2 / np.pi) * se.mean()),
    }


def summarize(
    rows: Sequence[dict],
    thresholds: Sequence[int],
    focus: int = 5,
    n_boot: int = 1000,
    seed: int = 0,
    show: Sequence[int] = (1, 4, 5, 6),
) -> dict:
    """Everything the report shows for one group of calibration stations."""
    if not rows:
        return {"n": 0}
    mb = mean_bias_by_t(rows, thresholds)
    out = {
        "n": len(rows),
        "station_years": int(sum(r["years"] for r in rows)),
        "obs_pct": float(np.mean([r["obs_pct"] for r in rows])),
        "model_pct": {t: float(np.mean([r["model_pct"][t] for r in rows])) for t in show},
        "bias_pp": {t: mb[t] for t in thresholds},
        "mae_pp": {t: float(np.abs(biases(rows, t)).mean()) for t in thresholds},
        "median_bias_pp": {t: float(np.median(biases(rows, t))) for t in show},
        "agree_pct": {t: float(np.mean([r["agree_pct"][t] for r in rows])) for t in show},
        "best_whole_cm": best_whole(rows, thresholds),
        "t_star_cm": t_star(mb),
        "contingency": contingency(rows, focus),
        "spread": spread(rows, focus),
        "n_blocks": len({block_of(r) for r in rows}),
    }
    if len(rows) >= 3:
        boot = boot_mean_bias(rows, thresholds, n_boot, seed)
        out["bias_ci"] = {
            t: _percentile_ci(boot[:, k]) for k, t in enumerate(thresholds) if t in show
        }
        ts = np.array([t_star(dict(zip(thresholds, b, strict=True))) for b in boot])
        out["t_star_ci"] = _percentile_ci(ts)
        sig = [mcnemar_p(r, focus) < 0.05 for r in rows]
        out["n_significant_bias"] = int(sum(sig))
    return out


def group_by(rows: Sequence[dict], key: Callable[[dict], str]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return dict(g)


def region_balanced(
    rows: Sequence[dict],
    thresholds: Sequence[int],
    min_n: int,
    key: str = "region",
    n_boot: int = 1000,
    seed: int = 0,
) -> dict:
    """Mean over regions (each with >= min_n stations counts once) of the regional mean bias."""
    groups = {k: v for k, v in group_by(rows, lambda r: r[key]).items() if len(v) >= min_n}
    if not groups:
        return {}
    mb = {t: float(np.mean([biases(v, t).mean() for v in groups.values()])) for t in thresholds}
    best = min(thresholds, key=lambda t: (abs(mb[t]), t))
    # Stratified two-way bootstrap: blocks resampled within each region (the regions themselves
    # are kept fixed), calendar years resampled once and shared by all regions.
    yearly = all("yearly" in r for r in rows)
    span = period(rows) if yearly else None
    yw = year_weights(n_boot, seed, span) if yearly else None
    boot = np.mean(
        [
            boot_mean_bias(v, thresholds, n_boot, seed + k, yw=yw, span=span)
            for k, v in enumerate(groups.values())
        ],
        axis=0,
    )
    ts = np.array([t_star(dict(zip(thresholds, b, strict=True))) for b in boot])
    return {
        "regions": sorted(groups),
        "bias_pp": mb,
        "bias_ci": {t: _percentile_ci(boot[:, k]) for k, t in enumerate(thresholds)},
        "best_whole_cm": best,
        "t_star_cm": t_star(mb),
        "t_star_ci": _percentile_ci(ts),
    }


def leave_one_region_out(
    rows: Sequence[dict], thresholds: Sequence[int], min_n: int, focus: int = 5
) -> list[dict]:
    """For each region: the threshold chosen without it, and how it does there."""
    out = []
    for name, held in sorted(group_by(rows, lambda r: r["region"]).items()):
        if len(held) < min_n:
            continue
        rest = [r for r in rows if r["region"] != name]
        t_rest = best_whole(rest, thresholds)
        out.append({
            "region": name,
            "n": len(held),
            "t_chosen_without": t_rest,
            "bias_at_chosen_pp": float(biases(held, t_rest).mean()),
            "mae_at_chosen_pp": float(np.abs(biases(held, t_rest)).mean()),
            "bias_at_focus_pp": float(biases(held, focus).mean()),
            "own_best_whole_cm": best_whole(held, thresholds),
        })  # fmt: skip
    return out


def blocked_cv(
    rows: Sequence[dict],
    thresholds: Sequence[int],
    min_region_n: int,
    focus: int = 5,
    deg: float = CV_BLOCK_DEG,
) -> dict:
    """Leave-one-block-out cross-validation (10° × 10° blocks).

    For each held-out block, the global threshold (``best_whole`` on all other stations) and a
    per-region threshold (``best_whole`` on the other stations of the same region, the global one
    if fewer than ``min_region_n`` remain) are chosen without it, then scored on its stations.
    The fixed shipped threshold ``focus`` is scored for comparison.
    """
    blocks = group_by(rows, lambda r: str(block_of(r, deg)))
    held_bias: dict[str, list[tuple[dict, float]]] = {"global": [], "regional": [], "fixed": []}
    chosen: dict[str, list[int]] = {"global": [], "regional": []}
    for b, test in blocks.items():
        train = [r for r in rows if str(block_of(r, deg)) != b]
        if not train:
            continue
        tg = best_whole(train, thresholds)
        chosen["global"].append(tg)
        by_region = group_by(train, lambda r: r["region"])
        cache: dict[str, int] = {}
        for r in test:
            reg = r["region"]
            if reg not in cache:
                tr = by_region.get(reg, [])
                cache[reg] = best_whole(tr, thresholds) if len(tr) >= min_region_n else tg
            chosen["regional"].append(cache[reg])
            held_bias["global"].append((r, bias(r, tg)))
            held_bias["regional"].append((r, bias(r, cache[reg])))
            held_bias["fixed"].append((r, bias(r, focus)))

    def score(pairs: list[tuple[dict, float]]) -> dict:
        if not pairs:  # a single block: nothing to train on
            keys = ("mean_bias_pp", "mae_pp", "rmse_pp", "region_mean_abs_bias_pp")
            return {**dict.fromkeys(keys, float("nan")), "by_region": {}}
        d = np.array([v for _, v in pairs])
        by_reg = defaultdict(list)
        for r, v in pairs:
            by_reg[r["region"]].append(v)
        return {
            "mean_bias_pp": float(d.mean()),
            "mae_pp": float(np.abs(d).mean()),
            "rmse_pp": float(np.sqrt((d**2).mean())),
            "region_mean_abs_bias_pp": float(
                np.mean([abs(np.mean(v)) for v in by_reg.values() if len(v) >= min_region_n])
            )
            if any(len(v) >= min_region_n for v in by_reg.values())
            else float("nan"),
            "by_region": {k: float(np.mean(v)) for k, v in sorted(by_reg.items())},
        }

    return {
        "n_blocks": len(blocks),
        "block_deg": deg,
        **{k: score(v) for k, v in held_bias.items()},
        "global_threshold_counts": {
            t: chosen["global"].count(t) for t in sorted(set(chosen["global"]))
        },
    }


def elevation_effect(rows: Sequence[dict], t: int = 5, n_boot: int = 1000) -> dict:
    """Bias at T against the elevation difference cell − station (OLS per 100 m, r, bins)."""
    rs = [r for r in rows if np.isfinite(r.get("elev_diff_m", float("nan")))]
    if len(rs) < 5:
        return {}
    x = np.array([r["elev_diff_m"] for r in rs]) / 100.0
    y = biases(rs, t)

    def slope(sub: Sequence[dict]) -> float:
        xs = np.array([r["elev_diff_m"] for r in sub]) / 100.0
        ys = biases(sub, t)
        return float(np.polyfit(xs, ys, 1)[0]) if np.ptp(xs) > 0 else float("nan")

    edges = [-math.inf, -500, -200, -50, 50, 200, 500, math.inf]
    labels = ["< −500", "−500 to −200", "−200 to −50", "−50 to 50", "50 to 200", "200 to 500",
              "≥ 500"]  # fmt: skip
    bins = []
    for lo, hi, lab in zip(edges, edges[1:], labels, strict=False):
        sub = [r for r in rs if lo <= r["elev_diff_m"] < hi]
        if sub:
            d = biases(sub, t)
            bins.append({"bin": lab, "n": len(sub), "bias_pp": float(d.mean()),
                         "mae_pp": float(np.abs(d).mean())})  # fmt: skip
    return {
        "n": len(rs),
        "slope_pp_per_100m": slope(rs),
        "slope_ci": block_bootstrap(rs, slope, n_boot),
        "r": float(np.corrcoef(x, y)[0, 1]),
        "bins": bins,
    }


def within_region_slope(rows: Sequence[dict], t: int = 5, n_boot: int = 1000) -> dict:
    """Bias at T against cell − station elevation after removing each region's mean (pp/100 m).

    A fixed-effects slope: it compares stations of the same region, so a region that is both
    mountainous and biased (for another reason) does not create the slope on its own.
    """
    rs = [r for r in rows if np.isfinite(r.get("elev_diff_m", float("nan")))]
    if len(rs) < 10:
        return {}

    def slope(sub: Sequence[dict]) -> float:
        xs, ys = [], []
        for grp in group_by(sub, lambda r: r["region"]).values():
            if len(grp) < 3:
                continue
            x = np.array([r["elev_diff_m"] for r in grp]) / 100.0
            y = biases(grp, t)
            xs.append(x - x.mean())
            ys.append(y - y.mean())
        if not xs:
            return float("nan")
        x, y = np.concatenate(xs), np.concatenate(ys)
        return float((x * y).sum() / (x * x).sum()) if (x * x).sum() > 0 else float("nan")

    return {
        "n": len(rs),
        "slope_pp_per_100m": slope(rs),
        "slope_ci": block_bootstrap(rs, slope, n_boot),
    }


def bands(value: float, edges: Sequence[float], labels: Sequence[str]) -> str:
    if not np.isfinite(value):
        return "unknown"
    for e, lab in zip(edges, labels, strict=False):
        if value < e:
            return lab
    return labels[-1]


LAT_EDGES = (30, 40, 50, 60, 70, math.inf)
LAT_LABELS = ("< 30° N", "30–40° N", "40–50° N", "50–60° N", "60–70° N", "≥ 70° N")
ELEV_EDGES = (200, 500, 1000, 1500, 2500, math.inf)
ELEV_LABELS = ("< 200 m", "200–500 m", "500–1000 m", "1000–1500 m", "1500–2500 m", "≥ 2500 m")
YEARS_EDGES = (30, 50, math.inf)
YEARS_LABELS = ("15–29 years", "30–49 years", "≥ 50 years")
OBS_EDGES = (25, 50, 75, math.inf)
OBS_LABELS = ("5–25 % white", "25–50 % white", "50–75 % white", "75–95 % white")

DIMENSIONS: dict[str, Callable[[dict], str]] = {
    "region": lambda r: r["region"],
    "latitude": lambda r: bands(r["lat"], LAT_EDGES, LAT_LABELS),
    "elevation": lambda r: bands(r["elev_m"], ELEV_EDGES, ELEV_LABELS),
    "climate": lambda r: r["climate"],
    "record": lambda r: bands(r["years"], YEARS_EDGES, YEARS_LABELS),
    "snowiness": lambda r: bands(r["obs_pct"], OBS_EDGES, OBS_LABELS),
    "units": lambda r: "US (whole inches)" if r["us_inches"] else "metric (whole cm or mm)",
}
