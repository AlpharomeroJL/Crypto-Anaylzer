"""
Portfolio construction: vol targeting, risk parity, beta neutral, long/short.
Research-only; no execution or order routing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import periods_per_year

# Defaults (config can override via get_config().get("research", {}))
DEFAULT_TARGET_ANNUAL_VOL = 0.15
DEFAULT_MAX_WEIGHT_PER_ASSET = 0.25
MIN_ASSETS_FOR_PORTFOLIO = 3


def vol_target_weights(
    returns_window_df: pd.DataFrame,
    target_annual_vol: float = DEFAULT_TARGET_ANNUAL_VOL,
    freq: str = "1h",
) -> pd.Series:
    """
    Weights inversely proportional to volatility so portfolio vol ≈ target_annual_vol.
    weights_i ∝ 1/vol_i; then scale so that portfolio_vol = target. Uses latest rolling vol.
    """
    if returns_window_df.empty or returns_window_df.shape[1] < 1:
        return pd.Series(dtype=float)
    periods_yr = periods_per_year(freq)
    vol = returns_window_df.std(ddof=1)
    vol = vol.replace(0, np.nan)
    inv_vol = 1.0 / vol
    inv_vol = inv_vol.fillna(0)
    if inv_vol.sum() == 0:
        return pd.Series(index=returns_window_df.columns, data=0.0)
    w = inv_vol / inv_vol.sum()
    # Scale to target vol: port_vol = sqrt(w' V w) with V diagonal = vol_i^2 -> port_vol = sqrt(sum w_i^2 vol_i^2)
    port_vol = np.sqrt((w**2 * vol**2).sum())
    if port_vol > 0:
        scale = target_annual_vol / (port_vol * np.sqrt(periods_yr)) if periods_yr else 1.0
        w = w * scale
    w = w.clip(upper=1.0)
    if w.sum() > 1.0:
        w = w / w.sum()
    return w


def risk_parity_weights(cov_matrix: pd.DataFrame) -> pd.Series:
    """
    Simple risk parity: weights proportional to 1/vol (inverse vol). Fallback when full iterative RP not used.
    cov_matrix: square DataFrame; we use diagonal (variances) for inverse-vol weights.
    """
    if cov_matrix.empty or cov_matrix.shape[0] != cov_matrix.shape[1]:
        return pd.Series(dtype=float)
    vol = np.sqrt(np.diag(cov_matrix))
    vol = np.where(vol > 0, vol, np.nan)
    inv_vol = 1.0 / vol
    inv_vol = np.nan_to_num(inv_vol, nan=0.0)
    if inv_vol.sum() == 0:
        return pd.Series(index=cov_matrix.index, data=1.0 / len(cov_matrix))
    w = inv_vol / inv_vol.sum()
    return pd.Series(w, index=cov_matrix.index)


def beta_neutralize_weights(
    weights: pd.Series,
    betas: pd.Series,
    target_beta: float = 0.0,
) -> pd.Series:
    """
    Adjust weights so portfolio beta = target_beta. Assumes betas are vs single factor.
    w_new = w - (sum(w*beta) - target_beta) * adjustment. Simple: scale long/short or add cash beta.
    Here we use: port_beta = w @ beta. To get port_beta = 0, we need sum(w_i * beta_i) = 0.
    One approach: subtract from each w_i a multiple of beta_i so that sum(w*beta)=0.
    Let c such that sum((w - c*beta)*beta) = 0 -> sum(w*beta) - c*sum(beta^2) = 0 -> c = sum(w*beta)/sum(beta^2).
    Then w_adj = w - c*beta. Clamp to non-negative if long-only; for L/S we allow negative.
    """
    if weights.empty or betas.empty:
        return weights
    common = weights.index.intersection(betas.index)
    if len(common) < 2:
        return weights
    w = weights.reindex(common).fillna(0)
    b = betas.reindex(common).fillna(0)
    port_beta = (w * b).sum()
    beta_sq_sum = (b**2).sum()
    if beta_sq_sum == 0:
        return weights
    c = (port_beta - target_beta) / beta_sq_sum
    w_adj = w - c * b
    # Allow negative (L/S); do not clip to [0,1] so that beta neutral works
    out = weights.copy()
    out.loc[common] = w_adj.values
    return out


def long_short_from_ranks(
    ranks_df: pd.DataFrame,
    top_k: int,
    bottom_k: int,
    gross_leverage: float = 1.0,
) -> pd.DataFrame:
    """
    Weights panel: at each timestamp, long top_k (equal weight), short bottom_k (equal weight).
    Long weight each = (gross_leverage/2) / top_k, short each = -(gross_leverage/2) / bottom_k.
    Returns DataFrame index=ts_utc, columns=asset_id, values=weight.
    """
    if ranks_df.empty or ranks_df.shape[1] < 2:
        return pd.DataFrame()
    w_plus = (gross_leverage / 2.0) / max(1, top_k)
    w_minus = -(gross_leverage / 2.0) / max(1, bottom_k)
    out = pd.DataFrame(0.0, index=ranks_df.index, columns=ranks_df.columns)
    for t in ranks_df.index:
        r = ranks_df.loc[t].dropna()
        if len(r) < top_k + bottom_k:
            continue
        top = r.nlargest(top_k).index
        bot = r.nsmallest(bottom_k).index
        out.loc[t, top] = w_plus
        out.loc[t, bot] = w_minus
    return out


def apply_costs_to_portfolio(
    pnl_series: pd.Series,
    turnover_series: pd.Series,
    fee_bps: float,
    slippage_bps: float,
) -> pd.Series:
    """
    Net PnL after costs: cost per period = turnover * (fee_bps + slippage_bps) / 10000.
    Delegates to ExecutionCostModel. pnl_series and turnover_series must be aligned (same index).
    """
    from .execution_cost import apply_costs

    net, _ = apply_costs(pnl_series, turnover_series, fee_bps=fee_bps, slippage_bps=slippage_bps)
    return net


def portfolio_returns_from_weights(
    weights_df: pd.DataFrame,
    returns_df: pd.DataFrame,
) -> pd.Series:
    """Period portfolio return: at each t, ret_t = sum(weight_t * return_t). Weights and returns aligned on index."""
    common = weights_df.index.intersection(returns_df.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    cols = weights_df.columns.intersection(returns_df.columns)
    if len(cols) == 0:
        return pd.Series(dtype=float)
    w = weights_df.loc[common, cols].fillna(0)
    r = returns_df.loc[common, cols].fillna(0)
    return (w * r).sum(axis=1)


def constrain_weights(
    weights: pd.Series,
    max_weight: float = DEFAULT_MAX_WEIGHT_PER_ASSET,
) -> pd.Series:
    """Clip weights to [-max_weight, max_weight] and renormalize to sum 1 (or keep L/S sum)."""
    w = weights.clip(lower=-max_weight, upper=max_weight)
    return w


def turnover_from_weights(weights_df: pd.DataFrame) -> pd.Series:
    """Turnover at each date: sum of abs(weight change) from previous period."""
    if weights_df.empty or len(weights_df) < 2:
        return pd.Series(dtype=float)
    diff = weights_df.diff().abs()
    return diff.sum(axis=1).fillna(0)
