"""The shared change computation (used by production, the hindcast and the sensitivity run)."""

import numpy as np

from whitexmas.projections.changes import masked_delta, model_land
from whitexmas.projections.settings import ProjPaths, ProjSettings


def test_masked_delta_is_nan_off_land_and_without_valid_years():
    kb = np.array([[10.0, 10.0, 10.0, 0.0]])
    kf = np.array([[5.0, 5.0, 5.0, 0.0]])
    nb = np.array([[20, 20, 0, 20]])
    nf = np.array([[20, 20, 20, 20]])
    land = np.array([True, False, True, True])
    d = masked_delta(kb, nb, kf, nf, land)
    assert d[0, 0] < 0
    assert np.isnan(d[0, 1])  # ocean (e.g. snow on sea ice) never enters
    assert np.isnan(d[0, 2])  # no baseline year
    assert d[0, 3] == 0.0  # snow-free in both windows: no change


def test_model_land_uses_the_land_fraction_not_just_data_presence(tmp_path):
    # no sftlf on disk -> land fraction from the ERA5-Land mask aggregated to the model grid
    era5_land = np.zeros((1801, 3600), bool)
    era5_land[:900, :1800] = True  # north-west quarter of the globe is land
    lat = np.array([45.0, -45.0])
    lon = np.array([270.0, 90.0])  # 270 E = 90 W (land), 90 E (ocean)
    n_base = np.full((2, 2), 20)  # the model reports snw everywhere, ocean included
    land, pct = model_land(ProjPaths(tmp_path), "X", lat, lon, n_base, ProjSettings(), era5_land)
    np.testing.assert_array_equal(land, [[True, False], [False, False]])
    assert pct[0, 0] > 99
