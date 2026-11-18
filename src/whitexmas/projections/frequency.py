"""White-Christmas frequencies in a model's own climate, from daily snow water equivalent.

The downloaded model subsets hold 11 Dec - 8 Jan of every year. :func:`season_cube` arranges
them as ``cube[season_year, offset, cell]``, where ``offset`` is days from 25 December
(-14 ... +14) in the model's own calendar, so a 360-day calendar (no 31 December) is handled.

:func:`white_fraction` applies a white-Christmas rule centred on each day within
``pool_days`` of Christmas and averages over those centre days. With ``pool_days = 0`` it is
the plain rule (1 = white, 0 = green). With pooling it is the share of nearby days on which the
rule holds: a less noisy estimate of the same frequency that keeps the model's seasonal timing.
"""

from __future__ import annotations

import numpy as np

OFFSETS = np.arange(-14, 15)
_C = 14  # index of offset 0


def season_cube(values: np.ndarray, times) -> tuple[np.ndarray, np.ndarray]:
    """``values[time, ...]`` + cftime ``times`` → ``(years, cube[year, offset, ...])``.

    Days outside 11 Dec - 8 Jan are ignored. Missing days are NaN.
    """
    import cftime

    values = np.asarray(values)
    syear = np.array([t.year if t.month == 12 else t.year - 1 for t in times])
    xmas = [cftime.datetime(y, 12, 25, calendar=times[0].calendar) for y in syear]
    off = np.array(
        [int(np.floor((t - x).total_seconds() / 86400.0)) for t, x in zip(times, xmas, strict=True)]
    )
    keep = (off >= OFFSETS[0]) & (off <= OFFSETS[-1])
    years = np.unique(syear[keep])
    cube = np.full((len(years), len(OFFSETS), *values.shape[1:]), np.nan, dtype="float32")
    yi = np.searchsorted(years, syear[keep])
    cube[yi, off[keep] - OFFSETS[0]] = values[keep]
    return years, cube


def white_fraction(
    cube: np.ndarray, definition: str, threshold: float, pool_days: int = 0
) -> np.ndarray:
    """Per year, the share of centre days within ``pool_days`` of Christmas on which the rule
    holds. NaN where no centre day can be evaluated."""
    if not 0 <= pool_days <= 13:
        raise ValueError("pool_days must be within 0..13")
    snowy = np.where(np.isnan(cube), np.nan, (cube >= threshold).astype("float32"))
    hits = []
    for c in range(_C - pool_days, _C + pool_days + 1):
        if definition == "christmas_day":
            h = snowy[:, c]
        elif definition in ("all_three_days", "any_day"):
            three = snowy[:, c - 1 : c + 2]
            missing = np.isnan(three).any(axis=1)
            h = (
                (three == 1).all(axis=1)
                if definition == "all_three_days"
                else (three == 1).any(axis=1)
            )
            h = np.where(missing, np.nan, h.astype("float32"))
        else:
            raise ValueError(f"unknown definition {definition!r}")
        hits.append(h)
    with np.errstate(invalid="ignore"), _quiet():
        return np.nanmean(np.stack(hits), axis=0)


def window_counts(frac: np.ndarray, years: np.ndarray, start: int, end: int):
    """White-year count ``k`` (fractional when pooled) and valid years ``n`` in start..end."""
    sel = (years >= start) & (years <= end)
    f = frac[sel]
    n = np.isfinite(f).sum(axis=0)
    k = np.nansum(f, axis=0)
    return k, n


class _quiet:
    """Silence numpy's 'Mean of empty slice' warning (all-NaN cells are expected: ocean)."""

    def __enter__(self):
        import warnings

        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", category=RuntimeWarning)

    def __exit__(self, *exc):
        return self._w.__exit__(*exc)
