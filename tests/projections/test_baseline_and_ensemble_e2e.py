"""Real-baseline reader on the pipeline's synthetic indicators, and build_ensemble end to end."""

import json

import numpy as np
import pytest
import xarray as xr
import zarr

from tests.synthetic import make_paths, small_config, synthetic_cells, write_cube
from whitexmas.indicators import compute_all
from whitexmas.projections.baseline import NX, NY, _from_indicators, load_baseline
from whitexmas.projections.changes import ESTIMATOR
from whitexmas.projections.settings import ProjPaths, ProjSettings


def test_from_indicators_reads_the_pipeline_layout(tmp_path):
    cfg = small_config()
    paths = make_paths(tmp_path)
    cube, glacier = synthetic_cells()
    write_cube(paths.cube, cube, glacier)
    compute_all(cfg, paths)
    b = _from_indicators(paths.indicators, "christmas_day", "2000_2009")
    assert not b.placeholder and b.window == "2000_2009"
    assert np.isnan(b.p[0, 0]) and not b.land[0, 0]  # ocean
    assert b.p[1, 0] == 100 and b.p[1, 1] == 0 and b.p[1, 2] == 50
    assert b.n[1, 1] == 10
    assert b.glacier[0, 1] and not b.glacier[0, 2]
    b2 = load_baseline(paths, "christmas_day", "2010_2019")  # picks indicators over placeholder
    assert b2.source == "indicators" and b2.p[1, 0] == 0


def _write_indicators(path, p_cells: dict):
    """A full-size indicators store with one definition and one window."""
    root = zarr.open_group(str(path), mode="w")
    p = np.full((1, 1, NY, NX), np.nan, "float32")
    for (j, i), v in p_cells.items():
        p[0, 0, j, i] = v
    root.create_array("probability", data=p, chunks=(1, 1, 601, 600))
    root.create_array("n_valid", data=np.where(np.isfinite(p), 30, 0).astype("int16"),
                      chunks=(1, 1, 601, 600))  # fmt: skip
    root.create_array("land", data=np.isfinite(p[0, 0]), chunks=(601, 600))
    root.create_array("glacier", data=np.zeros((NY, NX), bool), chunks=(601, 600))
    root.attrs.update({"definitions": json.dumps(["christmas_day"]),
                       "windows": json.dumps([{"id": "1996_2025"}])})  # fmt: skip


def _write_model(
    pp: ProjPaths, name: str, delta: float, estimator: str = ESTIMATOR, land_source="sftlf"
):
    lat = np.linspace(-80, 80, 9)
    lon = np.arange(0.0, 360.0, 30.0)
    d = np.full((3, 1, len(lat), len(lon)), delta, "float32")
    pp.models.mkdir(parents=True, exist_ok=True)
    xr.Dataset(
        {"delta": (("gwl", "definition", "lat", "lon"), d)},
        coords={"gwl": [1.5, 2.0, 3.0], "definition": ["christmas_day"], "lat": lat, "lon": lon},
        attrs={
            **({"estimator": estimator} if estimator else {}),
            **({"era5_land_source": land_source} if land_source else {}),
        },
    ).to_netcdf(pp.models / f"{name}.nc")


def test_build_ensemble_end_to_end(tmp_path):
    from whitexmas.projections.ensemble import build_ensemble

    paths = make_paths(tmp_path)
    cells = {(400, 1900): 50.0, (500, 2000): 100.0, (600, 100): 0.0}
    _write_indicators(paths.indicators, cells)
    pp = ProjPaths.from_data(paths)
    for name, d in (("A", -1.0), ("B", -1.0), ("C", 0.5)):
        _write_model(pp, name, d)
    build_ensemble(paths, ProjSettings(definitions=("christmas_day",)))
    ds = xr.open_zarr(pp.ensemble)
    assert not ds.attrs["placeholder"] and json.loads(ds.attrs["models"]) == ["A", "B", "C"]
    assert json.loads(ds.attrs["settings"])["estimator"] == ESTIMATOR
    e = ds.sel(definition="christmas_day", gwl=2.0)
    # 50 % with deltas (-1, -1, +0.5): median model is -1 -> 26.12 %
    assert float(e.p50[400, 1900]) == pytest.approx(26.12, abs=0.01)
    assert float(e.change[400, 1900]) == pytest.approx(26.12 - 50, abs=0.01)
    assert bool(e.agree[400, 1900])  # 2 of 3 decrease
    assert int(e.n_models[400, 1900]) == 3
    # two models tie at the low end, so p10 equals the median; the +0.5 model lifts p90
    assert float(e.p10[400, 1900]) == pytest.approx(float(e.p50[400, 1900]))
    assert float(e.p90[400, 1900]) > 50.0
    assert np.isnan(float(e.p50[0, 0]))  # no baseline -> nodata
    assert float(e.p50[600, 100]) == 0.0  # 0 % cannot decline further


def test_build_ensemble_refuses_a_placeholder_selection(tmp_path):
    from whitexmas.projections.ensemble import build_ensemble
    from whitexmas.projections.validation import UntrustedSelection

    paths = make_paths(tmp_path)
    _write_indicators(paths.indicators, {(400, 1900): 50.0})
    pp = ProjPaths.from_data(paths)
    _write_model(pp, "A", -1.0)
    pp.validation.mkdir(parents=True)
    (pp.validation / "selection.json").write_text(json.dumps(
        {"reference": "placeholder-legacy-geotiff 2015_2024", "placeholder": True,
         "dropped": {}}))  # fmt: skip
    with pytest.raises(UntrustedSelection):
        build_ensemble(paths, ProjSettings(definitions=("christmas_day",)))


@pytest.mark.parametrize("estimator", ["", "jeffreys-per-window"])
def test_build_ensemble_refuses_changes_from_another_estimator(tmp_path, estimator):
    # files from before the common-n fix carry a spurious change in never/always-white cells
    from whitexmas.projections.ensemble import build_ensemble

    paths = make_paths(tmp_path)
    _write_indicators(paths.indicators, {(400, 1900): 50.0})
    pp = ProjPaths.from_data(paths)
    _write_model(pp, "A", -1.0)
    _write_model(pp, "B", -1.0, estimator=estimator)
    with pytest.raises(ValueError, match="re-run"):
        build_ensemble(paths, ProjSettings(definitions=("christmas_day",)))


@pytest.mark.parametrize("land_source", ["placeholder-legacy-geotiff", "none", None])
def test_build_ensemble_refuses_land_masks_not_from_sftlf_or_the_indicators(tmp_path, land_source):
    from whitexmas.projections.ensemble import build_ensemble

    paths = make_paths(tmp_path)
    _write_indicators(paths.indicators, {(400, 1900): 50.0})
    pp = ProjPaths.from_data(paths)
    _write_model(pp, "A", -1.0)
    _write_model(pp, "B", -1.0, land_source="indicators")  # fine: real ERA5-Land mask
    _write_model(pp, "C", -1.0, land_source=land_source)
    with pytest.raises(ValueError, match="land masks"):
        build_ensemble(paths, ProjSettings(definitions=("christmas_day",)))
