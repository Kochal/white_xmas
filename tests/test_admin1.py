"""States and provinces: weights, regional statistics and export on a small synthetic grid.

The grid is the real 0.1° grid anchored at (-180, 90), truncated to 30 x 40 cells
(lat 90 … 87.1, lon -180 … -176.1); the polygons are toy boxes in that corner.
"""

import json

import numpy as np
import pytest
import shapely
from scipy import sparse

from tests.synthetic import YEARS, small_config
from whitexmas.admin1 import stats as st
from whitexmas.admin1.build import compute_weights, observed_stats
from whitexmas.admin1.export import build_index, region_flags, stage, write_web
from whitexmas.admin1.weights import region_fractions

NY, NX = 30, 40


def lon(i):  # west edge of column i
    return -180.05 + 0.1 * i


def lat(j):  # north edge of row j
    return 90.05 - 0.1 * j


def box(i0, i1, j0, j1):
    """Cells i0..i1-1, j0..j1-1 exactly."""
    return shapely.box(lon(i0), lat(j1), lon(i1), lat(j0))


def region(rid, geom, country="AAA", source="ne_admin1"):
    return {"id": rid, "name": rid, "name_local": "", "type": "State", "country": country,
            "country_name": country, "adm0_a3": country, "source": source, "n_features": 1,
            "geom": geom}  # fmt: skip


# --------------------------------------------------------------------------- fractions
def test_exact_fractions_of_an_aligned_box_and_a_half_cell():
    idx, fr = region_fractions(box(2, 5, 3, 5), NY, NX)
    assert sorted(idx.tolist()) == sorted(j * NX + i for j in (3, 4) for i in (2, 3, 4))
    assert np.allclose(fr, 1.0)
    half = shapely.box(lon(2), lat(4), lon(2) + 0.05, lat(3))  # west half of cell (3, 2)
    idx, fr = region_fractions(half, NY, NX)
    assert idx.tolist() == [3 * NX + 2] and fr[0] == pytest.approx(0.5)


def test_supersampled_fractions_match_area_and_edges():
    g = shapely.Point(-178.0, 88.5).buffer(1.2)  # ~ 450 cells: supersampled path
    idx, fr = region_fractions(g, NY, NX, exact_max_cells=100, k=10)
    assert fr.sum() == pytest.approx(g.area / 0.01, rel=0.01)
    idx2, fr2 = region_fractions(g, NY, NX, exact_max_cells=10_000)  # exact
    a = dict(zip(idx.tolist(), fr.tolist(), strict=True))
    b = dict(zip(idx2.tolist(), fr2.tolist(), strict=True))
    assert set(a) <= set(b)
    assert max(abs(a.get(c, 0) - v) for c, v in b.items()) <= 0.06  # a few sub-cells per edge
    idx, fr = region_fractions(box(1, 30, 1, 25), NY, NX, exact_max_cells=10, k=4)
    assert np.allclose(fr, 1.0) and len(idx) == 29 * 24


def test_fractions_wrap_across_the_antimeridian():
    g = shapely.MultiPolygon([
        shapely.box(179.85, 60.05, 180.0, 60.35), shapely.box(-180.0, 60.05, -179.85, 60.35)
    ])  # fmt: skip
    idx, fr = region_fractions(g, 1801, 3600)
    cols = sorted({int(c % 3600) for c in idx})
    # 179.85-179.95 is column 3599, 179.95-180 and -180 to -179.95 are column 0, then 1
    assert cols == [0, 1, 3599]
    by_col = {}
    for c, f in zip(idx.tolist(), fr.tolist(), strict=True):
        by_col.setdefault(c % 3600, []).append(f)
    assert np.allclose(by_col[0], 1.0)  # both halves of column 0 add up


# --------------------------------------------------------------------------- stats
def test_weighted_mean_percentiles_and_extremes():
    w = sparse.csr_matrix(np.array([[1.0, 1.0, 2.0, 0.0], [0.0, 0.0, 0.0, 1.0]]))
    v = np.array([10.0, 20.0, 40.0, np.nan])
    usable = np.array([True, True, True, True])
    m = st.weighted_mean(w, v, usable)
    assert m[0] == pytest.approx(27.5) and np.isnan(m[1])  # NaN stays NaN, never 0
    assert st.weighted_mean(w, v, np.array([True, True, False, True]))[0] == 15.0
    q = st.weighted_percentiles(w, v, usable, (0, 25, 50, 100))
    assert q[:, 0].tolist() == [10.0, 10.0, 20.0, 40.0] and np.isnan(q[0, 1])
    frac = sparse.csr_matrix(np.array([[1.0, 0.6, 0.2, 0.0]]))
    lo, hi = st.weighted_extremes(frac, v, usable)
    assert (lo[0], hi[0]) == (10.0, 20.0)  # the 20 %-inside cell does not set the max


def test_trend_and_mann_kendall_match_references():
    import pymannkendall as mk

    rng = np.random.default_rng(3)
    years = np.arange(1950, 2026)
    series = np.clip(60 - 0.3 * (years - 1950) + rng.normal(0, 15, (4, len(years))), 0, 100)
    series[3] = np.round(series[3] / 25) * 25  # many ties
    p = st.mann_kendall_p(series)
    for r in range(4):
        assert p[r] == pytest.approx(mk.original_test(series[r]).p, rel=1e-6)
    slope = st.ols_slope_per_decade(series, years)
    assert slope[0] == pytest.approx(np.polyfit(years, series[0], 1)[0] * 10)
    assert st.mann_kendall_p(np.zeros((1, 20)))[0] == 1.0


def test_ensemble_summary_orders_median_of_regional_means():
    means = np.array([[10.0, 50.0], [20.0, 50.0], [30.0, 50.02], [np.nan, 49.9]])
    e = st.ensemble_summary(means, baseline=np.array([40.0, 50.0]), zero_pp=0.05)
    assert e["p50"][0] == 20.0 and e["change"][0] == -20.0
    assert e["agree"].tolist() == [True, True]  # region 2: 3 of 4 models "no change"
    assert e["n_models"].tolist() == [3, 4]


# --------------------------------------------------------------------------- end to end
@pytest.fixture
def synthetic():
    """Cube (20 years, 3 days, 30, 40): land everywhere except columns >= 34 (ocean).

    Region A (cells i 0-9, j 0-9): white in 2000-2009, green after; glacier in i 0-1.
    Region B (i 10-29, j 0-29): never white except rows j >= 20, always white.
    Region C: a tiny island in the ocean 1 cell from land (nearest-cell fallback).
    Region D: a box in the ocean 4 cells from land (3 across the wrapped edge): no land.
    Region E: all glacier.
    """
    from whitexmas.indicators import compute_band

    cfg = small_config()
    n = len(YEARS)
    cube = np.zeros((n, 3, NY, NX), "int16")
    cube[:, :, :, 34:] = -1
    cube[:10, :, 0:10, 0:10] = 20
    cube[:, :, 20:30, 10:30] = 30
    cube[:, :, 0:10, 0:2] = 3000  # glacier, always white
    cube[:, :, 25:30, 30:34] = 3000  # E: glacier
    gfrac = np.zeros((NY, NX), "float32")
    gfrac[0:10, 0:2] = 1.0
    gfrac[25:30, 30:34] = 1.0
    ind = compute_band(cube, np.array(YEARS), gfrac, cfg.definition_ids, cfg.windows(),
                       cfg.change_pair, 1)  # fmt: skip
    regions = [
        region("AA-A", box(0, 10, 0, 10)),
        region("AA-B", box(10, 30, 0, 30)),
        region("AA-C", shapely.box(lon(34) + 0.02, lat(5) - 0.08, lon(34) + 0.06, lat(5) - 0.02)),
        region("AA-D", box(37, 38, 10, 12), country="BBB", source="ne_admin0"),
        region("AA-E", box(30, 34, 25, 30)),
    ]
    places = [
        {"lat": 89.5, "lon": -179.5, "pop": 100000},  # in A
        {"lat": 88.5, "lon": -178.0, "pop": 50000},  # in B, green part
        {"lat": 87.3, "lon": -178.0, "pop": 150000},  # in B, white part
    ]
    w = compute_weights(regions, ind["land"], ind["glacier"], places, cfg.raw["admin1"])
    orog = np.tile(np.linspace(0, 3900, NX), (NY, 1))
    lat_c = 90 - 0.1 * np.arange(NY)
    out, yrs, _ = observed_stats(
        cfg, w["frac"], w["extra"], w["pop"], w,
        lat=lat_c, land=ind["land"], glacier=ind["glacier"], orog=orog,
        prob=lambda ti, di, wi: ind["probability"][di, wi], cube=cube, years=np.array(YEARS),
        band=7,
    )  # fmt: skip
    return cfg, regions, ind, out, yrs, w


def test_regional_values_from_synthetic_cube(synthetic):
    cfg, regions, ind, s, yrs, w = synthetic
    wid = [x.id for x in cfg.windows()]
    full, first, second = wid.index("2000_2019"), wid.index("2000_2009"), wid.index("2010_2019")
    # A: glacier columns excluded; the rest white in 2000-2009 only
    assert s["p"][0, 0, full, 0] == pytest.approx(50.0)
    assert s["p"][0, 0, first, 0] == pytest.approx(100.0)
    assert s["p"][0, 0, second, 0] == pytest.approx(0.0)
    assert s["glacier_pct"][0] == pytest.approx(20.0, abs=0.5)
    assert s["series"][0, 0, 0].tolist() == [100.0] * 10 + [0.0] * 10
    assert s["trend"][0, 0, 0] < 0 and s["trend_p"][0, 0, 0] < 0.01
    # B: rows 20-29 always white; area-weighted by cos(lat), which near the pole weighs the
    # southern rows far more than the northern ones
    cos = np.cos(np.radians(90 - 0.1 * np.arange(NY)))
    expect = 100 * cos[20:30].sum() / cos[0:30].sum()
    assert s["p"][0, 0, full, 1] == pytest.approx(expect)
    assert s["p5"][0, 0, full, 1] == 0.0 and s["p95"][0, 0, full, 1] == 100.0
    assert s["share50"][0, 0, full, 1] == pytest.approx(expect)
    assert s["trend_p"][0, 0, 1] == 1.0  # constant series: no trend
    # population: B's places 50k green, 150k white -> 75 %
    assert s["p_pop"][0, 0, full, 1] == pytest.approx(75.0)
    assert s["n_places"].tolist()[:2] == [1, 2]
    # C: no land inside, nearest land cell used; D: nothing nearby; E: all glacier
    assert s["fallback"][2] and np.isfinite(s["p"][0, 0, full, 2])
    assert not s["has_land"][3] and np.isnan(s["p"][..., 3]).all()
    assert s["has_land"][4] and not s["has_usable"][4] and np.isnan(s["p"][..., 4]).all()
    flags = [region_flags({**s, "source": [r["source"] for r in regions]}, k, 3)
             for k in range(5)]  # fmt: skip
    assert flags == [[], [], ["nearest_cell", "low_res"], ["admin0", "no_land"],
                     ["all_glacier"]]  # fmt: skip
    # elevation: min/max over cells mostly inside
    assert s["elev_min"][0] == pytest.approx(200.0) and s["elev_max"][0] == pytest.approx(900.0)
    # the regional window mean equals the mean of the yearly series where nothing is missing
    assert s["series"][0, 0, 1].mean() == pytest.approx(s["p"][0, 0, full, 1])


def test_export_writes_valid_json_and_stage_copies_it(synthetic, tmp_path):
    from whitexmas.admin1.build import export_info
    from whitexmas.admin1.geometry import boundaries_geojson, simplify_regions

    cfg, regions, ind, s, yrs, w = synthetic
    s = {k: v for k, v in s.items() if not k.startswith("_")}
    s["source"] = np.array([r["source"] for r in regions])
    meta = []
    for r in regions:
        p = shapely.point_on_surface(r["geom"])
        meta.append({**{k: v for k, v in r.items() if k != "geom"}, "lon": p.x, "lat": p.y,
                     "bbox": list(r["geom"].bounds)})  # fmt: skip
    info = export_info(cfg, {"thresholds": [t["id"] for t in cfg.thresholds],
                             "definitions": cfg.definition_ids,
                             "windows": [x.id for x in cfg.windows()],
                             "years": [int(y) for y in yrs], "projections": {}})  # fmt: skip
    gj = boundaries_geojson(regions, simplify_regions(regions, 0.01, 0.0), 3)
    prod = tmp_path / "products" / "admin1"
    sizes = write_web(prod / "web", meta, s, gj, info)
    idx = json.loads((prod / "web/admin1/index.json").read_text(encoding="utf-8"))
    assert [r[0] for r in idx["rows"]] == [r["id"] for r in regions]
    d = dict(zip(idx["fields"], idx["rows"][3], strict=True))
    text = ("id", "name", "country", "lon", "lat", "area_km2", "flags", "type", "name_local")
    nums = [v for k, v in d.items() if k not in text]
    assert nums == [None] * len(nums)  # no NaN, nulls
    assert "p_gwl2.0" not in idx["fields"]  # no projections in this build
    a = json.loads((prod / "web/admin1/c/AAA.json").read_text(encoding="utf-8"))
    assert a["projections"] is None and a["regions"][0]["proj"] is None
    frag = {"admin1": {"available": True, "format": "wx-admin1-v1"},
            "files": {k: {"bytes": v} for k, v in sizes.items()}}  # fmt: skip
    (prod / "manifest_fragment.json").write_text(json.dumps(frag))
    web_out = tmp_path / "web_out"
    assert stage(prod, web_out) == frag["admin1"]
    assert (web_out / "admin1/c/BBB.json").exists()
    (prod / "web/admin1/c/BBB.json").write_text("{}")  # changed since the build: refuse
    assert stage(prod, web_out) is None
    countries = build_index(meta, s, info)["countries"]
    assert countries == {"AAA": {"name": "AAA", "regions": 4}, "BBB": {"name": "BBB", "regions": 1}}


def test_dissolve_and_ids():
    from whitexmas.admin1.boundaries import build_regions

    def feat(code, iso, name, a3, **kw):
        base = {"adm1_code": code, "iso_3166_2": iso, "name": name, "name_en": "",
                "type": "", "type_en": "Province", "adm0_a3": a3, "admin": a3, "region": "",
                "region_cod": "", "geonunit": ""}  # fmt: skip
        base.update(kw)
        base["geom"] = box(0, 1, 0, 1)
        return base

    admin1 = [
        feat("ITA-1", "IT-MI", "Milano", "ITA", region="Lombardia", region_cod="IT-25"),
        feat("ITA-2", "IT-BG", "Bergamo", "ITA", region="Lombardia", region_cod="IT-25"),
        feat("DEU-1", "DE-BY", "Bayern", "DEU", name_en="Bavaria"),
        feat("MDG-1", "MG-M", "Boeny", "MDG"),
        feat("MDG-2", "MG-M", "Sofia", "MDG"),
        feat("KOS+1?", "XK-X02~", "Decani", "KOS"),
    ]
    countries = [
        {"iso_a3": a, "adm0_a3": a, "name": a, "geom": box(0, 1, 0, 1)}
        for a in ("ITA", "DEU", "MDG", "KOS", "CNM")
    ]
    dissolve = {
        "ITA": {"by": "region", "id_from": "region_cod", "names": {"Lombardia": "Lombardy"}}
    }
    regs = {r["id"]: r for r in build_regions(admin1, countries, dissolve)}
    assert set(regs) == {"IT-25", "DE-BY", "MDG-1", "MDG-2", "KOS1", "CNM"}
    assert regs["IT-25"]["name"] == "Lombardy" and regs["IT-25"]["name_local"] == "Lombardia"
    assert regs["IT-25"]["n_features"] == 2
    assert regs["DE-BY"]["name"] == "Bavaria" and regs["DE-BY"]["name_local"] == "Bayern"
    assert regs["CNM"]["source"] == "ne_admin0"


# --------------------------------------------------------------------------- review round
def test_benjamini_hochberg_matches_reference_and_skips_untestable():
    p = np.array([0.01, 0.04, 0.03, 0.20, np.nan, 1.0])
    testable = np.array([True, True, True, True, True, False])
    q = st.benjamini_hochberg(p, testable)
    # m = 4 testable: sorted 0.01, 0.03, 0.04, 0.20 -> 0.04, 0.0533, 0.0533, 0.20
    assert q[0] == pytest.approx(0.04)
    assert q[1] == pytest.approx(0.04 * 4 / 3) and q[2] == pytest.approx(0.04 * 4 / 3)
    assert q[3] == pytest.approx(0.2)
    assert np.isnan(q[4]) and np.isnan(q[5])  # NaN p and the constant series get no q
    assert (q[:4] >= p[:4]).all()


def test_testable_series_excludes_constant_and_short_rows():
    s = np.array([[0.0] * 10, [100.0] * 10, [0.0] * 9 + [5.0], [np.nan] * 8 + [1.0, 2.0]])
    assert st.testable_series(s).tolist() == [False, False, True, False]


def test_trend_q_in_index_and_country_files(synthetic, tmp_path):
    from whitexmas.admin1.build import export_info

    cfg, regions, ind, s, yrs, w = synthetic
    s = {k: v for k, v in s.items() if not k.startswith("_")}
    s["source"] = np.array([r["source"] for r in regions])
    meta = [{**{k: v for k, v in r.items() if k != "geom"}, "lon": 0.0, "lat": 0.0,
             "bbox": [0, 0, 1, 1]} for r in regions]  # fmt: skip
    info = export_info(cfg, {"thresholds": [t["id"] for t in cfg.thresholds],
                             "definitions": cfg.definition_ids,
                             "windows": [x.id for x in cfg.windows()],
                             "years": [int(y) for y in yrs], "projections": {}})  # fmt: skip
    idx = build_index(meta, s, info)
    f = idx["fields"]
    assert f[-3:] == ["type", "trend_q", "name_local"]
    rows = {r[0]: dict(zip(f, r, strict=True)) for r in idx["rows"]}
    assert rows["AA-A"]["type"] == "State"
    # A is the only testable region (B is constant), so its q equals its p
    assert rows["AA-A"]["trend_q"] == rows["AA-A"]["trend_p"]
    assert rows["AA-B"]["trend_q"] is None and rows["AA-B"]["trend_p"] == 1.0


def test_wrapped_bounds_for_antimeridian_regions():
    from whitexmas.admin1.geometry import wrapped_bounds

    alaska = shapely.MultiPolygon([
        shapely.box(-179.14, 51.2, -129.98, 71.4), shapely.box(172.4, 52.0, 179.78, 53.0),
    ])  # fmt: skip
    assert wrapped_bounds(alaska) == pytest.approx([172.4, 51.2, 230.02, 71.4])
    chukotka = shapely.MultiPolygon([
        shapely.box(-180.0, 64.0, -169.0, 68.0), shapely.box(160.0, 61.8, 180.0, 71.6),
    ])  # fmt: skip
    assert wrapped_bounds(chukotka) == pytest.approx([160.0, 61.8, 191.0, 71.6])
    bavaria = shapely.box(8.98, 47.27, 13.84, 50.56)
    assert wrapped_bounds(bavaria) == pytest.approx([8.98, 47.27, 13.84, 50.56])
    antarctica = shapely.box(-180.0, -90.0, 180.0, -60.0)
    assert wrapped_bounds(antarctica) == pytest.approx([-180.0, -90.0, 180.0, -60.0])
    # parts spread around most of the globe (Natural Earth's second Antarctica feature): plain
    ata = shapely.MultiPolygon(
        [shapely.box(-171.9, -83, 121.2, -61), shapely.box(161.8, -80, 169.96, -70)]
    )
    assert wrapped_bounds(ata) == pytest.approx([-171.9, -83, 169.96, -61])
    # a region with parts in both hemispheres but far from the antimeridian keeps plain bounds
    split = shapely.MultiPolygon([shapely.box(-10, 0, -5, 1), shapely.box(5, 0, 10, 1)])
    assert wrapped_bounds(split) == pytest.approx([-10, 0, 10, 1])


def test_region_ids_fit_the_url_pattern():
    from whitexmas.admin1.boundaries import ID_RE

    assert ID_RE.match("SVN-JUGOVZHODNA-SLOVENIJA")  # 25 chars, the longest real id
    assert not ID_RE.match("-DE")
    assert not ID_RE.match("A" * 49)
