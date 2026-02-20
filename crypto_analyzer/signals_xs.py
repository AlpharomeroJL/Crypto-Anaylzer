"""
Cross-sectional signal framework: z-score, winsorize, neutralize, orthogonalize.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .features import period_return_bars


def zscore_cross_section(signal_df: pd.DataFrame, clip: float = 5.0) -> pd.DataFrame:
    """
    Cross-sectional z-score at each timestamp: (x - mean) / std, then clip to [-clip, clip].
    """
    if signal_df.empty:
        return signal_df.copy()
    out = signal_df.sub(signal_df.mean(axis=1), axis=0)
    std = signal_df.std(axis=1)
    std = std.replace(0, np.nan)
    out = out.div(std, axis=0)
    out = out.clip(lower=-clip, upper=clip)
    return out


def winsorize_cross_section(signal_df: pd.DataFrame, p: float = 0.01) -> pd.DataFrame:
    """At each timestamp, winsorize to [p, 1-p] quantiles (cross-sectional)."""
    if signal_df.empty:
        return signal_df.copy()
    out = signal_df.copy()
    for t in out.index:
        row = out.loc[t].dropna()
        if len(row) < 2:
            continue
        lo = row.quantile(p)
        hi = row.quantile(1 - p)
        out.loc[t] = out.loc[t].clip(lower=lo, upper=hi)
    return out


def _ols_residual_cross_section(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """y and X aligned; return residual y - X @ beta (with const in X)."""
    if X.size == 0 or len(y) < 3 or X.shape[0] != len(y):
        return y.copy()
    try:
        XtX = X.T @ X
        Xty = X.T @ y
        beta = np.linalg.solve(XtX, Xty)
        return y - X @ beta
    except np.linalg.LinAlgError:
        return y.copy()


def neutralize_signal_to_exposures(
    signal_df: pd.DataFrame,
    exposures_df: Dict[str, pd.DataFrame],
    method: str = "ols",
) -> pd.DataFrame:
    """
    For each timestamp, regress signal cross-section on exposures and take residuals.
    exposures_df: dict of name -> DataFrame (same index/columns as signal_df).
    Degrades gracefully if < 3 assets at a timestamp (returns raw signal).
    """
    if signal_df.empty or not exposures_df:
        return signal_df.copy()
    common_idx = signal_df.index
    cols = signal_df.columns
    X_list = []
    for name, df in exposures_df.items():
        if df.empty or df.columns.intersection(cols).empty:
            continue
        X_list.append(df.reindex(index=common_idx, columns=cols))
    if not X_list:
        return signal_df.copy()
    out = pd.DataFrame(index=common_idx, columns=cols, dtype=float)
    for t in common_idx:
        y = signal_df.loc[t].values
        valid = np.isfinite(y)
        if valid.sum() < 3:
            out.loc[t] = signal_df.loc[t]
            continue
        X_rows = []
        for xdf in X_list:
            row = xdf.loc[t].values if t in xdf.index else np.full(len(cols), np.nan)
            X_rows.append(row)
        X_mat = np.column_stack([np.ones(len(cols)), *X_rows])
        X_mat = np.where(np.isfinite(X_mat), X_mat, 0.0)
        y_finite = np.where(valid, y, 0.0)
        resid = _ols_residual_cross_section(y_finite, X_mat)
        out.loc[t] = np.where(valid, resid, np.nan)
    return out


def _flatten_pair(
    df1: pd.DataFrame, df2: pd.DataFrame, idx: pd.Index
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Flatten two dataframes to 1d over common index and columns; same shape or None."""
    cols = df1.columns.intersection(df2.columns)
    if len(cols) == 0:
        return None
    x = df1.reindex(index=idx, columns=cols).to_numpy().ravel()
    y = df2.reindex(index=idx, columns=cols).to_numpy().ravel()
    if x.shape != y.shape:
        return None
    return x, y


def orthogonalize_signals(
    signals_dict: Dict[str, pd.DataFrame],
    order: Optional[List[str]] = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, float]]:
    """
    Orthogonalize signals sequentially per timestamp: regress each signal's cross-section
    on previous (orthogonalized) signals and take residuals.
    order: list of keys (default: keys of signals_dict). Returns (orthogonalized_dict, report)
    with report containing avg cross-corr before/after.
    """
    if not signals_dict:
        return {}, {}
    order = order or list(signals_dict.keys())
    orth: Dict[str, pd.DataFrame] = {}
    for i, name in enumerate(order):
        if name not in signals_dict:
            continue
        S = signals_dict[name]
        if S.empty:
            orth[name] = S.copy()
            continue
        if i == 0:
            orth[name] = S.copy()
            continue
        # Per-timestamp: regress this signal's row on previous orthogonalized rows
        out = pd.DataFrame(index=S.index, columns=S.columns, dtype=float)
        for t in S.index:
            y = S.loc[t].values.astype(float)
            X_cols = [np.ones(len(y))]
            for j in range(i):
                if order[j] not in orth:
                    continue
                prev = orth[order[j]].loc[t].values.astype(float)
                if prev.shape == y.shape:
                    X_cols.append(prev)
            if len(X_cols) < 2:
                out.loc[t] = S.loc[t]
                continue
            X = np.column_stack(X_cols)
            valid = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
            if valid.sum() < 3:
                out.loc[t] = S.loc[t]
                continue
            resid = _ols_residual_cross_section(np.where(valid, y, 0.0), np.where(np.isfinite(X), X, 0.0))
            out.loc[t] = np.where(valid, resid, np.nan)
        orth[name] = out
    # Report: average absolute cross-correlation before/after
    report: Dict[str, float] = {}
    for k in order:
        if k not in signals_dict or k not in orth:
            continue
        orig = signals_dict[k]
        o = orth[k]
        if orig.empty or o.empty:
            continue
        corrs_before: List[float] = []
        corrs_after: List[float] = []
        for other in order:
            if other == k or other not in signals_dict or other not in orth:
                continue
            ob = signals_dict[other]
            oa = orth[other]
            common = orig.index.intersection(ob.index).intersection(o.index).intersection(oa.index)
            if len(common) < 2:
                continue
            pair = _flatten_pair(orig, ob, common)
            if pair is not None:
                a, b = pair
                mask = np.isfinite(a) & np.isfinite(b)
                if mask.sum() >= 2:
                    c = np.corrcoef(a[mask], b[mask])
                    if c.size >= 4 and np.isfinite(c[0, 1]):
                        corrs_before.append(float(np.abs(c[0, 1])))
            pair2 = _flatten_pair(o, oa, common)
            if pair2 is not None:
                aa, bb = pair2
                mask2 = np.isfinite(aa) & np.isfinite(bb)
                if mask2.sum() >= 2:
                    c2 = np.corrcoef(aa[mask2], bb[mask2])
                    if c2.size >= 4 and np.isfinite(c2[0, 1]):
                        corrs_after.append(float(np.abs(c2[0, 1])))
        if corrs_before:
            report[f"{k}_avg_corr_before"] = float(np.mean(corrs_before))
        if corrs_after:
            report[f"{k}_avg_corr_after"] = float(np.mean(corrs_after))
    return orth, report


def build_exposure_panel(
    returns_df: pd.DataFrame,
    meta_df: pd.DataFrame,
    factor_returns: Optional[pd.Series] = None,
    freq: str = "1h",
    liquidity_panel: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Build exposure panels (index=time, columns=assets): beta_btc_72, rolling_vol_24h,
    log_liquidity (if liquidity_panel given), turnover_proxy (rolling mean of abs return).
    """
    out = {}
    if returns_df.empty:
        return out
    idx = returns_df.index
    cols = returns_df.columns
    bars_24 = period_return_bars(freq).get("24h", 24)

    # Rolling vol (24h realized)
    vol = returns_df.rolling(bars_24).std(ddof=1)
    out["rolling_vol_24h"] = vol

    # Turnover proxy: rolling mean of abs return
    out["turnover_proxy"] = returns_df.abs().rolling(bars_24).mean()

    # Beta vs factor
    if factor_returns is not None and not factor_returns.dropna().empty:
        beta_df = pd.DataFrame(index=idx, columns=cols, dtype=float)
        for c in cols:
            r = returns_df[c].dropna()
            f = factor_returns.reindex(r.index).dropna()
            common = r.index.intersection(f.index)
            if len(common) < 72:
                continue
            r = r.loc[common]
            f = f.loc[common]
            cov = r.rolling(72).cov(f)
            var_f = f.rolling(72).var()
            beta = (cov / var_f).replace([np.inf, -np.inf], np.nan)
            beta_df[c] = beta.reindex(idx)
        out["beta_btc_72"] = beta_df

    # Log liquidity (if provided)
    if liquidity_panel is not None and not liquidity_panel.empty:
        log_liq = np.log(liquidity_panel.replace(0, np.nan).clip(lower=1e-6))
        out["log_liquidity"] = log_liq.reindex(index=idx, columns=cols)

    return out


def value_vs_beta(
    returns_df: pd.DataFrame,
    freq: str,
    factor_returns: Optional[pd.Series] = None,
    liquidity_panel: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """
    Institutional composite: residual_momentum_24h neutralized to beta + vol + liquidity.
    """
    from .alpha_research import signal_residual_momentum_24h

    sig = signal_residual_momentum_24h(returns_df, freq)
    if sig is None or sig.empty:
        return None
    exposures = build_exposure_panel(
        returns_df, pd.DataFrame(), factor_returns=factor_returns, freq=freq, liquidity_panel=liquidity_panel
    )
    to_use = {k: v for k, v in exposures.items() if v is not None and not v.empty and v.shape[0] >= 3}
    if not to_use:
        return sig
    return neutralize_signal_to_exposures(sig, to_use, method="ols")


def clean_momentum(
    returns_df: pd.DataFrame,
    freq: str,
    factor_returns: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Momentum 24h orthogonalized against beta and vol (institutional composite).
    """
    from .alpha_research import signal_momentum_24h

    mom = signal_momentum_24h(returns_df, freq)
    if mom.empty:
        return mom
    exposures = build_exposure_panel(returns_df, pd.DataFrame(), factor_returns=factor_returns, freq=freq)
    beta_df = exposures.get("beta_btc_72")
    vol_df = exposures.get("rolling_vol_24h")
    to_use = {}
    if beta_df is not None and not beta_df.empty:
        to_use["beta_btc_72"] = beta_df
    if vol_df is not None and not vol_df.empty:
        to_use["rolling_vol_24h"] = vol_df
    if not to_use:
        return mom
    return neutralize_signal_to_exposures(mom, to_use, method="ols")
