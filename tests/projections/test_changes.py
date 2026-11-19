"""The shared change computation (used by production, the hindcast and the sensitivity run)."""

import numpy as np
import pytest

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
    land, pct, uses_era5 = model_land(
        ProjPaths(tmp_path), "X", lat, lon, n_base, ProjSettings(), era5_land
    )
    np.testing.assert_array_equal(land, [[True, False], [False, False]])
    assert pct[0, 0] > 99
    assert uses_era5


def _write_attrs(path, s: ProjSettings, **extra):
    import xarray as xr

    attrs = {f"setting_{k}": str(v) for k, v in s.as_attrs().items()}
    xr.Dataset(attrs={**attrs, **extra}).to_netcdf(path)


def test_per_model_file_is_reused_only_with_same_estimator_and_land_mask_source(tmp_path):
    from whitexmas.projections.changes import ESTIMATOR
    from whitexmas.projections.cli import _reuse_file

    s = ProjSettings()
    f = tmp_path / "X.nc"
    _write_attrs(f, s, estimator=ESTIMATOR, era5_land_source="indicators")
    assert _reuse_file(f, s, "indicators") == "reuse"
    _write_attrs(f, s, estimator=ESTIMATOR, era5_land_source="placeholder-legacy-geotiff")
    # built while only the placeholder baseline existed: its fallback land mask is wrong
    assert _reuse_file(f, s, "indicators") == "recompute"
    _write_attrs(f, s, era5_land_source="indicators")  # before the common-n estimator
    assert _reuse_file(f, s, "indicators") == "recompute"
    _write_attrs(f, s, estimator=ESTIMATOR)  # land mask source not recorded
    assert _reuse_file(f, s, "indicators") == "recompute"


def test_models_with_sftlf_ignore_the_era5_land_source(tmp_path):
    from whitexmas.projections.changes import ESTIMATOR, SFTLF
    from whitexmas.projections.cli import _reuse_file

    s = ProjSettings()
    f = tmp_path / "X.nc"
    _write_attrs(f, s, estimator=ESTIMATOR, era5_land_source=SFTLF)
    for now in ("indicators", "placeholder-legacy-geotiff", "none"):
        assert _reuse_file(f, s, now) == "reuse"
    _write_attrs(f, s, estimator="old", era5_land_source=SFTLF)
    assert _reuse_file(f, s, "none") == "recompute"  # its own land fraction: safe to rebuild


def test_a_land_mask_from_the_indicators_is_never_replaced_by_a_worse_one(tmp_path):
    from whitexmas.projections.changes import ESTIMATOR
    from whitexmas.projections.cli import _reuse_file

    s = ProjSettings()
    f = tmp_path / "X.nc"
    _write_attrs(f, s, estimator=ESTIMATOR, era5_land_source="indicators")
    assert _reuse_file(f, s, "placeholder-legacy-geotiff") == "keep"
    assert _reuse_file(f, s, "none") == "keep"
    # even when the estimator changed: keep it (the ensemble then refuses it, loudly)
    _write_attrs(f, s, estimator="old", era5_land_source="indicators")
    assert _reuse_file(f, s, "none") == "keep"
    # a placeholder mask may be replaced by the real one, never the other way round
    _write_attrs(f, s, estimator=ESTIMATOR, era5_land_source="placeholder-legacy-geotiff")
    assert _reuse_file(f, s, "none") == "keep"


def test_era5_land_raises_when_the_indicators_exist_but_cannot_be_read(tmp_path):
    from tests.synthetic import make_paths
    from whitexmas.projections.cli import _era5_land

    paths = make_paths(tmp_path)
    paths.indicators.mkdir(parents=True)  # exists, but is no readable zarr store
    with pytest.raises(RuntimeError, match="could not be read"):
        _era5_land(paths)


def test_era5_land_without_indicators_falls_back(tmp_path, monkeypatch):
    from tests.synthetic import make_paths
    from whitexmas.projections import baseline
    from whitexmas.projections.cli import _era5_land

    paths = make_paths(tmp_path)
    assert not paths.indicators.exists()
    # no placeholder GeoTIFF either: no mask, source "none"
    monkeypatch.setattr(baseline, "LEGACY_TIF", tmp_path / "missing.tif")
    land, source = _era5_land(paths)
    assert land is None and source == "none"
    # with the placeholder: its mask, labelled as the placeholder
    fake = baseline.Baseline(
        np.zeros((2, 2), "float32"), np.zeros((2, 2), "int16"), np.ones((2, 2), bool),
        np.zeros((2, 2), bool), "placeholder-legacy-geotiff", "2015_2024",
    )  # fmt: skip
    monkeypatch.setattr(baseline, "_from_legacy", lambda tif: fake)
    land, source = _era5_land(paths)
    assert land.all() and source == "placeholder-legacy-geotiff"
