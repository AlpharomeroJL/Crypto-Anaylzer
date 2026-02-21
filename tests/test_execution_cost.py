"""ExecutionCostModel: determinism, monotonicity, missing-liquidity fallback."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from crypto_analyzer.execution_cost import (
    CAPACITY_CURVE_EXTRA_COLUMNS,
    CAPACITY_CURVE_REQUIRED_COLUMNS,
    DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY,
    ExecutionCostConfig,
    ExecutionCostModel,
    apply_costs,
    capacity_curve,
    capacity_curve_is_non_monotone,
    impact_bps_from_participation,
    slippage_bps_from_liquidity,
    spread_bps_from_vol_liquidity,
)


def test_same_inputs_identical_net_returns():
    """Same inputs -> identical net_returns (deterministic)."""
    np.random.seed(1)
    n = 50
    gross = pd.Series(np.random.randn(n) * 0.01)
    turnover = pd.Series(np.random.rand(n) * 0.1)
    net1, cost1 = apply_costs(gross, turnover, fee_bps=30, slippage_bps=10)
    net2, cost2 = apply_costs(gross, turnover, fee_bps=30, slippage_bps=10)
    pd.testing.assert_series_equal(net1, net2)
    pd.testing.assert_series_equal(cost1, cost2)


def test_higher_turnover_higher_costs():
    """Higher turnover => higher costs (monotone)."""
    gross = pd.Series([0.01] * 10)
    low_turnover = pd.Series([0.05] * 10)
    high_turnover = pd.Series([0.20] * 10)
    _, cost_low = apply_costs(gross, low_turnover, fee_bps=30, slippage_bps=10)
    _, cost_high = apply_costs(gross, high_turnover, fee_bps=30, slippage_bps=10)
    assert cost_high.sum() > cost_low.sum()
    assert (cost_high >= cost_low).all()


def test_missing_liquidity_conservative_fallback():
    """Missing/zero/NaN liquidity uses conservative default slippage (50 bps)."""
    cfg = ExecutionCostConfig(
        slippage_bps=10,
        slippage_bps_missing_liquidity=DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY,
    )
    assert slippage_bps_from_liquidity(None, cfg) == DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY
    assert slippage_bps_from_liquidity(0, cfg) == DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY
    assert slippage_bps_from_liquidity(float("nan"), cfg) == DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY
    assert slippage_bps_from_liquidity(-1, cfg) == DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY


def test_portfolio_wrapper_consistent():
    """apply_costs_to_portfolio (portfolio module) matches ExecutionCostModel net result."""
    from crypto_analyzer.portfolio import apply_costs_to_portfolio

    gross = pd.Series([0.01, -0.005, 0.02], index=pd.date_range("2025-01-01", periods=3, freq="1h"))
    turnover = pd.Series([0.1, 0.05, 0.15], index=gross.index)
    net_wrapper = apply_costs_to_portfolio(gross, turnover, fee_bps=30, slippage_bps=10)
    net_direct, _ = apply_costs(gross, turnover, fee_bps=30, slippage_bps=10)
    pd.testing.assert_series_equal(net_wrapper, net_direct)


def test_execution_cost_model_with_slippage_series():
    """Per-period slippage series is applied when provided."""
    gross = pd.Series([0.01, 0.01], index=[0, 1])
    turnover = pd.Series([0.1, 0.1], index=[0, 1])
    slip_bps = pd.Series([10, 50], index=[0, 1])
    model = ExecutionCostModel(ExecutionCostConfig(fee_bps=30, slippage_bps=10))
    net, cost = model.apply_costs(gross, turnover, slippage_bps_series=slip_bps)
    # Second period has higher slippage => higher cost
    assert cost.iloc[1] > cost.iloc[0]
    assert net.iloc[1] < net.iloc[0]


def test_spread_increases_with_vol_and_lower_liquidity():
    """spread_bps_from_vol_liquidity: higher vol or lower liquidity -> higher spread."""
    low_vol = spread_bps_from_vol_liquidity(0.01, 1e6, base_spread_bps=10, spread_vol_scale=50)
    high_vol = spread_bps_from_vol_liquidity(0.05, 1e6, base_spread_bps=10, spread_vol_scale=50)
    assert high_vol > low_vol
    high_liq = spread_bps_from_vol_liquidity(0.02, 5e6, base_spread_bps=10, spread_vol_scale=50)
    low_liq = spread_bps_from_vol_liquidity(0.02, 100e3, base_spread_bps=10, spread_vol_scale=50)
    assert low_liq > high_liq


def test_impact_increases_with_participation():
    """impact_bps_from_participation: higher participation -> higher impact."""
    assert impact_bps_from_participation(1.0, 5.0, 10.0) == 5.0
    assert impact_bps_from_participation(5.0, 5.0, 10.0) == 25.0
    assert impact_bps_from_participation(20.0, 5.0, 10.0) == 50.0  # capped at 10%


def test_capacity_curve_multipliers():
    """Capacity curve: higher notional multiplier -> lower Sharpe (more turnover, more cost)."""
    np.random.seed(3)
    n = 100
    gross = pd.Series(np.random.randn(n) * 0.01)
    turnover = pd.Series(np.random.rand(n) * 0.2)
    df = capacity_curve(gross, turnover, multipliers=[1.0, 2.0, 5.0], freq="1h")
    assert len(df) == 3
    assert list(df["notional_multiplier"]) == [1.0, 2.0, 5.0]
    # Typically Sharpe decreases as multiplier increases (more cost)
    assert df["sharpe_annual"].iloc[0] >= df["sharpe_annual"].iloc[2] or np.isnan(df["sharpe_annual"].iloc[2])


def test_capacity_curve_extra_columns():
    """Capacity curve: required columns first; extra columns present (additive only, backwards compatible)."""
    n = 80
    gross = pd.Series(np.random.randn(n) * 0.01)
    turnover = pd.Series(np.ones(n) * 0.1)
    df = capacity_curve(gross, turnover, multipliers=[1.0, 2.0, 5.0], freq="1h")
    # CSV contract: first two columns in order
    assert list(df.columns[:2]) == CAPACITY_CURVE_REQUIRED_COLUMNS
    for col in CAPACITY_CURVE_REQUIRED_COLUMNS + CAPACITY_CURVE_EXTRA_COLUMNS:
        assert col in df.columns


def test_capacity_curve_monotone_sharpe_with_impact():
    """Synthetic: stable gross + constant turnover + costs increasing with m -> sharpe_annual non-increasing."""
    np.random.seed(42)
    n = 500  # enough points so Sharpe is stable (same freq pattern as stats stack)
    gross = pd.Series(0.001 + np.random.randn(n) * 0.002)  # positive mean, low vol so curve is stable
    turnover = pd.Series(np.ones(n) * 0.05)  # constant turnover
    df = capacity_curve(
        gross,
        turnover,
        multipliers=[1.0, 2.0, 4.0, 8.0],
        freq="1h",
        use_participation_impact=True,
        impact_bps_per_participation=5.0,
        max_participation_pct=10.0,
    )
    sharpes = df["sharpe_annual"].values
    for i in range(1, len(sharpes)):
        if not np.isnan(sharpes[i]) and not np.isnan(sharpes[i - 1]):
            assert sharpes[i] <= sharpes[i - 1] + 1e-9, "net Sharpe should be non-increasing with multiplier"
    assert not capacity_curve_is_non_monotone(df), "synthetic curve with impact should be monotone (non-increasing)"


def test_capacity_curve_is_non_monotone():
    """capacity_curve_is_non_monotone: False when monotone; True when any increase; False for empty/missing."""
    # Monotone decreasing
    df_mono = pd.DataFrame({"sharpe_annual": [0.5, 0.4, 0.3]})
    assert not capacity_curve_is_non_monotone(df_mono)
    # Non-monotone (one increase)
    df_up = pd.DataFrame({"sharpe_annual": [0.3, 0.5, 0.2]})
    assert capacity_curve_is_non_monotone(df_up)
    # NaN/inf ignored for comparison; only finite increase counts
    df_nan = pd.DataFrame({"sharpe_annual": [0.5, np.nan, 0.3]})
    assert not capacity_curve_is_non_monotone(df_nan)
    # Empty or no column
    assert not capacity_curve_is_non_monotone(pd.DataFrame())
    assert not capacity_curve_is_non_monotone(pd.DataFrame({"x": [1]}))
