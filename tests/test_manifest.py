"""manifest.json follows the single threshold value in the config (review should-fix 1)."""

import json

import pytest

from tests.synthetic import small_config
from whitexmas.config import Config
from whitexmas.export import build_manifest, plan_layers


def _manifest(**overrides):
    cfg = small_config(**overrides)
    return cfg, build_manifest(cfg, plan_layers(cfg))


def test_threshold_4_leaves_no_1_cm_in_manifest():
    cfg, m = _manifest(threshold_cm=4)
    text = json.dumps(m, ensure_ascii=False)
    assert m["threshold_cm"] == 4
    assert "1 cm" not in text
    assert all("at least 4 cm" in d["description"] for d in m["definitions"])
    assert "station_equivalent_cm" not in m


def test_station_equivalent_is_passed_through_when_set():
    _, m = _manifest(threshold_cm=4, station_equivalent_cm=1)
    assert m["station_equivalent_cm"] == 1
    assert list(m)[5:7] == ["threshold_cm", "station_equivalent_cm"]


def test_default_config_texts_say_1_cm():
    cfg = Config.load()
    assert cfg.definitions[0]["description"] == (
        "Daily-mean snow depth on 25 December is at least 1 cm."
    )
    assert "{threshold_cm}" not in json.dumps(cfg.definitions)


@pytest.mark.parametrize("bad", [4.5, "2.5", -1])
def test_fractional_or_negative_threshold_is_rejected(bad):
    with pytest.raises(ValueError):
        _ = small_config(threshold_cm=bad).threshold_cm


def test_whole_number_float_threshold_is_accepted():
    assert small_config(threshold_cm=4.0).threshold_cm == 4
