"""White-Christmas frequencies from daily model snow (SWE) around Christmas."""

import cftime
import numpy as np
import pytest

from whitexmas.projections.frequency import (
    OFFSETS,
    season_cube,
    white_fraction,
    window_counts,
)


def _dates(years, calendar="noleap"):
    out = []
    for y in years:
        out += [
            cftime.datetime(y, 12, d, 12, calendar=calendar)
            for d in range(11, 32)
            if not (calendar == "360_day" and d == 31)
        ]
        out += [cftime.datetime(y + 1, 1, d, 12, calendar=calendar) for d in range(1, 9)]
    return out


def test_season_cube_places_each_day_relative_to_christmas():
    t = _dates([2000, 2001])
    vals = np.array([d.day + 100 * (d.month == 1) for d in t], dtype="float64")[:, None]
    years, cube = season_cube(vals, t)
    assert list(years) == [2000, 2001]
    assert cube.shape == (2, len(OFFSETS), 1)
    c = list(OFFSETS).index(0)
    assert cube[0, c, 0] == 25  # Dec 25
    assert cube[1, c + 7, 0] == 101  # Jan 1 is Christmas + 7 in a 31-day December
    assert cube[0, 0, 0] == 11  # Dec 11 = Christmas - 14


def test_season_cube_360_day_calendar_has_no_dec_31():
    t = _dates([2000], calendar="360_day")
    vals = np.arange(len(t), dtype="float64")[:, None]
    _, cube = season_cube(vals, t)
    c = list(OFFSETS).index(0)
    # Jan 1 follows Dec 30, so it is Christmas + 6 in this calendar; nothing is lost
    assert np.isfinite(cube[0, c + 6, 0])
    assert np.isfinite(cube[0]).sum() == len(t)


def test_christmas_day_without_pooling_is_the_dec_25_rule():
    years = np.arange(4)
    cube = np.zeros((4, len(OFFSETS), 1))
    c = list(OFFSETS).index(0)
    cube[[0, 2], c, 0] = 3.0  # white on Dec 25 in years 0 and 2
    cube[1, c - 1, 0] = 3.0  # Dec 24 only
    f = white_fraction(cube, "christmas_day", threshold=2.5, pool_days=0)
    np.testing.assert_array_equal(f[:, 0], [1, 0, 1, 0])
    k, n = window_counts(f, years, 0, 3)
    assert (k[0], n[0]) == (2, 4)


def test_three_day_rules():
    cube = np.zeros((1, len(OFFSETS), 3))
    c = list(OFFSETS).index(0)
    cube[0, c - 1 : c + 2, 0] = 5.0  # cell 0: white Dec 24-26
    cube[0, c + 1, 1] = 5.0  # cell 1: Dec 26 only
    all3 = white_fraction(cube, "all_three_days", threshold=2.5, pool_days=0)
    anyd = white_fraction(cube, "any_day", threshold=2.5, pool_days=0)
    np.testing.assert_array_equal(all3[0], [1, 0, 0])
    np.testing.assert_array_equal(anyd[0], [1, 1, 0])


def test_pooling_averages_the_rule_over_centre_days():
    cube = np.zeros((1, len(OFFSETS), 1))
    c = list(OFFSETS).index(0)
    cube[0, c - 7 : c + 1, 0] = 9.0  # white Dec 18-25, green Dec 26 - Jan 1
    f = white_fraction(cube, "christmas_day", threshold=2.5, pool_days=7)
    assert f[0, 0] == pytest.approx(8 / 15)


def test_missing_days_are_skipped_and_all_missing_is_nan():
    cube = np.full((2, len(OFFSETS), 1), np.nan)
    c = list(OFFSETS).index(0)
    cube[0, c, 0] = 4.0
    f = white_fraction(cube, "christmas_day", threshold=2.5, pool_days=3)
    assert f[0, 0] == 1.0  # only Dec 25 present, and it is white
    assert np.isnan(f[1, 0])
    k, n = window_counts(f, np.array([2000, 2001]), 2000, 2001)
    assert (k[0], n[0]) == (1.0, 1)
