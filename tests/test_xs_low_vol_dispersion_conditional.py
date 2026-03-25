"""xs_low_vol_dispersion_conditional: low-vol tilt × sign(dispersion z), majors-native."""

import numpy as np
import pandas as pd

from crypto_analyzer.alpha_research import compute_dispersion_series, dispersion_zscore_series
from crypto_analyzer.signals_xs import xs_low_vol_dispersion_conditional, xs_low_vol_tilt


def test_xs_low_vol_dispersion_equals_base_times_sign_of_dispersion_z() -> None:
    idx = pd.date_range("2025-01-01", periods=50, freq="h", tz="UTC")
    cols = ["BTC-USD", "X-USD", "Y-USD", "Z-USD"]
    rng = np.random.default_rng(42)
    r = pd.DataFrame(rng.normal(0, 0.012, (len(idx), len(cols))), index=idx, columns=cols)
    w = 24
    base = xs_low_vol_tilt(r, "1h")
    out = xs_low_vol_dispersion_conditional(r, "1h", dispersion_window=w)
    dz = dispersion_zscore_series(compute_dispersion_series(r), w)
    common = base.index.intersection(dz.index)
    z = dz.reindex(common).ffill().bfill()
    sign_z = np.sign(z.to_numpy(dtype=float))
    sign_z = np.where(sign_z == 0.0, 1.0, sign_z)
    expected = base.reindex(common).mul(sign_z, axis=0)
    pd.testing.assert_frame_equal(
        out.reindex(common),
        expected,
        rtol=1e-9,
        atol=1e-9,
        check_names=False,
    )
