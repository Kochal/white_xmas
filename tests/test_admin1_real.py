"""Checks on the real Natural Earth boundaries; skipped when the data folder is not present
(CI). They need no snow data, only ``$WHITEXMAS_DATA/external/``."""

import pytest
import shapely

from whitexmas.config import Config
from whitexmas.paths import DataPaths

EXT = DataPaths.from_env().external
NEEDED = ("ne_10m_admin_1_states_provinces.zip", "ne_10m_admin_0_countries.zip")
pytestmark = pytest.mark.skipif(
    not all((EXT / n).exists() for n in NEEDED), reason="Natural Earth files not downloaded"
)
# outlines the independent review found self-intersecting after simplification and rounding
REVIEW_INVALID = ("BM-SGE", "BR-GO", "CA-NL", "CN-FJ", "CO-CAU", "GR-D", "ID-MA", "MX-BCS")
WRAPPING = ("US-AK", "RU-CHU", "FJ-N", "FJ-E", "KIR00")


@pytest.fixture(scope="module")
def built():
    from whitexmas.admin1.boundaries import load_regions
    from whitexmas.admin1.geometry import boundaries_geojson, simplify_regions

    a1 = Config.load().raw["admin1"]
    regions = load_regions(EXT, a1)
    geoms = simplify_regions(regions, float(a1["simplify_deg"]), float(a1["min_part_km2"]))
    gj = boundaries_geojson(regions, geoms, int(a1["coord_decimals"]))
    return regions, gj


def test_every_web_outline_is_valid(built):
    regions, gj = built
    from whitexmas.admin1.geometry import shape_of

    by_id = {f["properties"]["id"]: shape_of(f["geometry"]) for f in gj["features"]}
    for rid in REVIEW_INVALID:
        assert by_id[rid].is_valid, rid
        assert by_id[rid].geom_type in ("Polygon", "MultiPolygon")
    invalid = [rid for rid, g in by_id.items() if not g.is_valid]
    assert invalid == []
    assert len(gj["features"]) == len(regions)


def test_antimeridian_regions_get_a_narrow_wrapped_bbox(built):
    from whitexmas.admin1.geometry import wrapped_bounds

    regions, _ = built
    by_id = {r["id"]: r for r in regions}
    for rid in WRAPPING:
        w, s, e, n = wrapped_bounds(by_id[rid]["geom"])
        assert e > 180 and e - w < 60, (rid, w, e)
        # every part lies inside the wrapped box (shift western parts by +360)
        for p in shapely.get_parts(by_id[rid]["geom"]):
            x0, _, x1, _ = p.bounds
            if x1 < w:
                x0, x1 = x0 + 360, x1 + 360
            assert w - 1e-9 <= x0 and x1 <= e + 1e-9, (rid, p.bounds)
    assert wrapped_bounds(by_id["DE-BY"]["geom"]) == pytest.approx(by_id["DE-BY"]["geom"].bounds)


def test_ids_are_unique_and_fit_the_url_pattern(built):
    from whitexmas.admin1.boundaries import ID_RE

    regions, _ = built
    ids = [r["id"] for r in regions]
    assert len(ids) == len(set(ids)) == 3988
    assert all(ID_RE.match(i) for i in ids)
    assert max(ids, key=len) == "SVN-JUGOVZHODNA-SLOVENIJA"
