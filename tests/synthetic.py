"""Helpers that build a small synthetic snow cube on disk, shaped like the real one."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import zarr

from whitexmas.config import Config
from whitexmas.paths import DataPaths

YEARS = list(range(2000, 2020))


def small_config(**overrides) -> Config:
    raw = copy.deepcopy(Config.load().raw)
    raw["years"] = {"first": YEARS[0], "last": YEARS[-1]}
    raw["windows"] = {
        "full": True,
        "normals": [[2000, 2009], [2010, 2019]],
        "decades": True,
        "change": {"from": "2000_2009", "to": "2010_2019"},
    }
    raw.update(overrides)
    return Config(raw)


def write_cube(path: Path, cube: np.ndarray, glacier_fraction: np.ndarray, years=YEARS):
    """Write a cube store directly (bypassing NetCDF) with the ingest layout."""
    ny, nx = cube.shape[2:]
    root = zarr.open_group(str(path), mode="w")
    root.create_array(
        "snow_depth_cm",
        data=cube.astype("int16"),
        chunks=cube.shape,
        fill_value=-1,
        dimension_names=["year", "day", "lat", "lon"],
    )
    root.create_array(
        "glacier_fraction",
        data=glacier_fraction.astype("float32"),
        chunks=(ny, nx),
        dimension_names=["lat", "lon"],
    )
    root.create_array(
        "land", data=(cube != -1).any(axis=(0, 1)), chunks=(ny, nx), dimension_names=["lat", "lon"]
    )
    root.create_array("year", data=np.array(years, "int16"), dimension_names=["year"])
    lat = np.round(90 - 0.1 * np.arange(ny), 6)
    lon = np.round(-180 + 0.1 * np.arange(nx), 6)
    root.create_array("lat", data=lat, dimension_names=["lat"])
    root.create_array("lon", data=lon, dimension_names=["lon"])
    root.create_array("day", data=np.array([24, 25, 26], "int8"), dimension_names=["day"])
    root.attrs["input_fingerprint"] = "synthetic"
    zarr.consolidate_metadata(str(path))


def synthetic_cells(n_years: int = len(YEARS)):
    """A 2x3 grid of cells with known behaviour, cube shape (year, 3, 2, 3).

    (0,0) ocean | (0,1) always white glacier | (0,2) always white, no glacier mask
    (1,0) white in the first half only | (1,1) green always | (1,2) white every other year
    """
    cube = np.zeros((n_years, 3, 2, 3), dtype="int16")
    cube[:, :, 0, 0] = -1
    cube[:, :, 0, 1] = 3000
    cube[:, :, 0, 2] = 10
    cube[: n_years // 2, :, 1, 0] = 5
    cube[::2, :, 1, 2] = 2
    glacier = np.array([[np.nan, 1.0, 0.0], [0.0, 0.0, 0.0]], dtype="float32")
    return cube, glacier


def make_paths(tmp_path: Path) -> DataPaths:
    p = DataPaths(tmp_path)
    p.interim.mkdir(parents=True, exist_ok=True)
    return p
