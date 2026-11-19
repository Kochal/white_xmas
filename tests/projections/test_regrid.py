"""Bilinear regridding from a coarse model grid to a fine target grid."""

import numpy as np
import pytest

from whitexmas.projections.regrid import bilinear, fill_nearest


def test_linear_field_is_reproduced_exactly_inside_the_source_grid():
    src_lat = np.array([60.0, 50.0, 40.0])  # north-up, like many model grids reversed
    src_lon = np.array([0.0, 10.0, 20.0, 30.0])
    field = 2.0 * src_lat[:, None] + 0.5 * src_lon[None, :]
    dst_lat = np.array([55.0, 42.5])
    dst_lon = np.array([5.0, 12.5, 25.0])
    out = bilinear(field, src_lat, src_lon, dst_lat, dst_lon, periodic=False)
    expected = 2.0 * dst_lat[:, None] + 0.5 * dst_lon[None, :]
    np.testing.assert_allclose(out, expected)


def test_matches_hand_computed_cell_centre():
    src_lat = np.array([0.0, 1.0])
    src_lon = np.array([0.0, 1.0])
    field = np.array([[0.0, 1.0], [2.0, 4.0]])  # lat rows, lon cols
    out = bilinear(field, src_lat, src_lon, np.array([0.5]), np.array([0.25]), periodic=False)
    # lon 0.25 along row 0: 0.25; along row 1: 2.5; lat 0.5: mean = 1.375
    assert out[0, 0] == pytest.approx(1.375)


def test_periodic_longitude_wraps_across_the_dateline():
    # model grid 0..350 E; target -180..180 like ERA5-Land
    src_lon = np.arange(0.0, 360.0, 10.0)
    src_lat = np.array([10.0, 0.0])
    field = np.tile(np.where(src_lon == 350.0, 1.0, 0.0), (2, 1))
    field[:, 0] = 3.0  # lon 0
    out = bilinear(field, src_lat, src_lon, np.array([5.0]), np.array([-5.0, 355.0, -180.0]))
    # -5 E == 355 E, halfway between 350 (1.0) and 360=0 (3.0)
    assert out[0, 0] == pytest.approx(2.0)
    assert out[0, 1] == pytest.approx(2.0)
    assert out[0, 2] == pytest.approx(0.0)


def test_targets_beyond_the_outermost_latitude_take_the_edge_value():
    src_lat = np.array([-80.0, 80.0])
    src_lon = np.array([0.0, 180.0])
    field = np.array([[1.0, 1.0], [5.0, 5.0]])
    out = bilinear(field, src_lat, src_lon, np.array([90.0, -90.0]), np.array([90.0]))
    np.testing.assert_allclose(out[:, 0], [5.0, 1.0])


def test_fill_nearest_replaces_nan_with_the_nearest_valid_cell():
    f = np.array([[1.0, np.nan, np.nan], [np.nan, np.nan, 7.0]])
    out = fill_nearest(f)
    assert out[0, 1] == 1.0
    assert out[1, 1] in (1.0, 7.0)
    assert out[0, 2] == 7.0
    assert not np.isnan(out).any()
    assert np.isnan(fill_nearest(np.full((2, 2), np.nan))).all()
