"""
Dynamic (Kalman/RLS-style) beta estimator for factor model materialization.
Causal: beta at t uses only data up to t - as_of_lag_bars. No new deps; matches causal_rolling_ols output shape.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Minimum innovation variance to avoid division by zero / ill-conditioned gain (no new deps)
_S_MIN = 1e-12


def dynamic_beta_rls(
    returns_df: pd.DataFrame,
    factor_cols: List[str],
    *,
    as_of_lag_bars: int,
    add_const: bool = True,
    window_bars: int = 72,
    min_obs: int = 24,
    params: Optional[dict] = None,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Recursive Least Squares (RLS) / Kalman-style time-varying betas. Causal: at row i
    we use the state after processing observations with index <= i - as_of_lag_bars.

    Returns (betas_dict, r2_df, residual_df, alpha_df) matching causal_rolling_ols:
    - betas_dict: dict[factor_name] -> DataFrame(index=common_idx, columns=asset_cols)
    - r2_df, residual_df, alpha_df: DataFrame(index=common_idx, columns=asset_cols)
    """
    if as_of_lag_bars < 1:
        raise ValueError("as_of_lag_bars must be >= 1 to avoid fit including t+1 (no lookahead)")

    params = params or {}
    process_var = float(params.get("process_var", 1e-5))
    obs_var = float(params.get("obs_var", 1e-4))
    init_P_scale = float(params.get("init_P", 1.0))
    forgetting_factor = params.get("forgetting_factor")
    if forgetting_factor is not None:
        forgetting_factor = float(forgetting_factor)
        if not (0 < forgetting_factor <= 1):
            forgetting_factor = None

    available = [c for c in factor_cols if c in returns_df.columns]
    if not available:
        return (
            {},
            pd.DataFrame(index=returns_df.index),
            pd.DataFrame(index=returns_df.index),
            pd.DataFrame(index=returns_df.index),
        )
    asset_cols = sorted([c for c in returns_df.columns if c not in available])
    if not asset_cols:
        return (
            {},
            pd.DataFrame(index=returns_df.index),
            pd.DataFrame(index=returns_df.index),
            pd.DataFrame(index=returns_df.index),
        )
    common_idx = returns_df.index.intersection(returns_df[available].dropna(how="any").index)
    common_idx = common_idx.sort_values()
    if len(common_idx) < min_obs + as_of_lag_bars:
        empty = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols, dtype=float)
        return {f: empty.copy() for f in sorted(available)}, empty.copy(), empty.copy(), empty.copy()

    F_all = returns_df[available].reindex(common_idx).values.astype(float)
    n_obs = len(common_idx)
    if add_const:
        X_all = np.column_stack([np.ones(n_obs), F_all])
    else:
        X_all = F_all
    n_k = X_all.shape[1]

    betas_dict: Dict[str, pd.DataFrame] = {
        f: pd.DataFrame(np.nan, index=common_idx, columns=asset_cols) for f in sorted(available)
    }
    r2_df = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols)
    residual_df = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols)
    alpha_df = pd.DataFrame(np.nan, index=common_idx, columns=asset_cols)

    for col in asset_cols:
        y_all = returns_df[col].reindex(common_idx).values.astype(float)
        beta = np.zeros(n_k)
        P = np.eye(n_k) * init_P_scale
        valid_count = 0
        y_hist: List[float] = []
        resid_hist: List[float] = []

        for i in range(n_obs):
            y_i = y_all[i]
            x_i = X_all[i]
            if np.isnan(y_i) or np.any(np.isnan(x_i)):
                continue
            x_i = x_i.reshape(-1, 1)
            pred = (beta @ x_i).item()
            resid_i = y_i - pred

            if forgetting_factor is not None:
                P_pred = P / forgetting_factor
            else:
                P_pred = P + np.eye(n_k) * process_var
            P_pred = (P_pred + P_pred.T) / 2.0
            S = max((x_i.T @ P_pred @ x_i).item() + obs_var, _S_MIN)
            K = (P_pred @ x_i) / S
            beta = beta + (K * resid_i).ravel()
            P = (np.eye(n_k) - K @ x_i.T) @ P_pred
            P = (P + P.T) / 2.0
            valid_count += 1
            y_hist.append(y_i)
            resid_hist.append(resid_i)
            if len(y_hist) > window_bars:
                y_hist.pop(0)
                resid_hist.pop(0)

            out_row = i + as_of_lag_bars
            if out_row < n_obs and valid_count >= min_obs:
                beta_out = beta.copy()
                alpha_out = float(beta_out[0]) if add_const else 0.0
                alpha_df.iloc[out_row, alpha_df.columns.get_loc(col)] = alpha_out
                for j, fname in enumerate(sorted(available)):
                    betas_dict[fname].iloc[out_row, betas_dict[fname].columns.get_loc(col)] = (
                        float(beta_out[1 + j]) if add_const else float(beta_out[j])
                    )
                if not np.isnan(y_all[out_row]) and not np.any(np.isnan(X_all[out_row])):
                    fitted_out = (X_all[out_row] @ beta_out).item()
                    residual_df.iloc[out_row, residual_df.columns.get_loc(col)] = float(y_all[out_row] - fitted_out)
                if len(y_hist) >= min_obs:
                    y_a = np.array(y_hist)
                    r_a = np.array(resid_hist)
                    ss_tot = float(np.sum((y_a - np.mean(y_a)) ** 2))
                    ss_res = float(np.sum(r_a**2))
                    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
                    r2_df.iloc[out_row, r2_df.columns.get_loc(col)] = r2

    return betas_dict, r2_df, residual_df, alpha_df
