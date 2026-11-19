"""White-Christmas rules as pure functions of the snow cube.

Input: int16 snow depth in whole cm with shape ``(year, day, ...)``, days = Dec 24, 25, 26,
``-1`` = nodata. Output: float32 ``(year, ...)`` with 1.0 = white, 0.0 = green, NaN = unknown.
A rule that needs a day with nodata gives NaN, never 0 (the legacy bug turned NaN into 0).
"""

from __future__ import annotations

import numpy as np

NODATA = -1
DEFINITIONS = ("christmas_day", "all_three_days", "any_day")


def white(cube_cm: np.ndarray, definition: str, threshold_cm: float = 1) -> np.ndarray:
    cube_cm = np.asarray(cube_cm)
    if definition == "christmas_day":
        days = cube_cm[:, 1:2]
    elif definition in ("all_three_days", "any_day"):
        days = cube_cm[:, 0:3]
    else:
        raise ValueError(f"unknown definition {definition!r}; expected one of {DEFINITIONS}")
    missing = (days == NODATA).any(axis=1)
    snowy = days >= threshold_cm
    hit = snowy.all(axis=1) if definition == "all_three_days" else snowy.any(axis=1)
    out = hit.astype("float32")
    out[missing] = np.nan
    return out
