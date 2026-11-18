"""Bilinear regridding between regular latitude-longitude grids.

Model grids (``gn``/``gr``, regular or Gaussian) and the ERA5-Land 0.1° grid are both products
of a 1-D latitude and a 1-D longitude axis, so bilinear interpolation separates into two sparse
1-D interpolation matrices: ``out = W_lat @ field @ W_lon.T``. That maps a ~100 km model field
onto the 3600 x 1801 target in well under a second.

Longitude is periodic by default. Targets poleward of the outermost source latitude take the
edge row. NaNs (model ocean cells) should be filled first with :func:`fill_nearest`, so coastal
ERA5-Land cells get the nearest model land value instead of NaN.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage, sparse


def _weights_1d(src: np.ndarray, dst: np.ndarray) -> sparse.csr_matrix:
    """Linear interpolation matrix from increasing ``src`` to ``dst`` (clamped at the ends)."""
    n = len(src)
    if n == 1:
        return sparse.csr_matrix(np.ones((len(dst), 1)))
    x = np.clip(dst, src[0], src[-1])
    i = np.clip(np.searchsorted(src, x, side="right") - 1, 0, n - 2)
    w = (x - src[i]) / (src[i + 1] - src[i])
    rows = np.repeat(np.arange(len(dst)), 2)
    cols = np.stack([i, i + 1], axis=1).ravel()
    vals = np.stack([1 - w, w], axis=1).ravel()
    return sparse.csr_matrix((vals, (rows, cols)), shape=(len(dst), n))


def _lon_weights(src_lon: np.ndarray, dst_lon: np.ndarray, periodic: bool) -> sparse.csr_matrix:
    src = np.asarray(src_lon, dtype="float64")
    dst = np.asarray(dst_lon, dtype="float64")
    if not periodic:
        order = np.argsort(src)
        w = _weights_1d(src[order], dst)
        return w[:, np.argsort(order)]
    src = np.mod(src, 360.0)
    order = np.argsort(src)
    s = src[order]
    # pad one point on each side so every target has two neighbours
    ext = np.concatenate([[s[-1] - 360.0], s, [s[0] + 360.0]])
    idx = np.concatenate([[order[-1]], order, [order[0]]])
    d = np.mod(dst - ext[0], 360.0) + ext[0]
    w = _weights_1d(ext, d).tocoo()
    return sparse.csr_matrix((w.data, (w.row, idx[w.col])), shape=(len(dst), len(src)))


def bilinear(
    field: np.ndarray,
    src_lat: np.ndarray,
    src_lon: np.ndarray,
    dst_lat: np.ndarray,
    dst_lon: np.ndarray,
    periodic: bool = True,
) -> np.ndarray:
    """Interpolate ``field[lat, lon]`` onto the ``dst_lat`` x ``dst_lon`` grid.

    NaN in a source cell spreads to every target that uses it; fill first if that is unwanted.
    """
    lat = np.asarray(src_lat, dtype="float64")
    order = np.argsort(lat)
    w_lat = _weights_1d(lat[order], np.asarray(dst_lat, dtype="float64"))
    w_lon = _lon_weights(src_lon, dst_lon, periodic)
    f = np.asarray(field, dtype="float64")[order]
    nan = np.isnan(f)
    out = w_lat @ (w_lon @ np.where(nan, 0.0, f).T).T
    if nan.any():
        touched = w_lat @ (w_lon @ nan.astype("float64").T).T
        out[touched > 0] = np.nan
    return out


def fill_nearest(field: np.ndarray) -> np.ndarray:
    """Replace NaN cells with the value of the nearest valid cell (in index space)."""
    f = np.asarray(field, dtype="float64")
    nan = np.isnan(f)
    if not nan.any() or nan.all():
        return f.copy()
    idx = ndimage.distance_transform_edt(nan, return_distances=False, return_indices=True)
    return f[tuple(idx)]
