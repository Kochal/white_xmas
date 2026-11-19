"""Indicators on small synthetic series with hand-computed expectations."""

import numpy as np
import pymannkendall as mk
import pytest

from whitexmas.indicators import glacier_flag, mann_kendall_p, ols_trend_pp_per_decade, probability

N = np.nan


def test_probability_and_n_valid_ignore_nan():
    # 3 cells x 5 years: half white, all white, ocean (all NaN)
    w = np.array([[1, 1, N], [0, 1, N], [1, 1, N], [0, 1, N], [N, 1, N]], dtype="float32")
    p, n = probability(w, min_valid=1)
    np.testing.assert_allclose(p[:2], [50.0, 100.0])
    assert np.isnan(p[2])
    np.testing.assert_array_equal(n, [4, 5, 0])


def test_probability_needs_min_valid_years():
    w = np.array([[1], [N], [N], [0]], dtype="float32")
    p, n = probability(w, min_valid=3)
    assert np.isnan(p[0]) and n[0] == 2


def test_ols_trend_known_slope():
    years = np.arange(2000, 2010)
    # white in the first 5 years, green in the last 5: slope of a step series
    x = np.array([1] * 5 + [0] * 5, dtype="float32")[:, None]
    t = years - years.mean()
    expected = (t * (x[:, 0] - x.mean())).sum() / (t**2).sum() * 100 * 10
    got = ols_trend_pp_per_decade(x, years)
    assert got[0] == pytest.approx(expected)
    assert got[0] == pytest.approx(-1000 * 12.5 / 82.5)  # hand-computed: -151.5 pp/decade


def test_ols_trend_constant_and_nan():
    years = np.arange(10)
    x = np.stack([np.ones(10), np.full(10, N)], axis=1).astype("float32")
    x[3, 0] = N
    got = ols_trend_pp_per_decade(x, years)
    assert got[0] == 0.0
    assert np.isnan(got[1])


def test_ols_trend_skips_missing_years():
    years = np.arange(6)
    x = np.array([0, 0, N, 1, 1, 1], dtype="float32")[:, None]
    valid = np.array([0, 1, 3, 4, 5])
    xv = np.array([0, 0, 1, 1, 1])
    slope = np.polyfit(valid, xv, 1)[0]
    assert ols_trend_pp_per_decade(x, years)[0] == pytest.approx(slope * 1000)


def test_mann_kendall_matches_pymannkendall():
    rng = np.random.default_rng(1)
    n_years = 76
    p_white = np.linspace(0.7, 0.2, n_years)
    series = (rng.random((n_years, 40)) < p_white[:, None]).astype("float32")
    series[:, 0] = 0.0
    series[:, 1] = 1.0
    series[::7, 2] = N
    got = mann_kendall_p(series)
    for c in range(3, 40):
        assert got[c] == pytest.approx(mk.original_test(series[:, c]).p, abs=1e-9)
    # with NaN: same as the test on the valid years only
    v = series[:, 2][~np.isnan(series[:, 2])]
    assert got[2] == pytest.approx(mk.original_test(v).p, abs=1e-9)
    # constant series: no trend
    assert got[0] == 1.0 and got[1] == 1.0


def test_mann_kendall_strong_trend_is_significant():
    x = np.array([1] * 30 + [0] * 30, dtype="float32")[:, None]
    assert mann_kendall_p(x)[0] < 1e-6


def test_mann_kendall_all_nan():
    assert np.isnan(mann_kendall_p(np.full((10, 1), N, "float32"))[0])


def test_glacier_flag_needs_mask_and_snow_every_year():
    # cells: glacier always white | glacier with a green year | non-glacier always white | ocean
    any_white = np.array([[1, 1, 1, N], [1, 0, 1, N], [1, 1, 1, N]], dtype="float32")
    frac = np.array([0.9, 0.9, 0.1, N], dtype="float32")
    np.testing.assert_array_equal(
        glacier_flag(any_white, frac, min_fraction=0.5), [True, False, False, False]
    )
