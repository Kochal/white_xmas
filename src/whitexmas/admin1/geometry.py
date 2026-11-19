"""Simplified region outlines for the web map (GeoJSON).

The admin-1 polygons form a coverage (neighbours share their borders), so they are simplified
together with GEOS coverage simplification, which keeps shared borders identical and leaves no
gaps or overlaps between neighbours. Whole-country fallback regions (reefs, the Cyprus buffer
zone) are simplified on their own. Then parts smaller than ``min_part_km2`` are dropped (a
region always keeps its largest part) and coordinates are rounded to ``decimals``.
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


def to_geojson_geometry(geom, decimals: int) -> dict | None:
    polys = []
    for p in _polygons(geom):
        ext = _ring(p.exterior.coords, decimals)
        if not ext:
            continue
        rings = [ext] + [r for r in (_ring(i.coords, decimals) for i in p.interiors) if r]
        polys.append(rings)
    if not polys:
        return None
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


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
        feats.append({
            "type": "Feature", "id": k,
            "properties": {"id": r["id"], "country": r["country"]},
            "geometry": geo,
        })  # fmt: skip
    return {"type": "FeatureCollection", "features": feats}
