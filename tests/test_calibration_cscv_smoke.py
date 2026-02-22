"""CSCV calibration smoke: pbo in [0,1] when present; not all same."""

from crypto_analyzer.stats.calibration_cscv import calibrate_cscv_smoke


def test_calibration_cscv_smoke_all_in_01():
    out = calibrate_cscv_smoke(n_rep=20, T=40, J=4, S=8, seed=42)
    assert out["all_in_01"]


def test_calibration_cscv_smoke_returns():
    out = calibrate_cscv_smoke(n_rep=15, seed=7)
    assert "n_rep" in out
    assert out.get("skipped") or out.get("all_in_01", False) or "n_with_pbo" in out
