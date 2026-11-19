import gzip

import numpy as np
import pytest

from whitexmas.stations import calibrate, read_snwd


def _row(obs, model_by_t, agree=90.0):
    return {"obs_pct": obs, "model_pct": model_by_t, "agree_pct": dict.fromkeys(model_by_t, agree)}


def test_calibrate_picks_threshold_with_smallest_bias_and_skips_always_white():
    T = [1, 2, 3]
    rows = [
        _row(30, {1: 60, 2: 40, 3: 30}),
        _row(50, {1: 80, 2: 60, 3: 52}),
        _row(10, {1: 40, 2: 20, 3: 8}),
        _row(100, {1: 100, 2: 100, 3: 100}),  # always white: excluded
    ]
    cal = calibrate(rows, T, always_white_pct=95)
    assert cal["n_calibration"] == 3 and cal["n_excluded"] == 1
    assert cal["best_cm"] == 3
    assert cal["stats"][1]["bias_pp"] == pytest.approx(30.0)
    assert cal["stats"][3]["mae_pp"] == pytest.approx((0 + 2 + 2) / 3)
    assert sum(cal["loo_counts"].values()) == 3


def test_read_snwd_dec25_and_zero_share(tmp_path):
    lines = [
        "X,20001225,SNWD,30,,,E,",
        "X,20001224,SNWD,0,,,E,",
        "X,20011225,SNWD,0,,,E,",
        "X,20021225,SNWD,50,,G,E,",  # quality-flagged: dropped
        "X,20031225,TMAX,10,,,E,",
        "X,20040115,SNWD,100,,,E,",  # not December
    ]
    p = tmp_path / "X.csv.gz"
    with gzip.open(p, "wt") as f:
        f.write("\n".join(lines) + "\n")
    dec25, zero_share = read_snwd(p)
    assert dec25 == {2000: 30, 2001: 0}
    assert zero_share == pytest.approx(2 / 3)
    assert np.isfinite(zero_share)


def test_exclusion_rules():
    from whitexmas.stations import _exclusion

    sc = {"always_white_pct": 95, "min_coverage": 0.8, "max_elev_diff_m": 200}
    base = {"obs_pct": 40, "coverage": 0.95, "cell_elev_m": 500.0, "elev_m": 450.0}
    assert _exclusion(base, sc) is None
    assert _exclusion({**base, "obs_pct": 97}, sc) == "always white"
    assert _exclusion({**base, "coverage": 0.4}, sc).startswith("patchy")
    assert _exclusion({**base, "cell_elev_m": 1461.0}, sc).startswith("cell +1011 m")


def test_calibration_line_names_each_criterion():
    from whitexmas.stations import calibration_line

    cal = {
        "best_cm": 6,
        "stats": {
            "4": {"bias_pp": 4.7, "mae_pp": 8.68},
            "5": {"bias_pp": 1.6, "mae_pp": 8.64},
            "6": {"bias_pp": -1.2, "mae_pp": 9.29},
        },
    }
    assert calibration_line(cal, 5) == (
        "smallest mean bias: 6 cm (-1.2 pp); smallest MAE: 5 cm (8.6 pp); shipped: 5 cm"
    )
