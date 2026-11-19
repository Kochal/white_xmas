import numpy as np

from whitexmas.export.regions import regional_means


def test_regional_means_weight_by_cos_lat_and_skip_glacier():
    idx = np.array([[0, 0], [0, 1]])
    p_then = np.array([[10.0, 30.0], [50.0, 80.0]])
    p_now = p_then - 10
    glacier = np.array([[False, False], [True, False]])
    lat = np.array([0.0, 60.0])
    then, now, ws = regional_means(idx, p_then, p_now, glacier, lat, 2)
    assert then[0] == 20.0 and now[0] == 10.0  # the glacier cell (50) is excluded
    assert ws[1] == np.cos(np.radians(60.0))
