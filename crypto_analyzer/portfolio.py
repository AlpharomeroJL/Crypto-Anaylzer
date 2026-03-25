"""
Portfolio construction: vol targeting, risk parity, beta neutral, long/short.
Research-only; no execution or order routing.
"""

from __future__ import annotations

from typing import Optional

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


def adaptive_long_short_k(n_assets: int, top_k: int, bottom_k: int) -> tuple[int, int]:
    """
    Cap bucket sizes on small cross-sections so long+short does not consume most names.

    Rule: each leg at most max(1, n // 4), then min with requested k. Keeps a middle cohort on
    ~9-name panels (e.g. k<=2 vs default 3) to reduce brittle all-in long/short churn.
    """
    if n_assets < 2:
        return max(1, top_k), max(1, bottom_k)
    cap = max(1, n_assets // 4)
    tk = max(1, min(int(top_k), cap))
    bk = max(1, min(int(bottom_k), cap))
    if tk + bk > n_assets:
        # Last resort: shrink larger leg
        while tk + bk > n_assets and (tk > 1 or bk > 1):
            if tk >= bk and tk > 1:
                tk -= 1
            elif bk > 1:
                bk -= 1
    return tk, bk


def long_short_from_ranks(
    ranks_df: pd.DataFrame,
    top_k: int,
    bottom_k: int,
    gross_leverage: float = 1.0,
    signal_df: Optional[pd.DataFrame] = None,
    within_bucket: str = "equal",
) -> pd.DataFrame:
    """
    Weights panel: at each timestamp, long top_k, short bottom_k (by cross-sectional rank pct).

    within_bucket:
      - ``equal``: equal weight within each leg (legacy).
      - ``signal_abs``: weight by absolute pre-rank signal magnitude within each leg (requires
        ``signal_df`` aligned to ranks_df); preserves dollar-neutral gross leverage.

    Long leg sums to +gross_leverage/2, short leg to -gross_leverage/2.
    Returns DataFrame index=ts_utc, columns=asset_id, values=weight.
    """
    if ranks_df.empty or ranks_df.shape[1] < 2:
        return pd.DataFrame()
    use_signal = within_bucket == "signal_abs" and signal_df is not None and not signal_df.empty
    w_plus_eq = (gross_leverage / 2.0) / max(1, top_k)
    w_minus_eq = -(gross_leverage / 2.0) / max(1, bottom_k)
    out = pd.DataFrame(0.0, index=ranks_df.index, columns=ranks_df.columns)
    for t in ranks_df.index:
        r = ranks_df.loc[t].dropna()
        if len(r) < top_k + bottom_k:
            continue
        top = r.nlargest(top_k).index
        bot = r.nsmallest(bottom_k).index
        if not use_signal:
            out.loc[t, top] = w_plus_eq
            out.loc[t, bot] = w_minus_eq
            continue
        srow = signal_df.loc[t].reindex(r.index).astype(float)
        long_w = _bucket_weights_abs(srow.loc[top], gross_leverage / 2.0)
        short_w = _bucket_weights_abs(srow.loc[bot], gross_leverage / 2.0)
        out.loc[t, long_w.index] = long_w.values
        out.loc[t, short_w.index] = -short_w.values
    return out


def _bucket_weights_abs(s: pd.Series, gross_half: float) -> pd.Series:
    """Nonnegative weights summing to gross_half from absolute signal values; equal fallback."""
    s = s.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    a = s.abs().astype(float)
    a = a.replace(0.0, np.nan)
    ssum = float(a.sum())
    if not np.isfinite(ssum) or ssum <= 0:
        n = len(a)
        return pd.Series(gross_half / max(1, n), index=a.index)
    w = a / ssum * gross_half
    return w.fillna(0.0)


def ema_smooth_weights(weights_df: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """
    Exponential smoothing of target weights along time (reduces turnover; research-only).

    w_smooth[t] = alpha * w[t] + (1-alpha) * w_smooth[t-1]. First row unchanged.
    """
    if weights_df.empty or alpha <= 0.0:
        return weights_df
    if alpha > 1.0:
        alpha = 1.0
    out = weights_df.copy()
    arr = out.to_numpy(dtype=float)
    for i in range(1, len(out)):
        arr[i] = alpha * arr[i] + (1.0 - alpha) * arr[i - 1]
    return pd.DataFrame(arr, index=out.index, columns=out.columns)


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
