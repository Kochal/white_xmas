"""The committed sample fixture follows the wx-admin1-v1 schema (docs/admin1.md)."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures" / "admin1_sample" / "admin1"


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def no_nan(obj):
    if isinstance(obj, float):
        assert math.isfinite(obj)
    elif isinstance(obj, list):
        for v in obj:
            no_nan(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            no_nan(v)


def test_index_rows_match_fields_and_boundaries():
    idx = load("index.json")
    assert idx["format"] == "wx-admin1-v1" and idx["contract"] == "1.6"
    fields = idx["fields"]
    assert fields[:7] == ["id", "name", "country", "lon", "lat", "area_km2", "flags"]
    assert all(len(r) == len(fields) for r in idx["rows"])
    ids = [r[0] for r in idx["rows"]]
    assert len(ids) == len(set(ids))
    gj = load("boundaries.json")
    feats = {f["id"]: f for f in gj["features"]}
    for k, r in enumerate(idx["rows"]):
        assert feats[k]["properties"]["id"] == r[0]
        assert feats[k]["properties"]["country"] == r[2]
        assert feats[k]["geometry"]["type"] in ("Polygon", "MultiPolygon")
    for f in idx["flags"]:
        assert f in ("admin0", "low_res", "nearest_cell", "no_land", "all_glacier")
    no_nan(idx)


def test_country_files_cover_every_region():
    idx = load("index.json")
    by_country = {}
    for r in idx["rows"]:
        by_country.setdefault(r[2], []).append(r[0])
    assert set(by_country) == set(idx["countries"])
    for c, ids in by_country.items():
        doc = load(f"c/{c}.json")
        no_nan(doc)
        assert [r["id"] for r in doc["regions"]] == ids
        nw, ny = len(doc["windows"]), doc["years"][1] - doc["years"][0] + 1
        for r in doc["regions"]:
            assert set(r["stats"]) == set(doc["thresholds"])
            for t in doc["thresholds"]:
                assert set(r["stats"][t]) == set(doc["definitions"])
                for s in r["stats"][t].values():
                    for k in ("p", "p_pop", "share50", "p5", "p95"):
                        assert len(s[k]) == nw
                    assert len(s["series"]) == ny
            if r["proj"]:
                g = len(doc["projections"]["gwls"])
                assert all(len(r["proj"][k]) == g for k in ("p10", "p50", "p90", "agree"))


def test_flagged_region_has_nulls_not_numbers():
    doc = load("c/CNM.json")
    (r,) = doc["regions"]
    assert "no_land" in r["flags"] and "admin0" in r["flags"]
    s = r["stats"]["calibrated"]["christmas_day"]
    assert all(v is None for v in s["p"]) and s["trend"] is None and r["proj"] is None
