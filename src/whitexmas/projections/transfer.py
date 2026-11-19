"""Change transfer in log-odds with Jeffreys smoothing.

A frequency of ``k`` white years out of ``n`` is turned into a smoothed probability
``q = (k + 1/2) / (n + 1)`` (the Jeffreys estimate), so 0 % and 100 % have finite log-odds.

* :func:`logodds_change` gives a model's change ``logit(q_future) - logit(q_baseline)``.
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
    """Change in smoothed log-odds from the baseline to the future window."""
    d = logit(jeffreys(k_fut, n_fut)) - logit(jeffreys(k_base, n_base))
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
