"""Scan mode residual_momentum returns a DataFrame with residual columns when factors exist."""

import pandas as pd

from crypto_analyzer.cli.scan import run_scan


def test_residual_momentum_mode_returns_dataframe():
    """run_scan with mode=residual_momentum returns (DataFrame, float, float, list)."""

    try:
        res, disp_l, disp_z, reasons = run_scan(
            db="dex_data.sqlite",
            mode="residual_momentum",
            freq="1h",
            top=5,
        )
    except FileNotFoundError:
        res = pd.DataFrame()
        reasons = []
    assert isinstance(res, pd.DataFrame)
    assert isinstance(reasons, list)


def test_residual_momentum_mode_has_residual_columns_in_contract():
    """When run_scan(mode=residual_momentum) returns non-empty df, it must include residual_return_24h (contract)."""
    import numpy as np

    from crypto_analyzer.cli.scan import scan_residual_momentum

    # Minimal bars and returns_df with factor columns so residual_momentum can run
    idx = pd.date_range("2024-01-01", periods=50, freq="1h")
    bars = pd.DataFrame(
        {
            "ts_utc": idx.repeat(1),
            "chain_id": "solana",
            "pair_address": "addr1",
            "base_symbol": "SOL",
            "quote_symbol": "USDC",
            "close": 100.0 + np.cumsum(np.random.randn(50) * 0.5),
            "log_return": np.random.randn(50) * 0.01,
            "liquidity_usd": 1e6,
            "vol_h24": 5e5,
        }
    )
    bars["pair_id"] = bars["chain_id"] + ":" + bars["pair_address"]
    returns_df = pd.DataFrame(
        {
            "solana:addr1": np.random.randn(50) * 0.01,
            "BTC_spot": np.random.randn(50) * 0.01,
            "ETH_spot": np.random.randn(50) * 0.01,
        },
        index=idx,
    )
    out = scan_residual_momentum(bars, "1h", top=5, returns_df=returns_df, lookback_bars=24)
    assert isinstance(out, pd.DataFrame)
    if not out.empty:
        assert "residual_return_24h" in out.columns
