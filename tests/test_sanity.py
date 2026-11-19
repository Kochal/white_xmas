import numpy as np

from whitexmas.sanity import compare_legacy


def test_compare_legacy_on_land_only():
    new = np.array([[10.0, 20.0, np.nan, 50.0]])
    legacy = np.array([[20.0, 20.0, 0.0, 100.0]])  # legacy has 0 % over the ocean cell
    land = np.array([[True, True, False, True]])
    glac = np.array([[False, False, False, True]])
    s = compare_legacy(new, legacy, land, glac)
    assert s["land"]["cells"] == 3
    assert s["land"]["bias_pp"] == np.mean([-10, 0, -50])
    assert s["land"]["share_new_le_legacy"] == 1.0
    assert s["land_no_glacier"]["cells"] == 2
    assert s["land_no_glacier"]["pearson_r"] == 1.0 or np.isnan(s["land_no_glacier"]["pearson_r"])
