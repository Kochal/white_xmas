"""Ensemble agreement and the per-model projection onto the target grid."""

import warnings

import numpy as np

from whitexmas.projections.baseline import NX, NY
from whitexmas.projections.ensemble import agreement, nan_percentiles, project_model


def test_agreement_needs_two_thirds_in_one_direction():
    d = np.array(
        [
            [-1.0, -1.0, 1.0, 0.0, np.nan],
            [-0.5, 1.0, 1.0, 0.0, np.nan],
            [-0.2, 2.0, -1.0, -0.3, np.nan],
        ]
    )
    np.testing.assert_array_equal(agreement(d), [True, True, True, True, False])
    d4 = np.array([[-1.0], [-1.0], [1.0], [1.0]])
    assert not agreement(d4)[0]  # 2 of 4 is not two thirds


def test_agreement_ignores_models_without_a_value():
    d = np.array([[-1.0], [-1.0], [np.nan]])
    assert agreement(d)[0]


def test_uniform_model_change_projects_uniformly_and_fills_coasts():
    lat = np.array([-60.0, 0.0, 60.0])
    lon = np.array([0.0, 120.0, 240.0])
    delta = np.full((3, 3), -1.0)
    delta[1, 1] = np.nan  # a model ocean cell: filled from its land neighbours
    p_obs = np.full((NY, NX), 50.0, dtype="float32")
    n_obs = np.full((NY, NX), 30, dtype="int16")
    cells = (np.array([0, 900, 1800]), np.array([0, 1800, 3599]))
    reg, proj = project_model(delta, lat, lon, p_obs, n_obs, cells)
    np.testing.assert_allclose(reg, -1.0)
    # 50 % -> logit 0 -> expit(-1) = 0.2689 -> (31 * 0.2689 - 0.5) / 30 = 26.12 %
    np.testing.assert_allclose(proj, 26.12, atol=0.01)


def test_nan_percentiles_match_numpy():
    rng = np.random.default_rng(1)
    x = rng.uniform(0, 100, (21, 500))
    x[rng.random(x.shape) < 0.2] = np.nan
    x[:, 0] = np.nan
    x[1:, 1] = np.nan  # a single model
    got = nan_percentiles(x, (10, 50, 90))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        want = np.nanpercentile(x, [10, 50, 90], axis=0)
    np.testing.assert_allclose(got, want, equal_nan=True)
