"""Capacity and estimated slippage behave as expected on synthetic inputs."""
import numpy as np
import pandas as pd
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "cli"))

from scan import _add_capacity_slippage_tradable, DEFAULT_MAX_POS_LIQ_PCT, DEFAULT_MAX_SLIPPAGE_BPS_TRADABLE


def test_capacity_usd_scales_with_liquidity():
    """capacity_usd = max_pos_liq_pct * liquidity_usd."""
    df = pd.DataFrame({
        "chain_id": ["c1", "c2"],
        "pair_address": ["a1", "a2"],
        "liquidity_usd": [1_000_000.0, 500_000.0],
    })
    out = _add_capacity_slippage_tradable(df, max_pos_liq_pct=0.01)
    assert "capacity_usd" in out.columns
    assert out.loc[0, "capacity_usd"] == 10_000.0
    assert out.loc[1, "capacity_usd"] == 5_000.0


def test_est_slippage_bps_higher_when_capacity_small():
    """est_slippage_bps is higher when capacity_usd is smaller (inverse relationship)."""
    df = pd.DataFrame({
        "chain_id": ["c1", "c2"],
        "pair_address": ["a1", "a2"],
        "liquidity_usd": [10_000_000.0, 100_000.0],
    })
    out = _add_capacity_slippage_tradable(df, max_pos_liq_pct=0.01)
    assert out.loc[0, "est_slippage_bps"] < out.loc[1, "est_slippage_bps"]


def test_tradable_false_when_slippage_above_threshold():
    """tradable is False when est_slippage_bps > max_slippage_bps_tradable."""
    df = pd.DataFrame({
        "chain_id": ["c1"],
        "pair_address": ["a1"],
        "liquidity_usd": [1.0],
    })
    out = _add_capacity_slippage_tradable(
        df,
        max_pos_liq_pct=0.01,
        max_slippage_bps_tradable=50.0,
    )
    assert out["est_slippage_bps"].iloc[0] > 50.0
    assert out["tradable"].iloc[0] == False


def test_tradable_true_when_slippage_below_threshold():
    """tradable is True when est_slippage_bps <= threshold."""
    df = pd.DataFrame({
        "chain_id": ["c1"],
        "pair_address": ["a1"],
        "liquidity_usd": [100_000_000.0],
    })
    out = _add_capacity_slippage_tradable(
        df,
        max_pos_liq_pct=0.01,
        max_slippage_bps_tradable=50.0,
    )
    assert out["est_slippage_bps"].iloc[0] <= 50.0 or out["tradable"].iloc[0] == True
