"""Which grid cells belong to a region, and how much: cell-fraction and population weights.

``fractions(regions, ...)`` returns a sparse matrix ``F[region, cell]`` with the share of each
0.1° cell that lies inside the region polygon (0-1; cells are ``j * nx + i``, row-major from the
north-west cell, as in the contract). A cell on a border is shared between the regions by its
fractions, so no cell is counted twice and no region loses its edge cells.

- Regions whose bounding box spans at most ``exact_max_cells`` cells (small states, islands,
  city states): exact polygon-cell intersection areas (in degrees², which is exact within a
  cell up to the cos-latitude change across 0.1°).
- Larger regions: the polygon is rasterised on a grid ``k`` times finer (k = 10, or 4 for
  continent-sized bounding boxes) and the sub-cells are counted, so a fraction is accurate to
  1/k² of a cell. Only cells on the region's edge are affected by that rounding.

Area weights are ``F * cos(lat)``: a cell's area shrinks with the cosine of its latitude.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy import sparse

log = logging.getLogger(__name__)

RES = 0.1
NX, NY = 3600, 1801
X0, Y0 = -180.0 - RES / 2, 90.0 + RES / 2  # outer corner of cell (0, 0)
EARTH_KM = 6371.0088
CELL_KM2_EQ = (np.radians(RES) * EARTH_KM) ** 2  # a 0.1° cell at the equator


def cell_area_km2(lat: np.ndarray) -> np.ndarray:
    return CELL_KM2_EQ * np.cos(np.radians(lat))


def _split_wide(geom):
    """Pieces of a geometry; one spanning more than 180° of longitude (split at the
    antimeridian, e.g. Chukotka or Fiji) is cut into its western and eastern halves."""
    import shapely

    x0, _, x1, _ = geom.bounds
    if x1 - x0 <= 180:
        return [geom]
    out = []
    for box in (shapely.box(-180.5, -91, 0, 91), shapely.box(0, -91, 180.5, 91)):
        part = shapely.intersection(geom, box)
        if not part.is_empty:
            out.append(part)
    return out


def _window(geom, ny: int, nx: int):
    x0, y0, x1, y1 = geom.bounds
    i0 = int(np.floor((x0 - X0) / RES))
    i1 = int(np.ceil((x1 - X0) / RES))
    j0 = max(0, int(np.floor((Y0 - y1) / RES)))
    j1 = min(ny, int(np.ceil((Y0 - y0) / RES)))
    return j0, j1, i0, max(i1, i0 + 1)


def _exact(geom, j0, j1, i0, i1):
    import shapely

    jj, ii = np.meshgrid(np.arange(j0, j1), np.arange(i0, i1), indexing="ij")
    jj, ii = jj.ravel(), ii.ravel()
    xs = X0 + ii * RES
    ys = Y0 - jj * RES
    boxes = shapely.box(xs, ys - RES, xs + RES, ys)
    shapely.prepare(geom)
    hit = shapely.intersects(geom, boxes)
    frac = np.zeros(len(boxes))
    if hit.any():
        frac[hit] = shapely.area(shapely.intersection(geom, boxes[hit])) / (RES * RES)
    return jj, ii, frac


def _supersampled(geom, j0, j1, i0, i1, k):
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    h, w = j1 - j0, i1 - i0
    t = from_origin(X0 + i0 * RES, Y0 - j0 * RES, RES / k, RES / k)
    fine = rasterize([(geom, 1)], out_shape=(h * k, w * k), transform=t, fill=0, dtype="uint8")
    frac = fine.reshape(h, k, w, k).sum(axis=(1, 3), dtype="int32") / (k * k)
    jj, ii = np.nonzero(frac)
    return jj + j0, ii + i0, frac[jj, ii]


def region_fractions(geom, ny: int = NY, nx: int = NX, exact_max_cells: int = 400,
                     k: int = 10, k_big: int = 4, big_cells: int = 1_000_000):  # fmt: skip
    """(flat cell index, fraction) of one region; columns wrap across the antimeridian."""
    cells: dict[int, float] = {}
    for piece in _split_wide(geom):
        j0, j1, i0, i1 = _window(piece, ny, nx)
        if j1 <= j0:
            continue
        n = (j1 - j0) * (i1 - i0)
        if n <= exact_max_cells:
            jj, ii, fr = _exact(piece, j0, j1, i0, i1)
        else:
            jj, ii, fr = _supersampled(piece, j0, j1, i0, i1, k if n <= big_cells else k_big)
        keep = fr > 0
        flat = jj[keep] * nx + np.mod(ii[keep], nx)
        for c, f in zip(flat.tolist(), fr[keep].tolist(), strict=True):
            cells[c] = cells.get(c, 0.0) + f
    if not cells:
        return np.zeros(0, "int64"), np.zeros(0, "float64")
    idx = np.fromiter(cells.keys(), "int64", len(cells))
    fr = np.minimum(np.fromiter(cells.values(), "float64", len(cells)), 1.0)
    return idx, fr


def fractions(regions: list[dict], ny: int = NY, nx: int = NX, **kw) -> sparse.csr_matrix:
    rows, cols, vals = [], [], []
    for r, reg in enumerate(regions):
        idx, fr = region_fractions(reg["geom"], ny, nx, **kw)
        rows.append(np.full(len(idx), r, "int32"))
        cols.append(idx)
        vals.append(fr)
        if (r + 1) % 500 == 0:
            log.info("admin1 weights: %d of %d regions", r + 1, len(regions))
    f = sparse.csr_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(len(regions), ny * nx),
        dtype="float64",
    )
    f.sum_duplicates()
    return f


def area_weights(frac: sparse.csr_matrix, lat: np.ndarray, nx: int = NX) -> sparse.csr_matrix:
    """``F * cos(lat)`` per cell (relative area of the part of the cell inside the region)."""
    coslat = np.repeat(np.cos(np.radians(np.asarray(lat, dtype="float64"))), nx)
    return sparse.csr_matrix(frac.multiply(coslat[None, :]))


def nearest_fallback(
    frac: sparse.csr_matrix, regions: list[dict], valid: np.ndarray, radius: int = 2
) -> tuple[sparse.csr_matrix, dict[int, tuple[int, int]]]:
    """Regions with no valid cell inside: the nearest valid cell within ``radius`` cells of
    the region's representative point (or of any cell it touches) gets weight 1.

    Returns the extra weights (same shape as ``frac``) and ``{region: (j, i)}``.
    """
    import shapely

    from ..export.places import cell_index, nearest_valid

    ny, nx = valid.shape
    vflat = valid.reshape(-1).astype("float64")
    has = frac @ vflat > 0
    rows, cols, picked = [], [], {}
    for r in np.nonzero(~has)[0]:
        g = regions[r]["geom"]
        p = shapely.point_on_surface(g)
        candidates = [cell_index(p.y, p.x)]
        lo, hi = frac.indptr[r], frac.indptr[r + 1]
        candidates += [(int(c // nx), int(c % nx)) for c in frac.indices[lo:hi]]
        for j, i in candidates:
            cell = nearest_valid(valid, min(j, ny - 1), i, radius)
            if cell is not None:
                rows.append(r)
                cols.append(cell[0] * nx + cell[1])
                picked[int(r)] = cell
                break
    extra = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=frac.shape, dtype="float64")
    return extra, picked


def population_weights(
    regions: list[dict],
    places: list[dict],
    valid: np.ndarray,
    radius: int = 2,
    max_deg: float = 0.1,
) -> tuple[sparse.csr_matrix, np.ndarray, np.ndarray]:
    """``P[region, cell]`` = population of the GeoNames places in the region whose value cell
    (the cell itself, or the nearest valid cell within ``radius``, as in places.json) is that
    cell. A place is in the region whose polygon contains it, else the nearest polygon within
    ``max_deg`` degrees (coastal towns just outside a generalised coastline).

    Returns ``P``, the number of places per region and their total population.
    """
    import shapely

    from ..export.places import cell_index, nearest_valid

    ny, nx = valid.shape
    geoms = np.array([r["geom"] for r in regions], dtype=object)
    tree = shapely.STRtree(geoms)
    pts = shapely.points([p["lon"] for p in places], [p["lat"] for p in places])
    pi, ri = tree.query(pts, predicate="within")
    region_of = np.full(len(places), -1, "int64")
    region_of[pi] = ri  # a point on a shared border lands in one of the two regions
    miss = np.nonzero(region_of < 0)[0]
    if len(miss):
        mi, mr = tree.query_nearest(pts[miss], max_distance=max_deg, all_matches=False)
        region_of[miss[mi]] = mr
    rows, cols, vals = [], [], []
    n_places = np.zeros(len(regions), "int64")
    pop = np.zeros(len(regions), "int64")
    for k, p in enumerate(places):
        r = region_of[k]
        if r < 0 or p["pop"] <= 0:
            continue
        cell = nearest_valid(valid, *cell_index(p["lat"], p["lon"]), radius)
        if cell is None:
            continue
        rows.append(r)
        cols.append(cell[0] * nx + cell[1])
        vals.append(float(p["pop"]))
        n_places[r] += 1
        pop[r] += p["pop"]
    m = sparse.csr_matrix((vals, (rows, cols)), shape=(len(regions), ny * nx), dtype="float64")
    m.sum_duplicates()
    log.info(
        "admin1 population: %d places in %d regions (%d outside every region)",
        int(n_places.sum()), int((n_places > 0).sum()), int((region_of < 0).sum()),
    )  # fmt: skip
    return m, n_places, pop
