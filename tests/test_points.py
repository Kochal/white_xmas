import gzip
import json

import numpy as np

from whitexmas.export.points import (
    decode_tile,
    encode_tile,
    tile_of,
    to_uint8,
    write_point_tiles,
)


def test_to_uint8_caps_and_nodata():
    a = np.array([-1, 0, 1, 253, 254, 300, 3333], dtype="int16")
    assert to_uint8(a).tolist() == [255, 0, 1, 253, 254, 254, 254]


def test_encode_layout_matches_contract():
    vals = np.zeros((50, 50, 2, 3), "uint8")
    vals[0, 1, 1, 2] = 7  # cell (row 0, col 1), year 2, Dec 26
    glac = np.zeros((50, 50), bool)
    glac[0, 0] = glac[0, 9] = True
    raw = gzip.decompress(encode_tile(vals, glac, 1950))
    assert raw[:4] == b"WXP1"
    assert int.from_bytes(raw[4:6], "little") == 1950
    assert int.from_bytes(raw[6:8], "little") == 2
    assert int.from_bytes(raw[8:10], "little") == 50
    assert int.from_bytes(raw[10:12], "little") == 50
    assert raw[12] == 3 and raw[13:16] == b"\0\0\0"
    # body offset of cell (0, 1), year index 1, day index 2
    assert raw[16 + ((0 * 50 + 1) * 2 + 1) * 3 + 2] == 7
    mask = raw[16 + 50 * 50 * 2 * 3 :]
    assert len(mask) == 313  # ceil(2500 / 8)
    assert mask[0] == 0b00000001 and mask[1] == 0b00000010


def test_round_trip():
    rng = np.random.default_rng(3)
    vals = rng.integers(0, 256, size=(50, 50, 76, 3), dtype="uint8")
    glac = rng.random((50, 50)) > 0.8
    t = decode_tile(encode_tile(vals, glac, 1950))
    assert t.first_year == 1950
    np.testing.assert_array_equal(t.values, vals)
    np.testing.assert_array_equal(t.glacier, glac)


def test_tile_of_contract_examples():
    assert tile_of(11.58, 48.14) == (38, 8)  # Munich
    assert tile_of(-180, 90) == (0, 0)
    assert tile_of(179.9, -90) == (71, 36)


def test_write_point_tiles_from_cube(tmp_path):
    ny, nx, years = 101, 150, [2000, 2001]
    cube = np.full((2, 3, ny, nx), -1, "int16")
    cube[:, :, 60, 120] = [[0, 5, 300], [1, 2, 3]]  # one land cell in tile (2, 1)
    cube[:, :, 100, 0] = 4  # south row j=100 → tile (0, 2), partial tile
    land = (cube != -1).any(axis=(0, 1))
    glac = np.zeros((ny, nx), bool)
    glac[60, 120] = True
    stats = write_point_tiles(tmp_path, cube, glac, land, years)
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx == {"format": "wx-points-v1", "tile_deg": 5, "years": [2000, 2001],
                   "tiles": ["2_1", "0_2"]}  # fmt: skip
    assert stats["tiles"] == 2
    t = decode_tile((tmp_path / "2_1.bin.gz").read_bytes())
    np.testing.assert_array_equal(t.values[10, 20], [[0, 5, 254], [1, 2, 3]])
    assert t.glacier[10, 20] and t.glacier.sum() == 1
    assert (t.values[10, 21] == 255).all()
    t2 = decode_tile((tmp_path / "0_2.bin.gz").read_bytes())
    assert (t2.values[0, 0] == 4).all() and (t2.values[1:] == 255).all()
