"""
Unified execution cost model: fee + slippage applied to turnover.
Used by portfolio (research) and backtest. Deterministic only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
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


# Capacity curve: column order contract (additive columns after these two)
CAPACITY_CURVE_REQUIRED_COLUMNS = ["notional_multiplier", "sharpe_annual"]
CAPACITY_CURVE_EXTRA_COLUMNS = [
    "mean_ret_annual",
    "vol_annual",
    "avg_turnover",
    "est_cost_bps",
    "impact_bps",
    "spread_bps",
]


def capacity_curve(
    gross_returns: pd.Series,
    turnover_series: pd.Series,
    multipliers: Optional[list] = None,
    freq: str = "1h",
    fee_bps: float = 30.0,
    slippage_bps: float = 10.0,
    use_participation_impact: bool = True,
    impact_bps_per_participation: float = 5.0,
    max_participation_pct: float = 10.0,
    impact_k: float = 5.0,
    impact_alpha: float = 0.5,
    spread_bps: float = 0.0,
) -> pd.DataFrame:
    """
    Capacity curve: at each notional multiplier m, scale turnover (same pattern, higher size),
    apply size-aware costs so net returns degrade with m; return Sharpe (annualized) vs multiplier.

    Cost model (increases with m, sensitive to turnover):
    - Fee + slippage: fixed bps applied to turnover.
    - Spread: spread_bps (linear in turnover via apply_costs).
    - Impact: when use_participation_impact=True we have a participation proxy (m * mean(turnover) as %),
      so impact_bps = impact_bps_from_participation(participation_pct). When False, fallback to
      power-law impact_bps(m) = impact_k * (m ** impact_alpha). Cost = turnover * (fee + slippage + spread + impact_bps) / 10000.

    Contract: first two columns are notional_multiplier, sharpe_annual (order fixed). Extra columns additive only.
    Artifacts (e.g. execution_evidence cost_config) must describe the same model used here.
    """
    from .features import bars_per_year

    if multipliers is None:
        multipliers = [1.0, 2.0, 5.0]
    bars_yr = bars_per_year(freq)
    rows = []
    for mult in multipliers:
        scaled_turnover = turnover_series * mult
        avg_turnover = float(scaled_turnover.mean())
        if use_participation_impact:
            # Participation-based impact: proxy participation_pct = m * mean(turnover) as %, capped
            participation_pct = min(max_participation_pct, float(mult * turnover_series.mean() * 100.0))
            impact_bps = impact_bps_from_participation(
                participation_pct,
                impact_per_pct=impact_bps_per_participation,
                max_pct=max_participation_pct,
            )
        else:
            # Fallback: power-law in multiplier (no participation proxy)
            impact_bps = float(impact_k * (mult ** impact_alpha)) if impact_k else 0.0
        effective_slippage = slippage_bps + impact_bps + spread_bps
        net_ret, cost_series = apply_costs(
            gross_returns, scaled_turnover, fee_bps=fee_bps, slippage_bps=effective_slippage
        )
        n = net_ret.dropna()
        if len(n) < 2 or n.std(ddof=1) == 0:
            sharpe = float("nan")
        else:
            sharpe = float(n.mean() / n.std(ddof=1) * (bars_yr**0.5))
        mean_ret_annual = float(n.mean() * bars_yr) if len(n) else float("nan")
        vol_annual = float(n.std(ddof=1) * (bars_yr**0.5)) if len(n) >= 2 else float("nan")
        est_cost_bps = fee_bps + slippage_bps + impact_bps + spread_bps
        rows.append({
            "notional_multiplier": mult,
            "sharpe_annual": sharpe,
            "mean_ret_annual": mean_ret_annual,
            "vol_annual": vol_annual,
            "avg_turnover": avg_turnover,
            "est_cost_bps": est_cost_bps,
            "impact_bps": impact_bps,
            "spread_bps": spread_bps,
        })
    # Enforce column order: required first, then extra (additive only)
    col_order = CAPACITY_CURVE_REQUIRED_COLUMNS + CAPACITY_CURVE_EXTRA_COLUMNS
    return pd.DataFrame(rows, columns=col_order)


def capacity_curve_is_non_monotone(cap_df: pd.DataFrame) -> bool:
    """
    True if any strict increase in sharpe_annual: any(diff(sharpe_annual) > 0) on consecutive rows (finite values).
    Used to set non_monotone_capacity_curve_observed in stats_overview; does not enforce monotonicity.
    Logic is "local increase" (consecutive pairs only); when multiple curves are written, callers OR the flag.
    """
    if cap_df is None or cap_df.empty or "sharpe_annual" not in cap_df.columns:
        return False
    s = cap_df["sharpe_annual"].values
    for i in range(1, len(s)):
        a, b = s[i - 1], s[i]
        if np.isfinite(a) and np.isfinite(b) and b > a:
            return True
    return False
