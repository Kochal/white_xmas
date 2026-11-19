"""Change transfer in log-odds with Jeffreys smoothing.

A frequency of ``k`` white years out of ``n`` is turned into a smoothed probability
``q = (k + 1/2) / (n + 1)`` (the Jeffreys estimate), so 0 % and 100 % have finite log-odds.

* :func:`logodds_change` gives a model's change ``logit(q_future) - logit(q_baseline)``, with
  both frequencies smoothed as if they came from the same number of years, the shorter of the
  two windows (``m = min(n_base, n_fut)``): ``q = (f m + 1/2) / (m + 1)`` with ``f = k / n``.
  Smoothing each window with its own ``n`` pulls the shorter window harder towards 50 %, so a
  cell with the same frequency in both windows got a spurious change (0/30 -> 0/20 gave
  +0.40, i.e. every never-white cell "gained" 0.8 % and every always-white cell lost 0.8 %).
  With a common ``m`` equal frequencies give exactly zero change, for any window lengths.
* :func:`apply_change` adds that change to the observed baseline's smoothed log-odds and maps
  the result back to a frequency with the inverse of the same smoothing,
  ``p = ((n + 1) q - 1/2) / n``, clipped to 0-100 %. With no change this returns the observed
  baseline exactly, and a 0 % or 100 % cell can still move in the direction of the change.

``k`` may be fractional (a share of pooled days times the number of years).
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit, logit


def jeffreys(k, n):
    """Smoothed probability (k + 1/2) / (n + 1)."""
    return (np.asarray(k, dtype="float64") + 0.5) / (np.asarray(n, dtype="float64") + 1.0)


def logodds_change(k_base, n_base, k_fut, n_fut):
    """Change in smoothed log-odds from the baseline to the future window.

    Both frequencies ``k / n`` are smoothed with the same effective sample size, the shorter
    window's ``m = min(n_base, n_fut)``, so equal frequencies give exactly 0 whatever the window
    lengths. For equal windows this is plain Jeffreys smoothing of each count. NaN where either
    window has no valid year.
    """
    nb = np.asarray(n_base, dtype="float64")
    nf = np.asarray(n_fut, dtype="float64")
    m = np.minimum(nb, nf)
    with np.errstate(invalid="ignore", divide="ignore"):
        fb = np.where(nb > 0, np.asarray(k_base, dtype="float64") / nb, np.nan)
        ff = np.where(nf > 0, np.asarray(k_fut, dtype="float64") / nf, np.nan)
        d = logit(jeffreys(ff * m, m)) - logit(jeffreys(fb * m, m))
    return d if np.ndim(d) else float(d)


def apply_change(p_obs_pct, n_obs, delta):
    """Projected probability in % from an observed baseline in % and a log-odds change.

    ``n_obs`` is the number of years behind the observed baseline (scalar or array).
    """
    p = np.asarray(p_obs_pct, dtype="float64") / 100.0
    n = np.asarray(n_obs, dtype="float64")
    q = expit(logit(jeffreys(p * n, n)) + np.asarray(delta, dtype="float64"))
    out = ((n + 1.0) * q - 0.5) / n
    return 100.0 * np.clip(out, 0.0, 1.0)
