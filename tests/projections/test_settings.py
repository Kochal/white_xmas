"""Projection paths: a named variant writes next to the default folders, never into them."""

from pathlib import Path

import pytest

from whitexmas.paths import DataPaths
from whitexmas.projections.settings import VARIANT_ENV, ProjPaths


def test_default_paths(tmp_path, monkeypatch):
    monkeypatch.delenv(VARIANT_ENV, raising=False)
    pp = ProjPaths.from_data(DataPaths(tmp_path))
    assert pp.interim == tmp_path / "interim" / "projections"
    assert pp.staging == tmp_path / "products" / "projections" / "web"


def test_variant_from_env_keeps_inputs_shared(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIANT_ENV, "v2")
    pp = ProjPaths.from_data(DataPaths(tmp_path))
    assert pp.models == tmp_path / "interim" / "projections_v2" / "models"
    assert pp.ensemble == tmp_path / "interim" / "projections_v2" / "projections.zarr"
    assert pp.validation == tmp_path / "interim" / "projections_v2" / "validation"
    assert pp.staging == tmp_path / "products" / "projections_v2" / "web"
    assert pp.cmip6 == tmp_path / "cmip6"  # downloads are shared


@pytest.mark.parametrize("bad", ["../x", "a/b", "v 2", "-x"])
def test_variant_must_be_a_plain_name(bad):
    with pytest.raises(ValueError):
        ProjPaths(Path("."), bad)


def test_variant_option_sets_the_env_var_for_the_subcommand(tmp_path, monkeypatch):
    import os

    from whitexmas.projections.cli import _main

    # setenv first so that monkeypatch restores the original state (unset) afterwards: the
    # callback writes os.environ directly and must not leak into other tests
    monkeypatch.setenv(VARIANT_ENV, "")
    _main(variant=" v2 ")
    assert os.environ[VARIANT_ENV] == "v2"
    assert (
        ProjPaths.from_data(DataPaths(tmp_path)).products
        == tmp_path / "products" / "projections_v2"
    )
    _main(variant=None)  # no option: leaves the environment as it is
    assert os.environ[VARIANT_ENV] == "v2"
    with pytest.raises(ValueError):
        _main(variant="../escape")
    assert os.environ[VARIANT_ENV] == "v2"
