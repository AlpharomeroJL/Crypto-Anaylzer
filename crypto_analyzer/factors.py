"""
Factor and residual returns: BTC_spot + ETH_spot factors, OLS betas, residual returns/vol.
Research-only; no execution.
"""
from __future__ import annotations

from typing import List, Optional

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
    # add intercept column
    ones = np.ones((len(X_mat), 1))
    X_with_const = np.hstack([ones, X_mat])
    try:
        # (X'X)^{-1} X' y
        xtx = X_with_const.T @ X_with_const
        xty = X_with_const.T @ y_vec
        sol = np.linalg.solve(xtx, xty)
        alpha = float(sol[0])
        betas = sol[1:]
        return betas, alpha
    except np.linalg.LinAlgError:
        return np.array([]), np.nan


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
