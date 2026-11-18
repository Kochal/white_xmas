import io

import numpy as np
from PIL import Image

from tests.synthetic import small_config
from whitexmas.export import plan_layers
from whitexmas.export.colors import COLORMAPS, GLACIER_FILL, GLACIER_LINE, apply_colormap
from whitexmas.export.tiles import LayerGrid, encode_webp, render_tile

RES = 10.0  # a coarse global grid: 19 x 36 cells
NY, NX = 19, 36


def test_colormap_endpoints_and_nan():
    rgba = apply_colormap(np.array([0, 100, 150, np.nan]), "probability")
    first, last = COLORMAPS["probability"]["stops"][0][1], COLORMAPS["probability"]["stops"][-1][1]
    assert "#{:02x}{:02x}{:02x}".format(*rgba[0, :3]) == first
    assert "#{:02x}{:02x}{:02x}".format(*rgba[1, :3]) == last
    assert (rgba[2] == rgba[1]).all()  # clamped
    assert rgba[3, 3] == 0  # NaN transparent


def test_colormaps_are_symmetric_where_diverging():
    for name in ("change", "trend"):
        stops = COLORMAPS[name]["stops"]
        assert stops[len(stops) // 2][0] == 0
        assert stops[0][0] == -stops[-1][0]


def _grid(values, **kw):
    return LayerGrid.build(values.astype("float32"), "probability", **kw)


def test_ocean_tile_is_skipped_and_land_coloured():
    v = np.full((NY, NX), np.nan)
    assert render_tile(_grid(v), 4, 3, 3, res=RES) is None
    v[:] = 100.0
    img = render_tile(_grid(v), 4, 3, 3, res=RES)
    expected = apply_colormap(np.array([100.0]), "probability")[0]
    assert (img == expected).all()


def test_low_zoom_averages_alpha_at_coast():
    v = np.full((NY, NX), np.nan)
    v[:, : NX // 2] = 50.0  # western hemisphere is land
    img = render_tile(_grid(v), 0, 0, 0, res=RES)
    assert img[128, 10, 3] == 255 and img[128, 245, 3] == 0


def test_glacier_cells_are_hatched_grey():
    v = np.full((NY, NX), 100.0)
    glac = np.ones((NY, NX), bool)
    img = render_tile(_grid(v, glacier=glac), 5, 10, 10, res=RES)
    colours = {tuple(c) for c in img[..., :3].reshape(-1, 3)}
    assert colours == {GLACIER_FILL, GLACIER_LINE}


def test_insignificant_trend_hatch_darkens_lines_only():
    v = np.full((NY, NX), 5.0)
    hatch = np.ones((NY, NX), bool)
    g = LayerGrid.build(v.astype("float32"), "trend", hatch=hatch)
    img = render_tile(g, 5, 10, 10, res=RES)
    base = apply_colormap(np.array([5.0]), "trend")[0]
    plain = (img == base).all(axis=-1)
    assert 0.4 < plain.mean() < 0.9  # some pixels untouched, others on hatch lines


def test_webp_decodes():
    img = np.zeros((256, 256, 4), "uint8")
    img[..., 3] = 255
    out = Image.open(io.BytesIO(encode_webp(img)))
    assert out.format == "WEBP" and out.size == (256, 256)


def test_layer_plan_matches_contract_ids():
    cfg = small_config()
    ids = [ly["id"] for ly in plan_layers(cfg)]
    assert "prob__christmas_day__2000_2019" in ids
    assert "change__christmas_day__2000_2009__2010_2019" in ids
    assert "trend__any_day__2000_2019" in ids
    trend = next(ly for ly in plan_layers(cfg) if ly["kind"] == "trend")
    assert trend["hatch_insignificant"] is True and trend["colormap"] == "trend"
