"""
Unified execution cost model: fee + slippage applied to turnover.
Used by portfolio (research) and backtest. Deterministic only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

# Conservative fallback when liquidity is missing (documented)
DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY = 50.0
LIQUIDITY_SLIPPAGE_SCALE = 1e6  # 1M USD liquidity = baseline


@dataclass
class ExecutionCostConfig:
    """Fee and slippage parameters."""

    fee_bps: float = 30.0
    slippage_bps: float = 10.0
    # When using liquidity-based proxy: missing/zero liquidity uses this (conservative)
    slippage_bps_missing_liquidity: float = DEFAULT_SLIPPAGE_BPS_WHEN_MISSING_LIQUIDITY
    # Spread proxy: scale spread by vol (e.g. vol_pct * spread_vol_scale -> extra bps). 0 = disabled.
    spread_vol_scale: float = 0.0
    # Participation-based impact: impact_bps = participation_ratio * impact_per_participation, capped.
    use_participation_impact: bool = False
    impact_bps_per_participation: float = 5.0  # bps per 1% participation
    max_participation_pct: float = 10.0  # cap participation for impact calc


def spread_bps_from_vol_liquidity(
    vol_proxy: float,
    liquidity_usd: float,
    base_spread_bps: float = 10.0,
    spread_vol_scale: float = 50.0,
) -> float:
    """
    Proxy spread: wider when vol is high or liquidity is low.
    spread_bps = base_spread_bps + vol_proxy * spread_vol_scale + liquidity component.
    Liquidity component uses same idea as slippage_bps_from_liquidity.
    """
    if vol_proxy is None or pd.isna(vol_proxy):
        vol_proxy = 0.0
    spread = base_spread_bps + vol_proxy * spread_vol_scale
    if liquidity_usd is not None and not pd.isna(liquidity_usd) and liquidity_usd > 0:
        # Lower liquidity -> higher spread (e.g. 1M USD -> 0 extra, 100k -> ~30 bps extra)
        spread += min(50.0, 1e6 / (liquidity_usd + 1e4))
    return max(0.0, spread)


def impact_bps_from_participation(
    participation_pct: float,
    impact_per_pct: float = 5.0,
    max_pct: float = 10.0,
) -> float:
    """
    Size-dependent impact: cost increases with participation (trade notional / ADV proxy).
    Linear in participation up to max_pct, then flat.
    """
    if participation_pct is None or pd.isna(participation_pct) or participation_pct <= 0:
        return 0.0
    p = min(float(participation_pct), max_pct)
    return p * impact_per_pct


def slippage_bps_from_liquidity(liquidity_usd: float, config: Optional[ExecutionCostConfig] = None) -> float:
    """
    Proxy: higher slippage when liquidity is lower. Double slippage when liq halves.
    Missing/zero/NaN liquidity returns config.slippage_bps_missing_liquidity (default 50 bps).
    """
    cfg = config or ExecutionCostConfig()
    if liquidity_usd is None or pd.isna(liquidity_usd) or liquidity_usd <= 0:
        return cfg.slippage_bps_missing_liquidity
    return min(
        cfg.slippage_bps_missing_liquidity,
        cfg.slippage_bps * (LIQUIDITY_SLIPPAGE_SCALE / liquidity_usd) ** 0.5,
    )


class ExecutionCostModel:
    """
    Single place for applying costs to gross returns.
    apply_costs(gross_returns, turnover_series, ...) -> (net_returns, cost_breakdown).
    """

    def __init__(self, config: Optional[ExecutionCostConfig] = None):
        self.config = config or ExecutionCostConfig()

    def apply_costs(
        self,
        gross_returns: pd.Series,
        turnover_series: pd.Series,
        slippage_bps_series: Optional[pd.Series] = None,
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Apply fee + slippage to turnover. Deterministic.

        gross_returns: period gross returns (e.g. strategy or portfolio).
        turnover_series: period turnover (same index as gross_returns).
        slippage_bps_series: optional per-period slippage bps (e.g. from liquidity proxy).
          If None, use fixed config.slippage_bps.

        Returns (net_returns, cost_series). cost_series is cost in return units per period.
        """
        if gross_returns.empty:
            return gross_returns.copy(), pd.Series(dtype=float)
        turnover = turnover_series.reindex(gross_returns.index).fillna(0)
        fee_bps = self.config.fee_bps
        if slippage_bps_series is not None:
            slip_bps = slippage_bps_series.reindex(gross_returns.index).fillna(
                self.config.slippage_bps_missing_liquidity
            )
        else:
            slip_bps = self.config.slippage_bps
        cost_bps = fee_bps + slip_bps
        if isinstance(cost_bps, pd.Series):
            cost = turnover * (cost_bps / 10_000)
        else:
            cost = turnover * (cost_bps / 10_000)
        net_returns = gross_returns - cost
        return net_returns, cost


def apply_costs(
    gross_returns: pd.Series,
    turnover_series: pd.Series,
    fee_bps: float = 30.0,
    slippage_bps: float = 10.0,
    slippage_bps_series: Optional[pd.Series] = None,
) -> Tuple[pd.Series, pd.Series]:
    """
    One-shot apply costs. Uses ExecutionCostModel with given fee/slippage.
    Returns (net_returns, cost_series).
    """
    cfg = ExecutionCostConfig(fee_bps=fee_bps, slippage_bps=slippage_bps)
    model = ExecutionCostModel(cfg)
    return model.apply_costs(gross_returns, turnover_series, slippage_bps_series=slippage_bps_series)


def capacity_curve(
    gross_returns: pd.Series,
    turnover_series: pd.Series,
    multipliers: Optional[list] = None,
    freq: str = "1h",
    fee_bps: float = 30.0,
    slippage_bps: float = 10.0,
) -> pd.DataFrame:
    """
    Minimal capacity curve: at each notional multiplier, scale turnover (same pattern, higher size)
    and apply costs; return Sharpe (annualized) vs multiplier. Higher multiplier -> higher turnover
    -> higher costs -> lower net Sharpe typically.
    """
    from .features import bars_per_year

    if multipliers is None:
        multipliers = [1.0, 2.0, 5.0]
    rows = []
    for mult in multipliers:
        scaled_turnover = turnover_series * mult
        net_ret, _ = apply_costs(gross_returns, scaled_turnover, fee_bps=fee_bps, slippage_bps=slippage_bps)
        n = net_ret.dropna()
        if len(n) < 2 or n.std(ddof=1) == 0:
            sharpe = float("nan")
        else:
            bars_yr = bars_per_year(freq)
            sharpe = float(n.mean() / n.std(ddof=1) * (bars_yr**0.5))
        rows.append({"notional_multiplier": mult, "sharpe_annual": sharpe})
    return pd.DataFrame(rows)
