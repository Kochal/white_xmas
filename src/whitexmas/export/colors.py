"""Colour maps shared by the tile renderer and the manifest (so legend == map).

- probability: ColorBrewer YlGnBu (sequential, colour-blind safe, monotone lightness).
  0 % is a pale sand-yellow, not white, so "never white" land stays distinct from snow and
  from nodata (transparent).
- change, trend: ColorBrewer RdBu (diverging, colour-blind safe); red = fewer white
  Christmases, blue = more, neutral grey-white at 0.

Interpolation between stops is linear in sRGB, and values outside the domain are clamped.
"""

from __future__ import annotations

import numpy as np

YLGNBU = ["#ffffd9", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4",
          "#1d91c0", "#225ea8", "#253494", "#081d58"]  # fmt: skip
RDBU = ["#b2182b", "#d6604d", "#f4a582", "#fddbc7", "#f7f7f7",
        "#d1e5f0", "#92c5de", "#4393c3", "#2166ac"]  # fmt: skip


def _stops(lo: float, hi: float, colours: list[str]) -> list[list]:
    vals = np.linspace(lo, hi, len(colours))
    return [[round(float(v), 4), c] for v, c in zip(vals, colours, strict=True)]


COLORMAPS: dict[str, dict] = {
    "probability": {"unit": "%", "domain": [0, 100], "stops": _stops(0, 100, YLGNBU)},
    "change": {"unit": "pp", "domain": [-50, 50], "stops": _stops(-50, 50, RDBU)},
    "trend": {"unit": "pp/decade", "domain": [-15, 15], "stops": _stops(-15, 15, RDBU)},
}

GLACIER_FILL = (224, 224, 224)
GLACIER_LINE = (150, 150, 150)
HATCH_LINE = (90, 90, 90)
HATCH_SPACING = 6  # px, screen space
HATCH_WIDTH = 2


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[k : k + 2], 16) for k in (0, 2, 4))


def apply_colormap(values: np.ndarray, name: str) -> np.ndarray:
    """float array → uint8 RGBA; NaN → fully transparent."""
    cm = COLORMAPS[name]
    xs = np.array([s[0] for s in cm["stops"]], dtype="float64")
    rgb = np.array([hex_to_rgb(s[1]) for s in cm["stops"]], dtype="float64")
    v = np.clip(np.asarray(values, dtype="float64"), xs[0], xs[-1])
    out = np.zeros((*v.shape, 4), dtype="uint8")
    ok = np.isfinite(values)
    for c in range(3):
        out[..., c][ok] = np.round(np.interp(v[ok], xs, rgb[:, c])).astype("uint8")
    out[..., 3][ok] = 255
    return out
