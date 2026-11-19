"""manifest.json and the snow-depth thresholds (contract v1.4/v1.5, review should-fix 1)."""

import json

import pytest

from tests.synthetic import small_config, thresholds
from whitexmas.config import Config
from whitexmas.export import build_manifest, plan_all_layers


def _manifest(cfg):
    return build_manifest(cfg, plan_all_layers(cfg))


def test_default_threshold_4_leaves_no_1_cm_in_default_texts():
    cfg = small_config(thresholds=thresholds(4))
    m = _manifest(cfg)
    assert m["threshold_cm"] == 4
    assert "1 cm" not in json.dumps(m, ensure_ascii=False)
    assert all("at least 4 cm" in d["description"] for d in m["definitions"])
    assert "station_equivalent_cm" not in m


def test_manifest_with_calibrated_and_raw_thresholds():
    cfg = small_config(thresholds=thresholds(5, raw_cm=1, eq=1))
    m = _manifest(cfg)
    assert m["threshold_cm"] == 5 and m["station_equivalent_cm"] == 1
    assert [t["id"] for t in m["thresholds"]] == ["calibrated", "raw"]
    assert m["thresholds"][0] == {
        "id": "calibrated", "cm": 5, "default": True, "station_equivalent_cm": 1,
        "label": "Calibrated", "description": "At least 5 cm in ERA5-Land.",
    }  # fmt: skip
    assert m["thresholds"][1]["cm"] == 1 and "default" not in m["thresholds"][1]
    # definitions use the default threshold only
    assert all("at least 5 cm" in d["description"] for d in m["definitions"])
    assert not any("1 cm" in d["description"] for d in m["definitions"])
    ids = [ly["id"] for ly in m["layers"]]
    assert "prob__christmas_day__2000_2019" in ids
    assert "prob__christmas_day__2000_2019__raw" in ids
    assert "change__christmas_day__2000_2009__2010_2019__raw" in ids
    assert "trend__christmas_day__2000_2019__raw" in ids
    for ly in m["layers"]:
        assert ly["threshold"] == ("raw" if ly["id"].endswith("__raw") else "calibrated")
        assert ly["url"] == f"tiles/{ly['id']}.pmtiles"
        assert "src" not in ly
    assert len(ids) == len(set(ids))


def test_raw_minimal_layer_set_is_the_contract_floor():
    t = thresholds(5, raw_cm=1, eq=1)
    t[1]["layers"] = "minimal"
    cfg = small_config(thresholds=t)
    raw = sorted(ly["id"] for ly in plan_all_layers(cfg) if ly["threshold"] == "raw")
    assert raw == sorted([
        "prob__christmas_day__2000_2019__raw", "prob__christmas_day__2000_2009__raw",
        "prob__christmas_day__2010_2019__raw",
        "change__christmas_day__2000_2009__2010_2019__raw",
        "trend__christmas_day__2000_2019__raw",
    ])  # fmt: skip
    assert len(plan_all_layers(cfg, others_minimal=True)) == len(plan_all_layers(cfg))


def test_projection_layers_get_the_default_threshold():
    cfg = small_config(thresholds=thresholds(5, raw_cm=1, eq=1))
    frag = {"layers": [{"id": "proj__christmas_day__gwl2.0", "kind": "projection",
                        "url": "tiles/p.pmtiles"}],
            "projections": {"available": True}}  # fmt: skip
    m = build_manifest(cfg, plan_all_layers(cfg) + frag["layers"], frag)
    assert m["layers"][-1]["threshold"] == "calibrated"
    assert m["projections"] == {"available": True}


def test_shipped_config_is_calibrated_5_cm_with_raw_1_cm():
    cfg = Config.load()
    assert cfg.threshold_cm == 5 and cfg.station_equivalent_cm == 1
    assert [(t["id"], t["cm"]) for t in cfg.thresholds] == [("calibrated", 5), ("raw", 1)]
    assert cfg.definitions[0]["description"] == (
        "Daily-mean snow depth on 25 December is at least 5 cm."
    )
    text = json.dumps(cfg.thresholds + cfg.definitions)
    assert not any(ph in text for ph in ("{cm}", "{station_equivalent_cm}", "{threshold_cm}"))


@pytest.mark.parametrize("bad", [4.5, "2.5", -1])
def test_fractional_or_negative_threshold_is_rejected(bad):
    with pytest.raises(ValueError):
        _ = small_config(thresholds=thresholds(bad)).thresholds


def test_whole_number_float_threshold_is_accepted():
    assert small_config(thresholds=thresholds(4.0)).threshold_cm == 4


def test_exactly_one_default_threshold():
    t = thresholds(5, raw_cm=1)
    t[1]["default"] = True
    with pytest.raises(ValueError):
        _ = small_config(thresholds=t).thresholds
