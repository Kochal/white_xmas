"""The indicators step end to end on a synthetic cube."""

import numpy as np
import pytest
import zarr

from tests.synthetic import make_paths, small_config, synthetic_cells, write_cube
from whitexmas.indicators import compute_all


@pytest.fixture
def ind(tmp_path):
    cfg = small_config()
    paths = make_paths(tmp_path)
    cube, glacier = synthetic_cells()
    write_cube(paths.cube, cube, glacier)
    compute_all(cfg, paths)
    return cfg, zarr.open_group(str(paths.indicators), mode="r")


def test_windows_and_probabilities(ind):
    cfg, z = ind
    wins = [w.id for w in cfg.windows()]
    # decades that coincide with a normal are not repeated
    assert wins == ["2000_2019", "2000_2009", "2010_2019"]
    p = z["probability"][:]
    d = cfg.definition_ids.index("christmas_day")
    full, a, b = wins.index("2000_2019"), wins.index("2000_2009"), wins.index("2010_2019")
    assert np.isnan(p[d, full, 0, 0])  # ocean stays NaN
    assert p[d, full, 0, 1] == 100 and p[d, full, 1, 1] == 0
    assert p[d, full, 1, 0] == 50 and p[d, a, 1, 0] == 100 and p[d, b, 1, 0] == 0
    assert p[d, full, 1, 2] == 50
    assert z["n_valid"][d, full, 0, 0] == 0 and z["n_valid"][d, full, 1, 1] == 20


def test_change_trend_and_significance(ind):
    cfg, z = ind
    d = cfg.definition_ids.index("christmas_day")
    ch = z["change"][d]
    assert ch[1, 0] == -100 and ch[1, 2] == 0 and np.isnan(ch[0, 0])
    tr, pv = z["trend"][d], z["trend_p"][d]
    # step from white to green over 20 years: slope = -sum(|t|)/2 / sum(t^2) per year
    t = np.arange(20) - 9.5
    expected = (t * (np.r_[np.ones(10), np.zeros(10)] - 0.5)).sum() / (t**2).sum() * 1000
    assert tr[1, 0] == pytest.approx(expected, rel=1e-5)
    assert pv[1, 0] < 0.001
    assert pv[1, 2] > 0.5  # alternating: no monotonic trend
    assert tr[1, 1] == 0 and pv[1, 1] == 1
    assert np.isnan(tr[0, 0]) and np.isnan(pv[0, 0])


def test_glacier_flag(ind):
    _, z = ind
    np.testing.assert_array_equal(z["glacier"][:], [[False, True, False], [False] * 3])
    np.testing.assert_array_equal(z["land"][:], [[False, True, True], [True] * 3])


def test_rerun_is_skipped(tmp_path, caplog):
    cfg = small_config()
    paths = make_paths(tmp_path)
    write_cube(paths.cube, *synthetic_cells())
    compute_all(cfg, paths)
    mtime = paths.indicators.stat().st_mtime_ns
    caplog.set_level("INFO")
    compute_all(cfg, paths)
    assert "up to date" in caplog.text
    assert paths.indicators.stat().st_mtime_ns == mtime
