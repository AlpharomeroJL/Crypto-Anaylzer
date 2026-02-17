"""
Covariance estimation and shrinkage for portfolio risk. Research-only.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    from sklearn.covariance import LedoitWolf
    HAS_SKLEARN_LW = True
except ImportError:
    HAS_SKLEARN_LW = False


def ewma_cov(returns_window_df: pd.DataFrame, halflife: float) -> pd.DataFrame:
    """
    EWMA covariance matrix over the given returns window.
    Weights decay by halflife (in observations); output is (N x N) DataFrame.
    """
    if returns_window_df.empty or len(returns_window_df) < 2:
        return pd.DataFrame()
    R = returns_window_df.dropna(axis=1, how="all")
    if R.shape[1] < 1:
        return pd.DataFrame()
    # Weight: recent = higher; w_t = (1 - alpha) * alpha^(T-t), alpha = 0.5^(1/halflife)
    alpha = 0.5 ** (1.0 / max(halflife, 1e-6))
    n = len(R)
    weights = np.array([alpha ** (n - 1 - i) for i in range(n)])
    weights = weights / weights.sum()
    centered = R - R.mean(axis=0)
    cov = (centered.T * weights) @ centered
    return cov


def shrink_cov_to_diagonal(cov: pd.DataFrame, shrink: float = 0.2) -> pd.DataFrame:
    """
    Shrink covariance toward its diagonal: (1 - shrink) * cov + shrink * diag(cov).
    shrink in [0, 1]; 0 = no shrinkage, 1 = diagonal.
    """
    if cov.empty:
        return cov.copy()
    c = cov.values.copy()
    d = np.diag(c)
    out = (1.0 - shrink) * c + shrink * np.diag(d)
    return pd.DataFrame(out, index=cov.index, columns=cov.columns)


def ledoit_wolf_shrinkage(returns_window_df: pd.DataFrame) -> pd.DataFrame:
    """
    Ledoit-Wolf shrinkage covariance. Uses sklearn.covariance.LedoitWolf if available;
    otherwise diagonal-shrink fallback with shrink=0.5 (see comment in code).
    """
    if returns_window_df.empty or len(returns_window_df) < 2:
        return pd.DataFrame()
    R = returns_window_df.dropna(axis=1, how="all")
    if R.shape[1] < 1:
        return pd.DataFrame()
    if HAS_SKLEARN_LW:
        lw = LedoitWolf().fit(R.values)
        return pd.DataFrame(lw.covariance_, index=R.columns, columns=R.columns)
    # Fallback: diagonal shrinkage (no sklearn). Conservative shrink toward diagonal.
    sample = R.cov()
    return shrink_cov_to_diagonal(sample, shrink=0.5)


def ensure_psd(cov: pd.DataFrame) -> pd.DataFrame:
    """
    Nearest PSD matrix via eigenvalue clipping: set negative eigenvalues to small positive.
    """
    if cov.empty:
        return cov.copy()
    idx = cov.index
    cols = cov.columns
    C = cov.values.astype(float)
    C = (C + C.T) / 2.0
    try:
        eigvals, eigvecs = np.linalg.eigh(C)
    except np.linalg.LinAlgError:
        return cov.copy()
    eigvals = np.maximum(eigvals, 1e-10)
    out = eigvecs @ np.diag(eigvals) @ eigvecs.T
    return pd.DataFrame(out, index=idx, columns=cols)


def estimate_covariance(
    returns_window_df: pd.DataFrame,
    method: str = "ewma",
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Estimate covariance matrix. method: 'ewma' | 'lw' | 'shrink'.
    For ewma: halflife (default 24). For shrink: uses sample cov then shrink_cov_to_diagonal with shrink (default 0.2).
    """
    if returns_window_df.empty:
        return pd.DataFrame()
    if method == "ewma":
        halflife = kwargs.get("halflife", 24.0)
        cov = ewma_cov(returns_window_df, halflife)
    elif method == "lw":
        cov = ledoit_wolf_shrinkage(returns_window_df)
    elif method == "shrink":
        sample = returns_window_df.cov()
        shrink = kwargs.get("shrink", 0.2)
        cov = shrink_cov_to_diagonal(sample, shrink=shrink)
    else:
        cov = returns_window_df.cov()
    return ensure_psd(cov)
