import numpy as np

from whitexmas.export.places import cell_index, nearest_valid, pick_alt


def test_cell_index_contract():
    assert cell_index(48.14, 11.58) == (419, 1916)
    assert cell_index(90, -180) == (0, 0)
    assert cell_index(-90, 179.96) == (1800, 0)  # wraps to i = 0


def test_nearest_valid_prefers_own_cell_then_closest_within_2():
    v = np.zeros((10, 10), bool)
    v[5, 5] = True
    assert nearest_valid(v, 5, 5) == (5, 5)
    assert nearest_valid(v, 5, 7) == (5, 5)
    assert nearest_valid(v, 7, 7) is None  # distance sqrt(8) > 2
    v[6, 9] = True
    assert nearest_valid(v, 6, 0) == (6, 9)  # wraps across the dateline


def test_pick_alt_orders_languages_and_dedupes():
    alts = [
        ("de", "München", True, False),
        ("de", "Muenchen", False, False),
        ("en", "Munich", False, False),
        ("it", "Monaco di Baviera", False, False),
        ("fr", "Munich", False, False),
        ("es", "Múnich", False, False),
        ("bar", "Minga", False, False),
    ]
    assert pick_alt("Munich", "Munich", ["de"], alts) == "München|Múnich"
    # an official language beyond the first comes after the exonyms
    assert pick_alt("Munich", "Munich", ["de", "it"], alts) == "München|Múnich|Monaco di Baviera"


def test_pick_alt_caps_count_and_length():
    alts = [(f"l{k}", f"Name{k}" * 3, False, False) for k in range(10)]
    out = pick_alt("X", "X", [f"l{k}" for k in range(10)], alts)
    assert len(out) <= 80 and out.count("|") <= 4
