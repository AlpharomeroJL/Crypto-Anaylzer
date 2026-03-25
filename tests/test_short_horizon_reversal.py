"""short_horizon_reversal: minus rolling sum of log returns over quarter-day window (majors)."""

import numpy as np
import pandas as pd

from crypto_analyzer.features import period_return_bars
from crypto_analyzer.signals_xs import short_horizon_reversal


def test_short_horizon_reversal_is_neg_rolling_sum_and_excludes_btc() -> None:
    idx = pd.date_range("2025-01-01", periods=40, freq="h", tz="UTC")
    cols = ["BTC-USD", "AAA-USD"]
    rng = np.random.default_rng(0)
    r = pd.DataFrame(rng.normal(0, 0.01, (len(idx), len(cols))), index=idx, columns=cols)
    out = short_horizon_reversal(r, "1h")
    bars_24 = period_return_bars("1h").get("24h", 24)
    short_bars = max(2, bars_24 // 4)
    t = idx[30]
    s = r["AAA-USD"].rolling(short_bars, min_periods=short_bars).sum().loc[t]
    assert abs(out.loc[t, "AAA-USD"] + s) < 1e-9
    assert out["BTC-USD"].isna().all()
