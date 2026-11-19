"""White-Christmas rules on hand-made (year, day, cell) arrays. -1 = nodata."""

import numpy as np
import pytest

from whitexmas.definitions import white

N = np.nan
# 6 years x 3 days (Dec 24, 25, 26) for one cell
CELL = np.array(
    [
        [0, 0, 0],  # green
        [5, 5, 5],  # white on all days
        [0, 2, 0],  # only Christmas Day
        [3, 0, 0],  # only Christmas Eve
        [1, 1, 0],  # exactly the threshold on 24 and 25
        [-1, 4, 4],  # nodata on the 24th
    ],
    dtype="int16",
)[:, :, None]


@pytest.mark.parametrize(
    "definition, expected",
    [
        ("christmas_day", [0, 1, 1, 0, 1, 1]),
        ("all_three_days", [0, 1, 0, 0, 0, N]),
        ("any_day", [0, 1, 1, 1, 1, N]),
    ],
)
def test_definitions_threshold_1cm(definition, expected):
    out = white(CELL, definition, threshold_cm=1)
    np.testing.assert_array_equal(out[:, 0], np.array(expected, dtype="float32"))


def test_threshold_is_a_parameter():
    out = white(CELL, "christmas_day", threshold_cm=3)
    np.testing.assert_array_equal(out[:, 0], [0, 1, 0, 0, 0, 1])


def test_ocean_cell_is_nan_not_zero():
    ocean = np.full((4, 3, 1), -1, dtype="int16")
    for d in ("christmas_day", "all_three_days", "any_day"):
        assert np.isnan(white(ocean, d)).all()


def test_unknown_definition():
    with pytest.raises(ValueError):
        white(CELL, "boxing_day")
