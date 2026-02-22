"""FDR calibration smoke: outputs in [0,1], not all 0 or 1."""

from crypto_analyzer.stats.calibration_fdr import calibrate_fdr_smoke


def test_calibration_fdr_smoke_outputs_in_01():
    out = calibrate_fdr_smoke(n_rep=25, n_hyp=8, seed=42)
    assert out["adj_bh_in_01"]
    assert out["adj_by_in_01"]


def test_calibration_fdr_smoke_not_all_zero_or_one():
    out = calibrate_fdr_smoke(n_rep=30, n_hyp=10, seed=7)
    assert out["not_all_zero"]
    assert out["not_all_one"]
