"""Log-odds change transfer (plan §3b): a model's change applied to the ERA5-Land baseline."""

import numpy as np
import pytest

from whitexmas.projections.transfer import apply_change, logodds_change


def test_no_model_change_returns_baseline_exactly():
    base = np.array([0.0, 10.0, 50.0, 73.3, 100.0])
    delta = logodds_change(k_base=7, n_base=20, k_fut=7, n_fut=20)
    assert delta == 0.0
    np.testing.assert_allclose(apply_change(base, n_obs=30, delta=delta), base, atol=1e-9)


def test_round_trip_change_and_its_inverse():
    base = np.linspace(0, 100, 31)
    d = logodds_change(k_base=12, n_base=20, k_fut=4, n_fut=20)
    there = apply_change(base, n_obs=30, delta=d)
    back = apply_change(there, n_obs=30, delta=-d)
    inner = (there > 0) & (there < 100)  # clipped values cannot come back
    np.testing.assert_allclose(back[inner], base[inner], atol=1e-9)


def test_zero_and_full_model_frequencies_stay_finite():
    # 0/20 -> 20/20 in the model would be +inf without smoothing
    d_up = logodds_change(k_base=0, n_base=20, k_fut=20, n_fut=20)
    d_down = logodds_change(k_base=20, n_base=20, k_fut=0, n_fut=20)
    assert np.isfinite(d_up) and np.isfinite(d_down)
    # Jeffreys: logit(20.5/21) - logit(0.5/21) = 2 * ln(41)
    assert d_up == pytest.approx(2 * np.log(41))
    assert d_down == pytest.approx(-2 * np.log(41))


def test_baseline_at_0_and_100_percent_can_move_and_stays_in_range():
    base = np.array([0.0, 100.0])
    down = apply_change(base, n_obs=30, delta=-1.0)
    up = apply_change(base, n_obs=30, delta=+1.0)
    assert down[0] == 0.0  # cannot go below 0
    assert 0 < down[1] < 100  # a 100 % cell does decline
    assert 0 < up[0] < 100  # a 0 % cell can gain
    assert up[1] == 100.0


def test_known_synthetic_change():
    # Model halves its odds: 10/20 -> 5/20 gives delta = logit(5.5/21) - logit(10.5/21)
    d = logodds_change(k_base=10, n_base=20, k_fut=5, n_fut=20)
    assert d == pytest.approx(np.log(5.5 / 15.5))
    # Baseline 15/30 = 50 %: q = 15.5/31 = 0.5, logit 0, so q' = expit(d) = 5.5/21.
    # Back to counts: k' = 31 q' - 0.5 = 7.619 of 30 years = 25.397 %.
    assert apply_change(np.array([50.0]), n_obs=30, delta=d)[0] == pytest.approx(25.3968, abs=1e-3)


def test_fractional_frequencies_and_arrays_broadcast():
    # pooled days give fractional "white" counts; arrays of cells broadcast
    k_base = np.array([[3.4, 0.0], [20.0, 10.0]])
    k_fut = np.array([[1.2, 0.0], [20.0, 12.5]])
    d = logodds_change(k_base, 20, k_fut, 20)
    assert d.shape == (2, 2)
    assert d[0, 1] == 0.0 and d[1, 0] == 0.0
    assert d[0, 0] < 0 < d[1, 1]


def test_nan_propagates():
    d = logodds_change(np.array([np.nan, 5.0]), 20, np.array([3.0, 5.0]), 20)
    assert np.isnan(d[0]) and d[1] == 0.0
    out = apply_change(np.array([np.nan, 40.0]), n_obs=30, delta=np.array([0.5, np.nan]))
    assert np.isnan(out).all()


# Windows of different length (production: a 30-year baseline, 20-year warming-level windows).
# Smoothing each window with its own n made equal frequencies look like a change.


@pytest.mark.parametrize(
    ("kb", "nb", "kf", "nf"),
    [
        (0, 30, 0, 20),  # never white in either window
        (30, 30, 20, 20),  # always white in either window
        (3, 30, 2, 20),  # 10 % in both
        (27, 30, 18, 20),  # 90 % in both
        (4.5, 30, 3.0, 20),  # fractional (pooled) counts, 15 % in both
        (0, 20, 0, 30),  # and the other way round
    ],
)
def test_same_frequency_in_windows_of_different_length_is_no_change(kb, nb, kf, nf):
    d = logodds_change(kb, nb, kf, nf)
    assert d == 0.0
    base = np.array([0.0, 3.3, 50.0, 96.7, 100.0])
    out = apply_change(base, n_obs=30, delta=d)
    assert out[0] == 0.0 and out[-1] == 100.0  # exactly, not "about 0.8 %"
    np.testing.assert_allclose(out, base, atol=1e-12)


def test_never_white_cell_stays_at_zero():
    # the reported bug: 0/30 -> 0/20 used to give +0.397 and London 0 % -> 0.79 %
    d = logodds_change(0, 30, 0, 20)
    assert apply_change(np.array([0.0]), n_obs=30, delta=d)[0] == 0.0
    d_full = logodds_change(30, 30, 20, 20)
    assert apply_change(np.array([100.0]), n_obs=30, delta=d_full)[0] == 100.0


def test_equal_windows_are_plain_jeffreys():
    # nothing changes for equal windows (the 30/30-year hindcast): logit((k+1/2)/(n+1))
    from scipy.special import logit

    for kb, kf in [(12, 4), (0, 3), (30, 29), (7.25, 9.5)]:
        expect = logit((kf + 0.5) / 31) - logit((kb + 0.5) / 31)
        assert logodds_change(kb, 30, kf, 30) == pytest.approx(expect, abs=1e-12)


def test_common_smoothing_uses_the_shorter_window():
    # 15/30 -> 5/20: f = 0.5 -> 0.25, both smoothed with m = 20
    d = logodds_change(15, 30, 5, 20)
    assert d == pytest.approx(np.log(5.5 / 15.5))
    # swapping the windows reverses the sign exactly
    assert logodds_change(5, 20, 15, 30) == pytest.approx(-d)


def test_rare_event_cells_move_the_right_way_and_stay_finite():
    one_to_none = logodds_change(1, 30, 0, 20)  # 3.3 % -> 0 %
    none_to_one = logodds_change(0, 30, 1, 20)  # 0 % -> 5 %
    assert np.isfinite(one_to_none) and one_to_none < 0
    assert np.isfinite(none_to_one) and none_to_one > 0
    # rarer in the future -> lower projection; never below 0 %
    p = apply_change(np.array([0.0, 3.3, 10.0]), n_obs=30, delta=one_to_none)
    assert p[0] == 0.0 and 0.0 <= p[1] < 3.3 and p[2] < 10.0
    # monotone in the future count
    ds = [logodds_change(1, 30, kf, 20) for kf in (0, 0.5, 1, 2, 4)]
    assert all(a < b for a, b in zip(ds, ds[1:], strict=False))


def test_per_cell_window_lengths_and_missing_windows():
    # n varies per cell (a missing year); n = 0 gives NaN, not a warning-free zero
    kb = np.array([0.0, 29.0, 5.0, 3.0])
    nb = np.array([30, 29, 30, 0])
    kf = np.array([0.0, 20.0, 2.0, 1.0])
    nf = np.array([20, 20, 20, 20])
    d = logodds_change(kb, nb, kf, nf)
    assert d[0] == 0.0 and d[1] == 0.0
    assert d[2] < 0
    assert np.isnan(d[3])
