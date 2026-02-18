"""
Constrained QP portfolio optimizer using scipy.optimize.
Research-only; no execution.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .risk_model import ensure_psd


def _rank_fallback(
    signal: pd.Series,
    gross_leverage: float,
    net_exposure: float,
) -> pd.Series:
    """Rank-based equal-weight fallback when optimizer fails."""
    if signal.empty:
        return pd.Series(dtype=float)
    n = len(signal)
    ranks = signal.rank(method="average", pct=True)
    mid = ranks.median()
    raw = np.where(ranks >= mid, 1.0, -1.0)
    w = pd.Series(raw, index=signal.index, dtype=float)

    n_pos = (w > 0).sum()
    n_neg = (w < 0).sum()
    if n_pos > 0:
        w[w > 0] = 1.0 / n_pos
    if n_neg > 0:
        w[w < 0] = -1.0 / n_neg

    current_gross = w.abs().sum()
    if current_gross > 1e-12:
        w = w * (gross_leverage / current_gross)

    shift = net_exposure - w.sum()
    w = w + shift / n
    return w


def optimize_ls_qp(
    signal: pd.Series,
    cov: pd.DataFrame,
    gross_leverage: float = 1.0,
    net_exposure: float = 0.0,
    max_weight: float = 0.10,
    long_only: bool = False,
    risk_aversion: float = 1.0,
    l2_reg: float = 1e-6,
) -> pd.Series:
    """
    Solve:  min  risk_aversion * w^T @ cov @ w  -  signal^T @ w  +  l2_reg * ||w||^2
    s.t.    sum(w) == net_exposure
            sum(|w|) <= gross_leverage   (variable splitting)
            -max_weight <= w_i <= max_weight  (0 <= w_i if long_only)

    Returns pd.Series of weights indexed like signal.
    On failure, falls back to rank-based equal-weight L/S.
    """
    if signal.empty or len(signal) < 2:
        return _rank_fallback(signal, gross_leverage, net_exposure)

    common = signal.index.intersection(cov.index).intersection(cov.columns)
    if len(common) < 2:
        return _rank_fallback(signal, gross_leverage, net_exposure)

    sig = signal.reindex(common).fillna(0.0)
    cov_aligned = cov.reindex(index=common, columns=common).fillna(0.0)

    try:
        cov_psd = ensure_psd(cov_aligned)
        Q = cov_psd.values.astype(float)
    except Exception:
        return _rank_fallback(signal, gross_leverage, net_exposure)

    s = sig.values.astype(float)
    n = len(common)

    reg_matrix = np.eye(n) * l2_reg
    H = risk_aversion * Q + reg_matrix
    H_full = np.block([
        [H, -H],
        [-H, H],
    ])

    s_full = np.concatenate([s, -s])

    def objective(x: np.ndarray) -> float:
        """QP objective in split variables."""
        return 0.5 * x @ H_full @ x - s_full @ x

    def grad(x: np.ndarray) -> np.ndarray:
        """Gradient of the QP objective."""
        return H_full @ x - s_full

    x0_w = _rank_fallback(sig, gross_leverage, net_exposure).reindex(common).fillna(0.0).values
    x0_plus = np.maximum(x0_w, 0.0)
    x0_minus = np.maximum(-x0_w, 0.0)
    x0 = np.concatenate([x0_plus, x0_minus])

    if long_only:
        bounds = [(0.0, max_weight)] * n + [(0.0, 0.0)] * n
    else:
        bounds = [(0.0, max_weight)] * (2 * n)

    constraints = [
        {
            "type": "eq",
            "fun": lambda x: np.sum(x[:n]) - np.sum(x[n:]) - net_exposure,
        },
        {
            "type": "ineq",
            "fun": lambda x: gross_leverage - np.sum(x[:n]) - np.sum(x[n:]),
        },
    ]

    try:
        result = minimize(
            objective,
            x0,
            jac=grad,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )
        if not result.success:
            return _rank_fallback(signal, gross_leverage, net_exposure)
        w = result.x[:n] - result.x[n:]
    except Exception:
        return _rank_fallback(signal, gross_leverage, net_exposure)

    return pd.Series(w, index=common)
