"""wx-proj-v1 point tiles and the manifest fragment (web data contract)."""

import gzip
import json
import struct

import numpy as np

from whitexmas.projections.export import (
    decode_proj_tile,
    encode_proj_tile,
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
    chg = next(ly for ly in layers if ly["id"] == "projchange__christmas_day__gwl2.0")
    assert chg["kind"] == "projection_change" and chg["colormap"] == "change"
    assert chg["hatch_disagreement"] is True and "from" not in chg
    block = projections_block(["A", "B"], [1.5, 2.0, 3.0], "1996_2025")
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


def _tiny_ensemble(root, placeholder: bool):
    import xarray as xr

    from whitexmas.projections.settings import ProjPaths

    pp = ProjPaths(root)
    pp.ensemble.parent.mkdir(parents=True, exist_ok=True)
    xr.Dataset(
        {"p50": (("definition", "gwl", "lat", "lon"), np.zeros((1, 1, 2, 2), "float32"))},
        coords={"definition": ["christmas_day"], "gwl": [2.0], "lat": [0.0, 1.0], "lon": [0, 1]},
        attrs={"placeholder": placeholder, "models": "[]", "settings": "{}"},
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
    with pytest.raises(RuntimeError, match="bundled"):
        export_projections(paths, bundled, cogs=False, allow_placeholder=True)
    assert not bundled.exists()


def test_manifest_fragment_is_none_unless_a_real_export_exists(tmp_path):
    from whitexmas.paths import DataPaths
    from whitexmas.projections.export import manifest_fragment
    from whitexmas.projections.settings import ProjPaths

    paths = DataPaths(tmp_path)
    assert manifest_fragment(paths) is None
    prod = ProjPaths(tmp_path).products
    prod.mkdir(parents=True)
    frag = {"layers": [{"id": "proj__christmas_day__gwl2.0"}], "projections": {"available": True}}
    (prod / "manifest_fragment.json").write_text(json.dumps({**frag, "placeholder": True}))
    assert manifest_fragment(paths) is None
    (prod / "manifest_fragment.json").write_text(json.dumps({**frag, "placeholder": False}))
    assert manifest_fragment(paths) == frag
