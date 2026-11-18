from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from whitexmas.ingest import NODATA, build_cube, open_cube, to_cm

NY, NX = 6, 8


def test_to_cm_floors_and_keeps_nodata():
    m = np.array([np.nan, -1e-23, 0.0099, 0.01, 0.03, 0.0151, 33.333], dtype="float32")
    assert to_cm(m).tolist() == [NODATA, 0, 0, 1, 3, 1, 3333]


def _snow_file(path: Path, year: int, field: np.ndarray, south_up=False, lon360=False):
    lat = 90.0 - 0.1 * np.arange(NY)
    lon = -180.0 + 0.1 * np.arange(NX)
    data = np.stack([field + d * 0.01 for d in range(3)]).astype("f4")
    if south_up:
        lat, data = lat[::-1], data[:, ::-1]
    if lon360:
        lon = lon % 360
    ds = xr.Dataset(
        {"sde": (("valid_time", "latitude", "longitude"), data)},
        coords={
            "valid_time": pd.date_range(f"{year}-12-24", periods=3),
            "latitude": lat,
            "longitude": lon,
        },
    )
    ds.to_netcdf(path)


def _static(path: Path, var: str, field: np.ndarray):
    # static fields come on a 0..360 grid
    lat = 90.0 - 0.1 * np.arange(NY)
    lon = (-180.0 + 0.1 * np.arange(NX)) % 360
    order = np.argsort(lon)
    xr.Dataset(
        {var: (("time", "latitude", "longitude"), field[None, :, order].astype("f4"))},
        coords={"time": [0], "latitude": lat, "longitude": lon[order]},
    ).to_netcdf(path)


def test_build_cube_orients_rolls_and_masks(tmp_path: Path):
    field = np.full((NY, NX), 0.05, "f4")  # 5 cm
    field[0, 0] = 0.0  # north-west corner bare
    field[:, -1] = np.nan  # an ocean column (east edge)
    field[5, 3] = 2.0  # 200 cm, south row
    files = {}
    for i, y in enumerate([2000, 2001]):
        p = tmp_path / f"sd_{y}.nc"
        _snow_file(p, y, field, south_up=(i == 1), lon360=(i == 1))
        files[y] = [p]
    static = tmp_path / "static"
    static.mkdir()
    glm = np.zeros((NY, NX))
    glm[5, 3] = 1.0
    _static(static / "glacier_mask.nc", "glm", glm)
    _static(static / "land_sea_mask.nc", "lsm", np.where(np.isnan(field), 0.0, 1.0))
    _static(static / "geopotential.nc", "z", np.full((NY, NX), 9.80665 * 1000))

    out = build_cube([2000, 2001], files, static, tmp_path / "cube.zarr", band=4, chunk=2)
    ds = open_cube(out)
    cube = ds["snow_depth_cm"].values
    assert cube.shape == (2, 3, NY, NX)
    assert ds["lat"].values[0] == 90.0 and ds["lon"].values[0] == -180.0
    for yi in range(2):
        np.testing.assert_array_equal(cube[yi, :, 0, 0], [0, 1, 2])
        np.testing.assert_array_equal(cube[yi, :, 1, 1], [5, 6, 7])
        np.testing.assert_array_equal(cube[yi, :, 5, 3], [200, 201, 202])
        assert (cube[yi, :, :, -1] == NODATA).all()
    assert ds["land"].values[:, :-1].all() and not ds["land"].values[:, -1].any()
    assert ds["glacier_fraction"].values[5, 3] == 1.0
    assert ds["glacier_fraction"].values[0, 0] == 0.0
    assert ds["land_sea_mask"].values[0, -1] == 0.0
    np.testing.assert_allclose(ds["orography_m"].values, 1000.0, rtol=1e-6)
