"""Simplified region outlines for the web map (GeoJSON).

The admin-1 polygons form a coverage (neighbours share their borders), so they are simplified
together with GEOS coverage simplification, which keeps shared borders identical and leaves no
gaps or overlaps between neighbours. Whole-country fallback regions (reefs, the Cyprus buffer
zone) are simplified on their own. Then parts smaller than ``min_part_km2`` are dropped (a
region always keeps its largest part), coordinates are rounded to ``decimals``, and outlines
that the rounding made invalid are repaired with ``make_valid`` (polygon parts only).
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)
KM_PER_DEG = 111.195


def approx_km2(geom) -> float:
    """Polygon area in km² from degrees² scaled by cos(latitude of its centroid)."""
    if geom.is_empty:
        return 0.0
    c = geom.centroid
    return float(geom.area * KM_PER_DEG**2 * np.cos(np.radians(c.y)))


def _polygons(geom) -> list:
    import shapely

    if geom is None or geom.is_empty:
        return []
    t = geom.geom_type
    if t == "Polygon":
        return [geom]
    if t in ("MultiPolygon", "GeometryCollection"):
        out = []
        for g in shapely.get_parts(geom):
            out += _polygons(g)
        return out
    return []


def wrapped_bounds(geom) -> list[float]:
    """``[west, south, east, north]`` of the smallest longitude span that holds every part.

    Natural Earth splits regions that cross the antimeridian (Alaska, Chukotka, Fiji,
    Kiribati) into parts near +180 and -180, so their plain bounds span the whole globe. Here
    the parts' longitude intervals are merged on the circle and the largest empty gap is left
    out; when that gap is not the one across ±180, the box wraps and ``east`` is given + 360
    (e.g. Alaska ``[172.4, 51.2, 230.0, 71.4]``), which MapLibre's ``fitBounds`` accepts.
    A box is wrapped only when that makes it narrower than 180°; a region spread around most
    of the globe (both Antarctica features) keeps its plain ``[-180…180]``-style bounds.
    """
    x0, y0, x1, y1 = geom.bounds
    parts = _polygons(geom) or [geom]
    iv = sorted((p.bounds[0], p.bounds[2]) for p in parts)
    merged: list[list[float]] = []
    for a, b in iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    # gap across the antimeridian: from the last interval's end to the first one's start
    best_gap = merged[0][0] + 360.0 - merged[-1][1]
    west, east = x0, x1
    for k in range(1, len(merged)):
        gap = merged[k][0] - merged[k - 1][1]
        if gap > best_gap:
            best_gap = gap
            west, east = merged[k][0], merged[k - 1][1] + 360.0
    if east - west >= 180.0:
        west, east = x0, x1
    return [float(west), float(y0), float(east), float(y1)]


def drop_small_parts(geom, min_km2: float):
    import shapely

    parts = _polygons(geom)
    if not parts:
        return geom
    areas = [approx_km2(p) for p in parts]
    biggest = int(np.argmax(areas))
    keep = [p for k, p in enumerate(parts) if k == biggest or areas[k] >= min_km2]
    return keep[0] if len(keep) == 1 else shapely.MultiPolygon(keep)


def simplify_regions(regions: list[dict], tolerance: float, min_part_km2: float) -> list:
    import shapely

    geoms = np.array([r["geom"] for r in regions], dtype=object)
    cov = np.array([r["source"] != "ne_admin0" for r in regions])
    out = np.empty(len(regions), dtype=object)
    try:
        out[cov] = shapely.coverage_simplify(geoms[cov], tolerance)
    except Exception as e:  # noqa: BLE001  (invalid coverage: fall back to per-polygon)
        log.warning("coverage simplification failed (%s); simplifying regions one by one", e)
        out[cov] = shapely.simplify(geoms[cov], tolerance, preserve_topology=True)
    if (~cov).any():
        out[~cov] = shapely.simplify(geoms[~cov], tolerance, preserve_topology=True)
    for k in range(len(out)):
        g = out[k]
        if g is None or g.is_empty or not _polygons(g):
            g = regions[k]["geom"]  # a tiny island simplified away: keep the original
        out[k] = drop_small_parts(g, min_part_km2)
    return list(out)


def _ring(coords, d: int) -> list:
    pts = []
    for x, y in coords:
        p = [round(float(x), d), round(float(y), d)]
        if not pts or p != pts[-1]:
            pts.append(p)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts if len(pts) >= 4 else []


def _rounded(geom, decimals: int):
    """The polygon parts of ``geom`` with coordinates rounded, or None if nothing is left."""
    import shapely

    polys = []
    for p in _polygons(geom):
        ext = _ring(p.exterior.coords, decimals)
        if not ext:
            continue
        holes = [r for r in (_ring(i.coords, decimals) for i in p.interiors) if r]
        polys.append(shapely.Polygon(ext, holes))
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys)


def valid_polygonal(geom):
    """``make_valid`` and keep only the polygon parts (rounding can make a ring touch or cross
    itself, or two parts overlap; make_valid can return stray lines and points as well)."""
    import shapely

    if geom is None or geom.is_empty:
        return None
    if geom.is_valid:
        return geom
    parts = _polygons(shapely.make_valid(geom))
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts)


def _coords(ring, d: int) -> list:
    return [[round(float(x), d), round(float(y), d)] for x, y in ring.coords]


def to_geojson_geometry(geom, decimals: int) -> dict | None:
    """GeoJSON geometry with coordinates rounded to ``decimals`` and repaired to be valid.

    Vertices that ``make_valid`` adds where a rounded ring crossed itself are kept to
    ``decimals + 3`` places, so rounding them does not break validity again.
    """
    g = _rounded(geom, decimals)
    if g is None:
        return None
    fixed = not g.is_valid
    g = valid_polygonal(g)
    if g is None:
        return None
    d = decimals + 3 if fixed else decimals
    polys = [[_coords(p.exterior, d)] + [_coords(i, d) for i in p.interiors] for p in _polygons(g)]
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def shape_of(geojson_geometry: dict):
    import shapely.geometry

    return shapely.geometry.shape(geojson_geometry)


def boundaries_geojson(regions: list[dict], geoms: list, decimals: int) -> dict:
    """FeatureCollection; each feature has ``properties: {id, country}`` and a numeric
    ``id`` (the region's row in index.json) for MapLibre feature state. A region that the
    simplification collapsed (a thin peninsula such as Conakry) keeps its original outline."""
    feats = []
    for k, (r, g) in enumerate(zip(regions, geoms, strict=True)):
        geo = to_geojson_geometry(g, decimals)
        if geo is None:
            geo = to_geojson_geometry(r["geom"], decimals)
        if geo is None:
            log.warning("admin1: %s has no geometry left after simplification", r["id"])
            continue
        if not shape_of(geo).is_valid:
            log.warning("admin1: %s outline is invalid after repair", r["id"])
        feats.append({
            "type": "Feature", "id": k,
            "properties": {"id": r["id"], "country": r["country"]},
            "geometry": geo,
        })  # fmt: skip
    return {"type": "FeatureCollection", "features": feats}
