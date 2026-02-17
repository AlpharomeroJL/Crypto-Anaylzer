"""Statistics: block bootstrap outputs."""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.statistics import block_bootstrap_pnl, sharpe_ci, significance_summary


def test_block_bootstrap_outputs():
    """Bootstrap CI returns lo <= mid <= hi and correct length."""
    np.random.seed(47)
    n = 100
    pnl = pd.Series(np.random.randn(n) * 0.01)
    lo, mid, hi = sharpe_ci(pnl, "1h", block_size=10, n=200, seed=42)
    assert lo <= mid <= hi or (np.isnan(lo) and np.isnan(mid) and np.isnan(hi))
    dist = block_bootstrap_pnl(pnl, block_size=10, n=100, seed=42)
    assert len(dist) == 100
    summ = significance_summary(pnl, "1h", block_size=10, n_bootstrap=50)
    assert "sharpe_annual" in summ
    assert "sharpe_ci_95_lo" in summ and "sharpe_ci_95_hi" in summ
    assert summ["sharpe_ci_95_lo"] <= summ["sharpe_ci_95_hi"] or (np.isnan(summ["sharpe_ci_95_lo"]) and np.isnan(summ["sharpe_ci_95_hi"]))
