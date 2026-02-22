"""RC calibration smoke: p-value in [0,1], null not degenerate."""

from crypto_analyzer.stats.calibration_rc import calibrate_rc_smoke


def test_calibration_rc_smoke_p_value_in_01():
    out = calibrate_rc_smoke(n_obs=50, n_sim=20, seed=42)
    assert out["in_01"]
    assert 0 <= out["rc_p_value"] <= 1


def test_calibration_rc_smoke_not_degenerate():
    out = calibrate_rc_smoke(n_obs=60, n_sim=25, seed=7)
    assert out["not_degenerate"]
    assert out["actual_n_sim"] == 25
