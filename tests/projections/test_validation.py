"""Validation scores: Brier score, bias scores, ERA5 aggregation to a model grid."""

import numpy as np
import pytest

from whitexmas.projections.cmip6 import box_mean
from whitexmas.projections.validation import bias_scores, brier


def test_brier_from_frequency_equals_yearly_brier():
    # 10 years, 3 white: forecast 40 % -> yearly BS = (3 * 0.36 + 7 * 0.16) / 10 = 0.22
    w = np.ones(1)
    assert brier(np.array([40.0]), np.array([0.3]), w) == pytest.approx(0.22)
    # a perfect frequency forecast scores f(1-f)
    assert brier(np.array([30.0]), np.array([0.3]), w) == pytest.approx(0.21)


def test_bias_scores_on_a_known_offset():
    lat = np.array([50.0, 60.0])
    model = np.array([[0.5, 0.6], [0.2, 0.3]])
    era = model - 0.1
    w = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, 2))
    sc = bias_scores(model, era, w)
    assert sc["bias_pp"] == pytest.approx(10.0)
    assert sc["mae_pp"] == pytest.approx(10.0)
    assert sc["corr"] == pytest.approx(1.0)


def test_box_mean_aggregates_fine_cells_to_nearest_model_cell():
    fine = np.full((1801, 3600), np.nan)
    fine[:900, :] = 1.0  # northern hemisphere land
    fine[:900, 1800:] = 3.0  # eastern half
    mlat = np.array([45.0, -45.0])
    mlon = np.array([90.0, 270.0])  # 0-360 like most models
    mean, cover = box_mean(fine, mlat, mlon)
    # the meridian at 180 E is equidistant from both centres and goes to the first one
    assert mean[0, 0] == pytest.approx(3.0, abs=0.01)  # 0-180 E
    assert mean[0, 1] == pytest.approx(1.0, abs=0.01)  # 180-360 E = -180-0
    assert np.isnan(mean[1]).all() and (cover[1] == 0).all()
    assert cover[0, 0] == pytest.approx(900 / 901, abs=1e-3)


def test_selection_rule_drops_gross_errors(tmp_path):
    import json

    from whitexmas.projections.validation import dropped_models, select_models

    (tmp_path / "skill.json").write_text(json.dumps({
        "reference": "ERA5-Land 1995-2014", "placeholder": False, "models": [
        {"model": "Good", "corr": 0.95, "mae_transition_pp": 15.0},
        {"model": "Pattern", "corr": 0.6, "mae_transition_pp": 20.0},
        {"model": "Melt", "corr": 0.9, "mae_transition_pp": 20.0},
    ]}))  # fmt: skip
    (tmp_path / "snow_amount.json").write_text(json.dumps({"models": [
        {"model": "Good", "ratio_to_era5": 0.6},
        {"model": "Pattern", "ratio_to_era5": 0.5},
        {"model": "Melt", "ratio_to_era5": 10.0},
    ]}))  # fmt: skip
    sel = select_models(tmp_path)
    assert sel["kept"] == ["Good"]
    assert set(sel["dropped"]) == {"Pattern", "Melt"}
    assert "snow amount" in sel["dropped"]["Melt"]
    assert sel["reference"] == "ERA5-Land 1995-2014" and sel["placeholder"] is False
    assert dropped_models(tmp_path) == ["Melt", "Pattern"]


def test_selection_made_without_real_era5_is_refused(tmp_path):
    import json

    from whitexmas.projections.validation import UntrustedSelection, dropped_models

    assert dropped_models(tmp_path) == []  # no selection yet: nothing dropped
    for sel in (
        {"reference": "placeholder-legacy-geotiff 2015_2024", "placeholder": True, "dropped": {}},
        {"dropped": {"X": "old selection without a reference"}},
    ):
        (tmp_path / "selection.json").write_text(json.dumps(sel))
        with pytest.raises(UntrustedSelection):
            dropped_models(tmp_path)


def test_validate_never_falls_back_to_the_placeholder(tmp_path):
    from whitexmas.paths import DataPaths
    from whitexmas.projections.settings import ProjSettings
    from whitexmas.projections.validation import validate

    paths = DataPaths(tmp_path)  # no snow cube, no raw ERA5-Land files
    with pytest.raises(FileNotFoundError, match="never uses the placeholder"):
        validate(paths, ProjSettings())
    assert not (tmp_path / "interim" / "projections" / "validation" / "selection.json").exists()
