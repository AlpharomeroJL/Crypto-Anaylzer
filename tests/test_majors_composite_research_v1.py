"""majors_composite_research_v1: equal-mean of z-scored short_horizon_reversal and xs_low_vol_tilt."""

import numpy as np
import pandas as pd

from crypto_analyzer.signals_xs import (
    majors_composite_research_v1,
    short_horizon_reversal,
    xs_low_vol_tilt,
    zscore_cross_section,
)


def test_majors_composite_research_v1_is_mean_of_zscored_legs() -> None:
    idx = pd.date_range("2025-01-01", periods=60, freq="h", tz="UTC")
    cols = ["BTC-USD", "A-USD", "B-USD", "C-USD"]
    rng = np.random.default_rng(7)
    r = pd.DataFrame(rng.normal(0, 0.011, (len(idx), len(cols))), index=idx, columns=cols)
    comp = majors_composite_research_v1(r, "1h")
    sh = short_horizon_reversal(r, "1h")
    lv = xs_low_vol_tilt(r, "1h")
    z1 = zscore_cross_section(sh)
    z2 = zscore_cross_section(lv)
    exp = (z1 + z2) / 2.0
    common = comp.index.intersection(exp.index)
    cols2 = comp.columns.intersection(exp.columns)
    pd.testing.assert_frame_equal(
        comp.reindex(common).reindex(columns=cols2),
        exp.reindex(common).reindex(columns=cols2),
        rtol=1e-9,
        atol=1e-9,
        check_names=False,
    )
