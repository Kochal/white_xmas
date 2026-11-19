"""Ensemble agreement and the per-model projection onto the target grid."""

import warnings

import numpy as np

from whitexmas.projections.baseline import NX, NY
from whitexmas.projections.ensemble import (
    NO_CHANGE_PP,
    agreement,
    nan_percentiles,
    project_model,
)


def test_agreement_needs_two_thirds_in_one_direction():
    # each model's projected probability minus today's, in pp
    d = np.array(
        [
            [-5.0, -3.0, 4.0, 0.0, np.nan],
            [-2.0, 3.0, 2.0, 0.2, np.nan],
            [-1.0, 6.0, -3.0, -3.0, np.nan],
        ]
    )
    np.testing.assert_array_equal(agreement(d), [True, True, True, True, False])
    d4 = np.array([[-1.0], [-1.0], [1.0], [1.0]])
    assert not agreement(d4)[0]  # 2 of 4 is not two thirds


def test_agreement_ignores_models_without_a_value():
    d = np.array([[-1.0], [-1.0], [np.nan]])
    assert agreement(d)[0]


def test_changes_below_half_a_point_count_as_no_change():
    assert NO_CHANGE_PP == 0.5
    # every model within 0.5 pp of today (both signs, tiny values, exact zeros): agreed
    d = np.array([[0.0], [0.3], [-0.49], [1e-4], [-0.2], [0.0]])
    assert agreement(d)[0]
    # 0.5 pp or more is a direction; three of six moving down by 0.6 pp breaks the agreement
    d2 = np.array([[0.0], [0.3], [-0.6], [-0.6], [-0.6], [0.0]])
    assert not agreement(d2)[0]
    # ... and once two thirds move down, they agree on a decrease
    d3 = np.array([[0.0], [-0.6], [-0.6], [-0.6], [-0.6], [0.0]])
    assert agreement(d3)[0]


def test_one_model_moving_more_than_half_a_point_is_flagged_as_before():
    # two models: one stays, one moves by 2 pp -> 1 of 2 is not two thirds
    d = np.array([[0.1, 0.1], [-2.0, 2.0]])
    np.testing.assert_array_equal(agreement(d), [False, False])


def test_a_london_like_cell_is_not_flagged():
    # never white today: models that lose snow cannot go below 0 % (change exactly 0), models
    # with a tiny positive log-odds change project a few hundredths of a per cent, after the
    # regrid some get a sliver. All round to today's 0 %: not "models disagree".
    from whitexmas.projections.transfer import apply_change

    deltas = np.array([-0.8, -0.3, 0.0, 0.0, 0.05, 0.1, 0.2, -1.2, 0.15, 0.0])
    proj = apply_change(np.zeros(len(deltas)), n_obs=30, delta=deltas)
    assert proj.max() < NO_CHANGE_PP
    q = nan_percentiles(proj[:, None], (10, 50, 90))[:, 0]
    assert np.round(q).tolist() == [0.0, 0.0, 0.0]  # p10 = p50 = p90 = today
    assert agreement(proj[:, None] - 0.0)[0]
    # the log-odds signs alone would split 3 down / 3 none / 4 up: no two thirds
    signs = np.sign(deltas)
    assert max((signs < 0).sum(), (signs > 0).sum(), (signs == 0).sum()) < 2 / 3 * len(signs)


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
