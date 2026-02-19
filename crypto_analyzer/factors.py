"""
Factor and residual returns: BTC_spot + ETH_spot factors, OLS betas, residual returns/vol.
Rolling multi-factor OLS regression for systematic factor exposure decomposition.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def build_factor_matrix(
    returns_df: pd.DataFrame,
    factor_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build aligned factor return matrix (index = returns_df.index).
    factor_cols default: ["BTC_spot", "ETH_spot"]. Drops rows where any factor is NaN.
    """
    if factor_cols is None:
        factor_cols = ["BTC_spot", "ETH_spot"]
    available = [c for c in factor_cols if c in returns_df.columns]
    if not available:
        return pd.DataFrame()
    X = returns_df[available].copy()
    X = X.dropna(how="any")
    return X


def fit_ols(X: np.ndarray, y: np.ndarray, add_const: bool = True) -> Tuple[np.ndarray, float, float]:
    """
    Fit OLS via numpy.linalg.lstsq. No sklearn dependency.
    Returns (betas, intercept, r_squared).
    If add_const, prepends a column of ones to X.
    """
    if len(y) < 2 or X.shape[0] < 2:
        k = X.shape[1] if X.ndim == 2 else 1
        return np.full(k, np.nan), np.nan, np.nan
    X_ = X.copy() if X.ndim == 2 else X.reshape(-1, 1)
    if add_const:
        ones = np.ones((X_.shape[0], 1))
        X_ = np.hstack([ones, X_])
    try:
        sol, residuals, rank, sv = np.linalg.lstsq(X_, y, rcond=None)
    except np.linalg.LinAlgError:
        k = X.shape[1] if X.ndim == 2 else 1
        return np.full(k, np.nan), np.nan, np.nan
    if add_const:
        intercept = float(sol[0])
        betas = sol[1:]
    else:
        intercept = 0.0
        betas = sol
    y_hat = X_ @ sol
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return betas, intercept, r2


def compute_ols_betas(y: pd.Series, X: pd.DataFrame) -> tuple:
    """
    OLS: y = X @ beta + alpha. Uses numpy only.
    Returns (betas array, intercept/alpha). Aligns y and X on index; drops NaN.
    """
    common = y.dropna().index.intersection(X.dropna(how="any").index)
    if len(common) < 2 or X.loc[common].empty:
        return np.array([]), np.nan
    y_a = y.reindex(common).dropna()
    X_a = X.reindex(common).dropna(how="any")
    idx = y_a.index.intersection(X_a.index)
    if len(idx) < 2:
        return np.array([]), np.nan
    y_vec = y_a.loc[idx].values.astype(float)
    X_mat = X_a.loc[idx].values.astype(float)
    ones = np.ones((len(X_mat), 1))
    X_with_const = np.hstack([ones, X_mat])
    try:
        xtx = X_with_const.T @ X_with_const
        xty = X_with_const.T @ y_vec
        sol = np.linalg.solve(xtx, xty)
        alpha = float(sol[0])
        betas = sol[1:]
        return betas, alpha
    except np.linalg.LinAlgError:
        return np.array([]), np.nan


def rolling_multifactor_ols(
    returns_df: pd.DataFrame,
    factor_df: pd.DataFrame,
    window: int = 72,
    min_obs: int = 24,
    add_const: bool = True,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Rolling multi-factor OLS regression for each asset column in returns_df.

    Degrades gracefully: if a factor column is missing from factor_df, uses
    whatever factors are available (BTC-only fallback).

    Returns:
        betas_dict: {factor_name: DataFrame(index=time, columns=assets)} of rolling betas
        r2_df: DataFrame(index=time, columns=assets) of rolling R^2
        residual_df: DataFrame(index=time, columns=assets) of residual returns
    """
    desired_factors = ["BTC_spot", "ETH_spot"]
    available_factors = [f for f in desired_factors if f in factor_df.columns]
    if not available_factors:
        available_factors = [c for c in factor_df.columns if c in returns_df.columns]
    if not available_factors:
        empty = pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
        return {}, empty.copy(), empty.copy()

    factor_sub = factor_df[available_factors].copy()

    asset_cols = [c for c in returns_df.columns if c not in available_factors]
    if not asset_cols:
        empty = pd.DataFrame(index=returns_df.index, columns=[], dtype=float)
        return {}, empty.copy(), empty.copy()

    common_idx = returns_df.index.intersection(factor_sub.dropna(how="any").index)
    if len(common_idx) < min_obs:
        empty = pd.DataFrame(index=returns_df.index, columns=asset_cols, dtype=float)
        return {f: empty.copy() for f in available_factors}, empty.copy(), empty.copy()

    betas_dict: Dict[str, pd.DataFrame] = {
        f: pd.DataFrame(np.nan, index=common_idx, columns=asset_cols) for f in available_factors
    }
    r2_df = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols)
    residual_df = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols)

    F_all = factor_sub.reindex(common_idx).values.astype(float)

    for col in asset_cols:
        y_all = returns_df[col].reindex(common_idx).values.astype(float)

        for i in range(len(common_idx)):
            start = max(0, i - window + 1)
            y_win = y_all[start : i + 1]
            F_win = F_all[start : i + 1]

            valid = ~(np.isnan(y_win) | np.any(np.isnan(F_win), axis=1))
            if valid.sum() < min_obs:
                continue

            y_v = y_win[valid]
            F_v = F_win[valid]

            betas, intercept, r2 = fit_ols(F_v, y_v, add_const=add_const)
            if np.any(np.isnan(betas)):
                continue

            for j, fname in enumerate(available_factors):
                betas_dict[fname].iloc[i, betas_dict[fname].columns.get_loc(col)] = betas[j]
            r2_df.iloc[i, r2_df.columns.get_loc(col)] = r2

            y_point = y_all[i]
            f_point = F_all[i]
            if not np.isnan(y_point) and not np.any(np.isnan(f_point)):
                fitted = intercept + float(f_point @ betas)
                residual_df.iloc[i, residual_df.columns.get_loc(col)] = y_point - fitted

    return betas_dict, r2_df, residual_df


def compute_residual_returns(
    asset_ret: pd.Series,
    factor_returns_df: pd.DataFrame,
    betas: np.ndarray,
    intercept: float,
) -> pd.Series:
    """
    Residual log return: r_resid = r_asset - (intercept + factor_returns @ betas).
    factor_returns_df columns order must match betas (e.g. BTC_spot, ETH_spot).
    """
    if factor_returns_df.empty or len(betas) == 0:
        return pd.Series(dtype=float)
    common = asset_ret.dropna().index.intersection(factor_returns_df.dropna(how="any").index)
    if len(common) < 1:
        return pd.Series(dtype=float)
    cols = factor_returns_df.columns.tolist()
    if len(cols) != len(betas):
        return pd.Series(dtype=float)
    r_asset = asset_ret.reindex(common).dropna()
    F = factor_returns_df.reindex(common).dropna(how="any")
    idx = r_asset.index.intersection(F.index)
    if len(idx) < 1:
        return pd.Series(dtype=float)
    r = r_asset.loc[idx].values
    f_mat = F.loc[idx].values
    fitted = intercept + f_mat @ betas
    resid = r - fitted
    return pd.Series(resid, index=idx)


def compute_residual_lookback_return(resid_log_ret: pd.Series, lookback_bars: int) -> float:
    """Return over last lookback_bars from residual log returns: exp(sum(resid)) - 1."""
    r = resid_log_ret.dropna().tail(lookback_bars)
    if len(r) < lookback_bars or lookback_bars <= 0:
        return np.nan
    return float(np.exp(r.sum()) - 1.0)


def compute_residual_vol(resid_log_ret: pd.Series, window_bars: int, freq: str) -> float:
    """Annualized volatility of residual log returns (rolling window)."""
    from .features import periods_per_year

    r = resid_log_ret.dropna()
    if len(r) < window_bars:
        return np.nan
    vol = r.rolling(window_bars).std(ddof=1).iloc[-1]
    if pd.isna(vol) or vol == 0:
        return np.nan
    periods_yr = periods_per_year(freq)
    return float(vol * np.sqrt(periods_yr))
