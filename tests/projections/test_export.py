"""wx-proj-v1 point tiles and the manifest fragment (web data contract)."""

import gzip
import json
import struct

import numpy as np
import pytest

from whitexmas.projections.changes import ESTIMATOR
from whitexmas.projections.export import (
    decode_proj_tile,
    encode_proj_tile,
    manifest_fragment,
    patch_manifest,
    plan_layers,
    projections_block,
    write_proj_tiles,
)


def test_header_layout_matches_the_contract():
    stats = np.full((50, 50, 3, 3), np.nan, dtype="float32")
    stats[0, 0, 1] = [10.4, 20.6, 30.0]
    agree = np.zeros((3, 50, 50), bool)
    agree[1, 0, 1] = True
    raw = gzip.decompress(encode_proj_tile(stats, agree))
    magic, nl, ns, nx, ny = struct.unpack_from("<4sBBHH", raw, 0)
    assert (magic, nl, ns, nx, ny) == (b"WXQ1", 3, 3, 50, 50)
    assert raw[10:16] == bytes(6)
    body = np.frombuffer(raw, "uint8", 50 * 50 * 3 * 3, 16).reshape(50, 50, 3, 3)
    assert list(body[0, 0, 1]) == [10, 21, 30]
    assert body[0, 0, 0, 0] == 255 and body[49, 49, 2, 2] == 255
    # level 1 mask starts after one 313-byte mask; cell (0, 1) is bit 1 of its first byte
    nbits = (50 * 50 + 7) // 8
    assert raw[16 + 50 * 50 * 9 + nbits] == 0b10
    assert len(raw) == 16 + 50 * 50 * 9 + 3 * nbits


def test_round_trip():
    rng = np.random.default_rng(0)
    stats = rng.uniform(0, 100, (50, 50, 3, 3)).astype("float32")
    stats[5, 5] = np.nan
    agree = rng.random((3, 50, 50)) > 0.5
    t = decode_proj_tile(encode_proj_tile(stats, agree))
    np.testing.assert_array_equal(t.agree, agree)
    assert (t.stats[5, 5] == 255).all()
    np.testing.assert_array_equal(t.stats[0, 0], np.round(stats[0, 0]).astype("uint8"))


def test_tiles_only_where_there_is_data_and_southern_row_is_padded(tmp_path):
    ny, nx = 1801, 3600
    p = np.full((3, ny, nx), np.nan, dtype="float32")
    p[:, 1800, 0] = 40.0  # southernmost row: tile ty = 36
    p[:, 0, 3599] = 60.0  # tile tx = 71, ty = 0
    agree = np.ones((3, ny, nx), bool)
    st = write_proj_tiles(tmp_path, p - 10, p, p + 10, agree)
    assert st["tiles"] == 2
    index = json.loads((tmp_path / "index.json").read_text())
    assert sorted(index["tiles"]) == ["0_36", "71_0"]
    t = decode_proj_tile((tmp_path / "0_36.bin.gz").read_bytes())
    assert t.stats.shape == (50, 50, 3, 3)
    assert list(t.stats[0, 0, 0]) == [30, 40, 50]
    assert (t.stats[1:] == 255).all()
    assert t.agree[:, 0, 0].all() and not t.agree[:, 1:].any()


def test_layer_ids_and_block_follow_the_contract(tmp_path):
    layers = plan_layers(["christmas_day"], [1.5, 2.0, 3.0])
    ids = [ly["id"] for ly in layers]
    assert "proj__christmas_day__gwl2.0" in ids and "projchange__christmas_day__gwl1.5" in ids
    proj = next(ly for ly in layers if ly["id"] == "proj__christmas_day__gwl2.0")
    assert proj["kind"] == "projection" and proj["warming_level"] == 2.0
    assert proj["colormap"] == "probability" and proj["url"].endswith("gwl2.0.pmtiles")
    assert all(ly["threshold"] == "calibrated" for ly in layers)  # contract v1.5
    chg = next(ly for ly in layers if ly["id"] == "projchange__christmas_day__gwl2.0")
    assert chg["kind"] == "projection_change" and chg["colormap"] == "change"
    assert chg["hatch_disagreement"] is True and "from" not in chg
    levels = [{"gwl": g, "label": f"+{g} °C", "approx": "x"} for g in (1.5, 2.0, 3.0)]
    block = projections_block(["A", "B"], levels, "1996_2025")
    assert block["available"] is True
    assert [w["gwl"] for w in block["warming_levels"]] == [1.5, 2.0, 3.0]
    assert block["points"] == {
        "tile_deg": 5,
        "format": "wx-proj-v1",
        "path": "proj/{tx}_{ty}.bin.gz",
    }
    m = tmp_path / "manifest.json"
    m.write_text(
        json.dumps(
            {
                "layers": [{"id": "prob__x"}, {"id": ids[0], "old": 1}],
                "projections": {"available": False},
            }
        )
    )
    patch_manifest(m, {"layers": layers, "projections": block})
    out = json.loads(m.read_text())
    assert [ly["id"] for ly in out["layers"]] == ["prob__x", *ids]
    assert out["projections"]["available"] is True


def _tiny_ensemble(root, placeholder: bool, threshold=None):
    import xarray as xr

    from whitexmas.projections.settings import ProjPaths

    pp = ProjPaths(root)
    pp.ensemble.parent.mkdir(parents=True, exist_ok=True)
    xr.Dataset(
        {"p50": (("definition", "gwl", "lat", "lon"), np.zeros((1, 1, 2, 2), "float32"))},
        coords={"definition": ["christmas_day"], "gwl": [2.0], "lat": [0.0, 1.0], "lon": [0, 1]},
        attrs={
            "placeholder": placeholder,
            "models": "[]",
            "settings": "{}",
            "baseline_threshold": json.dumps(threshold),
        },  # fmt: skip
    ).to_zarr(pp.ensemble, mode="w")
    return pp


def test_placeholder_export_is_refused_and_never_written_to_the_bundled_folder(tmp_path):
    import pytest

    from whitexmas.paths import DataPaths
    from whitexmas.projections.export import export_projections

    _tiny_ensemble(tmp_path, placeholder=True)
    paths = DataPaths(tmp_path)
    with pytest.raises(RuntimeError, match="PLACEHOLDER"):
        export_projections(paths, tmp_path / "preview", cogs=False)
    bundled = tmp_path / "repo" / "web" / "static" / "data"
    with pytest.raises(RuntimeError, match="published bundle"):
        export_projections(paths, bundled, cogs=False, allow_placeholder=True)
    assert not bundled.exists()
    from whitexmas.projections.settings import ProjPaths

    for target in (None, ProjPaths(tmp_path).staging):  # the staging folder feeds the bundle
        with pytest.raises(RuntimeError, match="published bundle"):
            export_projections(paths, target, cogs=False, allow_placeholder=True)


def _staged(tmp_path, placeholder=False, n_tiles=2):
    """A fragment plus its staged files, as a real export leaves them."""
    from whitexmas.paths import DataPaths
    from whitexmas.projections.settings import ProjPaths

    pp = ProjPaths(tmp_path)
    layers = plan_layers(["christmas_day"], [2.0])
    (pp.staging / "tiles").mkdir(parents=True)
    (pp.staging / "proj").mkdir(parents=True)
    for ly in layers:
        (pp.staging / ly["url"]).write_bytes(ly["id"].encode() * 100)
    names = [f"{i}_7" for i in range(n_tiles)]
    for n in names:
        (pp.staging / "proj" / f"{n}.bin.gz").write_bytes(n.encode() * 50)
    (pp.staging / "proj" / "index.json").write_text(
        json.dumps({"format": "wx-proj-v1", "tile_deg": 5, "tiles": names}), encoding="utf-8"
    )
    frag = {"placeholder": placeholder, "estimator": ESTIMATOR, "layers": layers,
            "projections": {"available": True}}  # fmt: skip
    (pp.products / "manifest_fragment.json").write_text(json.dumps(frag), encoding="utf-8")
    return DataPaths(tmp_path), pp, layers, names


@pytest.mark.parametrize("estimator", [None, "jeffreys-per-window"])
def test_fragment_from_another_estimator_is_refused(tmp_path, estimator):
    # e.g. the data-2025.1 fragment (no estimator) staged into a data-2025.2 bundle
    paths, pp, *_ = _staged(tmp_path)
    f = pp.products / "manifest_fragment.json"
    frag = json.loads(f.read_text(encoding="utf-8"))
    frag.pop("estimator")
    if estimator:
        frag["estimator"] = estimator
    f.write_text(json.dumps(frag), encoding="utf-8")
    web = tmp_path / "web"
    with pytest.raises(RuntimeError, match="estimator"):
        manifest_fragment(paths, web)
    assert not web.exists()  # nothing staged


def test_fragment_staging_logs_the_source_folder(tmp_path, caplog):
    import logging

    paths, pp, *_ = _staged(tmp_path)
    with caplog.at_level(logging.INFO, logger="whitexmas.projections.export"):
        out = manifest_fragment(paths, tmp_path / "web")
    assert out is not None and "estimator" not in out  # the manifest gets layers + block only
    assert f"staged {pp.staging}" in caplog.text


def test_manifest_fragment_is_none_without_a_real_export(tmp_path):
    from whitexmas.paths import DataPaths
    from whitexmas.projections.export import manifest_fragment

    assert manifest_fragment(DataPaths(tmp_path), tmp_path / "web") is None


def test_fragment_stages_its_files_into_an_empty_web_out(tmp_path):
    from whitexmas.projections.export import manifest_fragment

    paths, pp, layers, names = _staged(tmp_path)
    web = tmp_path / "web"
    frag = manifest_fragment(paths, web)
    assert frag is not None and [ly["id"] for ly in frag["layers"]] == [ly["id"] for ly in layers]
    assert "placeholder" not in frag
    for ly in layers:
        assert (web / ly["url"]).read_bytes() == (pp.staging / ly["url"]).read_bytes()
    assert (web / "proj" / "index.json").is_file()
    assert sorted(p.name for p in (web / "proj").glob("*.bin.gz")) == [f"{n}.bin.gz" for n in names]


def test_fragment_staging_is_idempotent_and_replaces_stale_files(tmp_path):
    import os

    from whitexmas.projections.export import manifest_fragment

    paths, pp, layers, names = _staged(tmp_path)
    web = tmp_path / "web"
    assert manifest_fragment(paths, web) is not None
    tile = web / layers[0]["url"]
    os.utime(tile, (1_000_000_000, 1_000_000_000))  # identical files are not copied again
    (web / "proj" / "99_99.bin.gz").write_bytes(b"old tile from an earlier build")
    (web / layers[1]["url"]).write_bytes(b"older build")  # differs -> replaced
    assert manifest_fragment(paths, web) is not None
    assert tile.stat().st_mtime == 1_000_000_000
    assert (web / layers[1]["url"]).read_bytes() == (pp.staging / layers[1]["url"]).read_bytes()
    assert not (web / "proj" / "99_99.bin.gz").exists()


def test_missing_staged_files_give_none_and_copy_nothing(tmp_path):
    from whitexmas.projections.export import manifest_fragment

    paths, pp, layers, names = _staged(tmp_path)
    (pp.staging / "proj" / f"{names[1]}.bin.gz").unlink()
    web = tmp_path / "web"
    assert manifest_fragment(paths, web) is None
    assert not web.exists()
    paths, pp, layers, names = _staged(tmp_path / "b")
    (pp.staging / layers[0]["url"]).unlink()
    assert manifest_fragment(paths, tmp_path / "web_b") is None


def test_placeholder_fragment_is_never_staged(tmp_path):
    from whitexmas.projections.export import manifest_fragment

    paths, *_ = _staged(tmp_path, placeholder=True)
    web = tmp_path / "web"
    assert manifest_fragment(paths, web) is None
    assert not web.exists()


def test_fragment_without_web_out_keeps_the_old_behaviour_with_a_warning(tmp_path, caplog):
    from whitexmas.projections.export import manifest_fragment

    paths, pp, layers, _ = _staged(tmp_path)
    with caplog.at_level("WARNING"):
        frag = manifest_fragment(paths)
    assert frag is not None and len(frag["layers"]) == len(layers)
    assert "without web_out" in caplog.text


def test_warming_level_labels_come_from_the_models_used():
    from whitexmas.projections.export import NOT_REACHED, approx_label, warming_levels

    w = lambda exp, a: {"experiment": exp, "start": a, "end": a + 19}  # noqa: E731
    # centres 2029.5, 2035.5, 2045.5 -> median 2035.5 -> 2030s
    assert approx_label([w("ssp245", 2020), w("ssp245", 2026), w("ssp245", 2036)]) == (
        "around the 2030s"
    )
    # 1 of 3 models reaches it under SSP2-4.5: honest wording, no decade
    assert approx_label([w("ssp245", 2070), w("ssp585", 2050), w("ssp585", 2060)]) == NOT_REACHED
    assert approx_label([w("ssp245", 2060), w("ssp245", 2070), None, w("ssp585", 2050)]) == (
        "around the 2070s"
    )
    plan = {
        "A": {"windows": {"2.0": w("ssp245", 2036)}},
        "B": {"windows": {"2.0": w("ssp245", 2030)}},
        "C": {"windows": {}},
    }
    lv = warming_levels(["A", "B"], [2.0], plan)
    assert lv == [{"gwl": 2.0, "label": "+2 °C", "approx": "around the 2040s"}]


def test_patch_manifest_writes_utf8(tmp_path):
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"layers": [], "projections": {"available": False}}), encoding="utf-8")
    block = {"available": True, "warming_levels": [{"gwl": 2.0, "label": "+2 °C", "approx": "x"}]}
    patch_manifest(m, {"layers": [], "projections": block})
    out = json.loads(m.read_bytes().decode("utf-8"))  # strict UTF-8, whatever the OS locale
    assert out["projections"]["warming_levels"][0]["label"] == "+2 °C"


def test_projections_are_exported_for_the_default_threshold_only(tmp_path):
    import pytest

    from whitexmas.paths import DataPaths
    from whitexmas.projections.export import export_projections

    _tiny_ensemble(tmp_path, placeholder=False, threshold=["raw", 1])
    with pytest.raises(RuntimeError, match="default threshold"):
        export_projections(DataPaths(tmp_path), cogs=False)
