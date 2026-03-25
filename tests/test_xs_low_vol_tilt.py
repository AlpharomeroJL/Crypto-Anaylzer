"""xs_low_vol_tilt: majors-native low-vol signal (not momentum-family)."""

import numpy as np
import pandas as pd

from crypto_analyzer.signals_xs import xs_low_vol_tilt


def test_xs_low_vol_tilt_negates_rolling_vol_and_excludes_btc_usd() -> None:
    idx = pd.date_range("2025-01-01", periods=30, freq="h", tz="UTC")
    cols = ["BTC-USD", "AAA-USD", "BBB-USD"]
    rng = np.random.default_rng(0)
    r = pd.DataFrame(rng.normal(0, 0.01, (len(idx), len(cols))), index=idx, columns=cols)
    out = xs_low_vol_tilt(r, "1h")
    assert out.shape == r.shape
    assert out["BTC-USD"].isna().all()
    # After warm-up, signal should be negative of rolling std (finite for alt legs)
    t = idx[25]
    vol = r["AAA-USD"].rolling(24).std(ddof=1).loc[t]
    assert np.isfinite(vol) and vol > 0
    assert abs(out.loc[t, "AAA-USD"] + vol) < 1e-9
