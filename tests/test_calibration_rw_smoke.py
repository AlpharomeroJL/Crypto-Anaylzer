"""RW calibration smoke: adjusted p-values in [0,1], not all 0 or 1."""

from crypto_analyzer.stats.calibration_rw import calibrate_rw_smoke


def test_calibration_rw_smoke_adj_in_01():
    out = calibrate_rw_smoke(n_obs=50, n_sim=30, seed=42)
    assert out["rw_adj_in_01"]


def test_calibration_rw_smoke_not_all_zero_or_one():
    out = calibrate_rw_smoke(n_obs=50, n_sim=30, seed=7)
    assert out["rw_not_all_zero"]
    assert out["rw_not_all_one"]
