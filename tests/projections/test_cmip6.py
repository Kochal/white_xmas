"""Reading model subsets across the historical / scenario seam."""

import cftime
import numpy as np
import xarray as xr

from whitexmas.projections.cmip6 import load_window
from whitexmas.projections.frequency import season_cube


def _write(root, model, exp, first, last):
    """A subset file with 11 Dec - 8 Jan days, as cmip6_download.py writes them."""
    t = []
    for y in range(first - 1, last + 1):
        t += [cftime.datetime(y, 12, d, 12, calendar="noleap") for d in range(11, 32)]
        t += [cftime.datetime(y + 1, 1, d, 12, calendar="noleap") for d in range(1, 9)]
    t = [x for x in t if first <= x.year <= last]
    v = np.array([1000 * x.year + 10 * x.month + x.day / 100 for x in t], "float32")
    d = root / "snw" / model
    d.mkdir(parents=True, exist_ok=True)
    name = f"snw_day_{model}_{exp}_r1i1p1f1_gn_{first}0101-{last}1231_xmas.nc"
    xr.Dataset(
        {"snw": (("time", "lat", "lon"), v[:, None, None])},
        coords={"time": t, "lat": [50.0], "lon": [10.0]},
    ).to_netcdf(d / name)


def test_season_2014_keeps_its_january_2015_days(tmp_path):
    _write(tmp_path, "M", "historical", 2010, 2014)
    _write(tmp_path, "M", "ssp245", 2015, 2020)
    f = load_window(tmp_path, "M", "historical", 2013, 2014)
    years, cube = season_cube(f.values, f.times)
    assert list(years) == [2013, 2014]
    assert np.isfinite(cube[:, :, 0, 0]).all()  # all 29 days in both seasons
    jan = [t for t in f.times if t.year == 2015]
    assert len(jan) == 8 and all(t.month == 1 for t in jan)


def test_window_across_the_seam_has_no_duplicates(tmp_path):
    _write(tmp_path, "M", "historical", 2010, 2014)
    _write(tmp_path, "M", "ssp245", 2015, 2020)
    f = load_window(tmp_path, "M", "ssp245", 2013, 2016)
    assert len(f.times) == len(set(f.times)) == 4 * 29
    # Dec days up to 2014 from historical, everything from 2015 on from ssp245
    assert f.times[0] == cftime.datetime(2013, 12, 11, 12, calendar="noleap")
    assert f.times[-1] == cftime.datetime(2017, 1, 8, 12, calendar="noleap")
