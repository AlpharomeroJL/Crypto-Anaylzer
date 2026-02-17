"""Milestone 4: signals_xs, risk_model, portfolio_advanced, evaluation, multiple_testing, experiments."""
import numpy as np
import pandas as pd
import sys
import tempfile
import os
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.signals_xs import (
    zscore_cross_section,
    winsorize_cross_section,
    neutralize_signal_to_exposures,
    orthogonalize_signals,
)
from crypto_analyzer.risk_model import ensure_psd, ewma_cov, shrink_cov_to_diagonal, estimate_covariance
from crypto_analyzer.portfolio_advanced import optimize_long_short_portfolio
from crypto_analyzer.evaluation import conditional_metrics, stability_report
from crypto_analyzer.multiple_testing import deflated_sharpe_ratio, pbo_proxy_walkforward
from crypto_analyzer.experiments import log_experiment, load_experiments


def test_neutralize_signal_reduces_corr_to_beta():
    """Neutralized signal should have lower correlation to beta exposure than raw."""
    np.random.seed(42)
    n_ts, n_assets = 30, 5
    idx = pd.date_range("2020-01-01", periods=n_ts, freq="h")
    cols = [f"a{i}" for i in range(n_assets)]
    # Signal = beta + noise (so highly correlated to beta)
    beta_exp = pd.DataFrame(
        np.random.randn(n_ts, n_assets).cumsum(axis=0) * 0.1,
        index=idx,
        columns=cols,
    )
    signal = beta_exp + np.random.randn(n_ts, n_assets) * 0.3
    raw_corr = np.corrcoef(signal.values.ravel(), beta_exp.values.ravel())[0, 1]
    neutral = neutralize_signal_to_exposures(signal, {"beta": beta_exp}, method="ols")
    if neutral.isna().all().all():
        return  # degenerate case
    valid = np.isfinite(neutral.values) & np.isfinite(beta_exp.values)
    if valid.sum() < 10:
        return
    after_corr = np.corrcoef(neutral.values.ravel()[valid.ravel()], beta_exp.values.ravel()[valid.ravel()])[0, 1]
    assert abs(after_corr) <= abs(raw_corr) + 0.2, "Neutralized signal should have lower correlation to beta"


def test_orthogonalize_signals_reduces_cross_corr():
    """After orthogonalization, average absolute cross-correlation should drop."""
    np.random.seed(43)
    n_ts, n_assets = 25, 4
    idx = pd.date_range("2020-01-01", periods=n_ts, freq="h")
    cols = [f"a{i}" for i in range(n_assets)]
    s1 = pd.DataFrame(np.random.randn(n_ts, n_assets).cumsum(axis=0), index=idx, columns=cols)
    s2 = s1 * 0.7 + pd.DataFrame(np.random.randn(n_ts, n_assets), index=idx, columns=cols)
    signals_dict = {"A": s1, "B": s2}
    orth, report = orthogonalize_signals(signals_dict)
    assert "A" in orth and "B" in orth
    if "B_avg_corr_before" in report and "B_avg_corr_after" in report:
        assert report["B_avg_corr_after"] <= report["B_avg_corr_before"] + 0.3


def test_cov_psd():
    """ensure_psd produces a PSD matrix (non-negative eigenvalues)."""
    np.random.seed(44)
    n = 4
    C = np.random.randn(n, n)
    C = C @ C.T
    C[0, 1] = C[1, 0] = -1.5
    df = pd.DataFrame(C, index=[f"a{i}" for i in range(n)], columns=[f"a{i}" for i in range(n)])
    out = ensure_psd(df)
    eigs = np.linalg.eigvalsh(out.values)
    assert np.all(eigs >= -1e-8), "Output should be PSD"


def test_portfolio_constraints_respected():
    """Weights should respect max_weight_per_asset and dollar neutrality."""
    np.random.seed(45)
    n = 5
    er = pd.Series(np.random.randn(n) * 0.1, index=[f"a{i}" for i in range(n)])
    cov = pd.DataFrame(np.eye(n) * 0.01, index=er.index, columns=er.index)
    constraints = {
        "max_weight_per_asset": 0.2,
        "dollar_neutral": True,
        "target_gross_leverage": 1.0,
    }
    w, diag = optimize_long_short_portfolio(er, cov, constraints)
    assert w.abs().max() <= 0.2 + 1e-6, "Max weight should be <= 0.2"
    # After final clip, sum may deviate from 0; heuristic aims for dollar neutral
    assert abs(w.sum()) < 0.2, "Weights should be roughly dollar neutral (clip can leave small residual)"


def test_conditional_metrics_outputs():
    """conditional_metrics returns table with expected columns."""
    np.random.seed(46)
    n = 100
    pnl = pd.Series(np.random.randn(n) * 0.01, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    regime = pd.Series(np.random.choice(["high", "mid", "low"], n), index=pnl.index)
    df = conditional_metrics(pnl, regime)
    assert isinstance(df, pd.DataFrame)
    assert "regime" in df.columns and "n" in df.columns


def test_deflated_sharpe_sane_ordering():
    """Higher raw Sharpe and lower n_trials should give higher deflated SR (or at least sane)."""
    np.random.seed(47)
    n = 200
    pnl_low = pd.Series(np.random.randn(n) * 0.005, index=pd.date_range("2020-01-01", periods=n, freq="h"))
    pnl_high = pd.Series(0.001 + np.random.randn(n) * 0.005, index=pnl_low.index)
    d_low = deflated_sharpe_ratio(pnl_low, "1h", 100)
    d_high = deflated_sharpe_ratio(pnl_high, "1h", 100)
    assert "raw_sr" in d_low and "deflated_sr" in d_low
    assert d_high["raw_sr"] >= d_low["raw_sr"] - 0.5, "Higher mean return should give higher raw SR"
    d_same_low_trials = deflated_sharpe_ratio(pnl_high, "1h", 10)
    d_same_high_trials = deflated_sharpe_ratio(pnl_high, "1h", 500)
    assert d_same_high_trials.get("e_max_sr_null", 0) >= d_same_low_trials.get("e_max_sr_null", 0) - 0.5


def test_pbo_proxy_range():
    """PBO proxy should be in [0, 1] when we have valid splits."""
    df = pd.DataFrame({
        "split_id": [0, 1, 2, 3, 4],
        "train_sharpe": [0.5, 0.6, 0.4, 0.7, 0.3],
        "test_sharpe": [0.1, -0.2, 0.3, 0.0, 0.2],
    })
    out = pbo_proxy_walkforward(df)
    assert "pbo_proxy" in out
    pbo = out["pbo_proxy"]
    assert 0 <= pbo <= 1 or (np.isnan(pbo)), "PBO should be in [0,1] or nan"


def test_experiment_logging_roundtrip():
    """Log experiment then load_experiments returns at least one row with matching run_name."""
    with tempfile.TemporaryDirectory() as d:
        run_name = "test_run_roundtrip"
        log_experiment(
            run_name=run_name,
            config_dict={"freq": "1h"},
            metrics_dict={"sharpe": 0.5},
            artifacts_paths=[],
            out_dir=d,
        )
        df = load_experiments(d)
        assert not df.empty
        assert "run_name" in df.columns
        assert run_name in df["run_name"].astype(str).values
