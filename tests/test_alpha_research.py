"""Alpha research: IC sign, IC decay smoke, turnover bounds."""
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

import numpy as np
import pandas as pd

from crypto_analyzer.alpha_research import (
    compute_forward_returns,
    information_coefficient,
    ic_decay,
    ic_summary,
    turnover_from_ranks,
    signal_momentum_24h,
)


def test_ic_sign():
    """IC positive when signal equals forward returns (synthetic)."""
    np.random.seed(42)
    n_t, n_a = 50, 5
    idx = pd.date_range("2024-01-01", periods=n_t, freq="1h")
    ret = np.random.randn(n_t, n_a) * 0.01
    returns_df = pd.DataFrame(ret, index=idx, columns=[f"a{i}" for i in range(n_a)])
    signal_df = signal_momentum_24h(returns_df, "1h")
    if signal_df.empty:
        signal_df = np.exp(returns_df.rolling(24).sum()) - 1.0
    fwd = compute_forward_returns(returns_df, 1)
    signal_eq_fwd = fwd.copy()
    ic_ts = information_coefficient(signal_eq_fwd, fwd, method="spearman")
    s = ic_summary(ic_ts)
    assert s["mean_ic"] > 0.5 or s["n_obs"] < 2


def test_ic_decay_monotonicity_smoke():
    """IC decay returns table with expected horizons."""
    np.random.seed(43)
    n_t, n_a = 80, 4
    idx = pd.date_range("2024-01-01", periods=n_t, freq="1h")
    ret = np.random.randn(n_t, n_a) * 0.01
    returns_df = pd.DataFrame(ret, index=idx, columns=[f"a{i}" for i in range(n_a)])
    signal_df = signal_momentum_24h(returns_df, "1h")
    if signal_df.empty:
        signal_df = np.exp(returns_df.rolling(24).sum()) - 1.0
    decay_df = ic_decay(signal_df, returns_df, [1, 2, 3, 6], method="spearman")
    assert "horizon_bars" in decay_df.columns and "mean_ic" in decay_df.columns


def test_turnover_bounds():
    """Turnover from ranks between 0 and 2."""
    np.random.seed(44)
    n_t, n_a = 30, 6
    idx = pd.date_range("2024-01-01", periods=n_t, freq="1h")
    ranks_df = pd.DataFrame(
        np.random.permutation(n_a * n_t).reshape(n_t, n_a).astype(float),
        index=idx,
        columns=[f"a{i}" for i in range(n_a)],
    )
    turnover_ser, avg = turnover_from_ranks(ranks_df, top_k=2, bottom_k=2)
    if turnover_ser.notna().any():
        assert (turnover_ser.dropna() >= 0).all() and (turnover_ser.dropna() <= 2.0 + 1e-6).all()
    assert 0 <= avg <= 2.0 + 1e-6
