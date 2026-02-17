"""
Cross-sectional alpha research: IC, decay, turnover, signal builders.
Institutional factor testing; research-only, no execution.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .features import period_return_bars
from .factors import (
    build_factor_matrix,
    compute_ols_betas,
    compute_residual_returns,
    compute_residual_lookback_return,
)


def compute_forward_returns(returns_df: pd.DataFrame, horizon_bars: int) -> pd.DataFrame:
    """
    Forward period return from log returns: at t, fwd_ret = exp(sum(log_ret[t+1:t+1+horizon])) - 1.
    Index aligned with returns_df; last horizon_bars rows are NaN.
    """
    if returns_df.empty or horizon_bars < 1:
        return pd.DataFrame()
    out = pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    for col in returns_df.columns:
        r = returns_df[col].dropna()
        if len(r) < horizon_bars + 1:
            continue
        roll_sum = r.rolling(horizon_bars).sum().shift(-horizon_bars)
        out[col] = np.exp(roll_sum) - 1.0
    return out


def rank_signal(signal_series: pd.Series) -> pd.Series:
    """
    Cross-sectional rank at each timestamp. Expects signal_series to be a DataFrame column
    or a Series with index = (timestamp, asset_id) or we need per-timestamp ranking.
    For a single asset column (one series per asset): use rank_signal_df(signal_df) which
    ranks across assets at each time.
    """
    if signal_series.empty:
        return signal_series
    return signal_series.rank(pct=True, method="average")


def rank_signal_df(signal_df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank at each timestamp. signal_df: index=ts_utc, columns=asset_id."""
    if signal_df.empty:
        return signal_df
    return signal_df.rank(axis=1, pct=True, method="average")


def information_coefficient(
    signal_df: pd.DataFrame,
    fwd_ret_df: pd.DataFrame,
    method: str = "spearman",
) -> pd.Series:
    """
    Time series of cross-sectional IC: at each timestamp, correlation between signal and forward return.
    method: 'spearman' (rank IC) or 'pearson'. Aligns on index; drops NaN.
    """
    common = signal_df.index.intersection(fwd_ret_df.index)
    if len(common) < 2:
        return pd.Series(dtype=float)
    S = signal_df.reindex(common).dropna(how="all")
    F = fwd_ret_df.reindex(common).dropna(how="all")
    idx = S.index.intersection(F.index)
    S = S.loc[idx]
    F = F.loc[idx]
    # Align columns
    cols = S.columns.intersection(F.columns)
    if len(cols) < 2:
        return pd.Series(dtype=float)
    S = S[cols]
    F = F[cols]
    ic_ts = []
    for t in idx:
        s = S.loc[t].dropna()
        f = F.loc[t].dropna()
        common_a = s.index.intersection(f.index)
        if len(common_a) < 2:
            ic_ts.append(np.nan)
            continue
        s = s.loc[common_a]
        f = f.loc[common_a]
        if method == "spearman":
            s_rank = s.rank()
            f_rank = f.rank()
            corr = s_rank.corr(f_rank)
        else:
            corr = s.corr(f)
        ic_ts.append(corr if pd.notna(corr) else np.nan)
    return pd.Series(ic_ts, index=idx)


def ic_summary(ic_ts: pd.Series) -> Dict[str, float]:
    """
    Summary of IC series: mean, std, t-stat, hit_rate (fraction IC>0), ic_95_lo, ic_95_hi, n_obs.
    """
    r = ic_ts.dropna()
    n = len(r)
    if n < 2:
        return {"mean_ic": np.nan, "std_ic": np.nan, "t_stat": np.nan, "hit_rate": np.nan, "ic_95_lo": np.nan, "ic_95_hi": np.nan, "n_obs": n}
    mean_ic = float(r.mean())
    std_ic = float(r.std(ddof=1))
    t_stat = (mean_ic / std_ic) * np.sqrt(n) if std_ic != 0 else np.nan
    hit_rate = float((r > 0).mean())
    se = std_ic / np.sqrt(n) if n > 0 else np.nan
    ic_95_lo = mean_ic - 1.96 * se if pd.notna(se) else np.nan
    ic_95_hi = mean_ic + 1.96 * se if pd.notna(se) else np.nan
    return {
        "mean_ic": mean_ic,
        "std_ic": std_ic,
        "t_stat": t_stat,
        "hit_rate": hit_rate,
        "ic_95_lo": ic_95_lo,
        "ic_95_hi": ic_95_hi,
        "n_obs": n,
    }


def ic_decay(
    signal_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    horizons: List[int],
    method: str = "spearman",
) -> pd.DataFrame:
    """
    IC vs horizon: for each horizon in horizons, compute forward returns and IC series, then mean IC.
    Returns table with columns: horizon_bars, mean_ic, std_ic, n_obs (and optionally t_stat).
    """
    rows = []
    for h in horizons:
        if h < 1:
            continue
        fwd = compute_forward_returns(returns_df, h)
        ic_ts = information_coefficient(signal_df, fwd, method=method)
        s = ic_summary(ic_ts)
        rows.append({"horizon_bars": h, "mean_ic": s["mean_ic"], "std_ic": s["std_ic"], "n_obs": s["n_obs"], "t_stat": s["t_stat"]})
    return pd.DataFrame(rows)


def turnover_from_ranks(
    ranks_df: pd.DataFrame,
    top_k: int,
    bottom_k: int,
) -> Tuple[pd.Series, float]:
    """
    Turnover at each rebalance: fraction of names that changed in top_k or bottom_k vs previous period.
    Returns (turnover_series, mean_turnover). Turnover in [0, 2] (theoretical max when all names flip).
    """
    if ranks_df.empty or ranks_df.shape[1] < 2 or top_k < 1:
        return pd.Series(dtype=float), 0.0
    idx = ranks_df.index.sort_values()
    out = []
    for i in range(1, len(idx)):
        r_prev = ranks_df.loc[idx[i - 1]].dropna()
        r_curr = ranks_df.loc[idx[i]].dropna()
        if r_prev.empty or r_curr.empty:
            out.append(np.nan)
            continue
        # Top k: largest ranks (rank 1 = smallest value, so we want k largest signal values -> nlargest)
        # In rank(pct=True), 1 = highest. So top_k = k largest ranks = nlargest(top_k)
        prev_top = set(r_prev.nlargest(top_k).index)
        curr_top = set(r_curr.nlargest(top_k).index)
        prev_bot = set(r_prev.nsmallest(bottom_k).index)
        curr_bot = set(r_curr.nsmallest(bottom_k).index)
        sym_diff_top = len(prev_top ^ curr_top)
        sym_diff_bot = len(prev_bot ^ curr_bot)
        turnover = (sym_diff_top + sym_diff_bot) / (top_k + bottom_k) if (top_k + bottom_k) > 0 else 0.0
        out.append(turnover)
    ser = pd.Series(out, index=idx[1:])
    mean_turnover = float(ser.mean()) if len(ser) and ser.notna().any() else 0.0
    return ser, mean_turnover


# ---- Signal builders (produce signal_df: index=ts_utc, columns=asset_id) ----


def signal_momentum_24h(returns_df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Momentum signal: rolling 24h return (log->simple). Works on DEX and spot."""
    bars_24h = period_return_bars(freq).get("24h", 24)
    out = pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    for col in returns_df.columns:
        r = returns_df[col].dropna()
        if len(r) < bars_24h:
            continue
        out[col] = (np.exp(r.rolling(bars_24h).sum()) - 1.0)
    return out


def signal_residual_momentum_24h(
    returns_df: pd.DataFrame,
    freq: str,
    factor_cols: Optional[List[str]] = None,
) -> Optional[pd.DataFrame]:
    """
    Residual momentum: 24h return of factor-model residual. If factor cols missing, returns None.
    """
    if factor_cols is None:
        factor_cols = [c for c in ["BTC_spot", "ETH_spot"] if c in returns_df.columns]
    if not factor_cols:
        return None
    X = build_factor_matrix(returns_df, factor_cols=factor_cols)
    if X.empty or len(X) < 2:
        return None
    bars_24h = period_return_bars(freq).get("24h", 24)
    out = pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    for col in returns_df.columns:
        if str(col).endswith("_spot"):
            out[col] = np.nan
            continue
        y = returns_df[col]
        betas, intercept = compute_ols_betas(y, X)
        if len(betas) == 0 or np.isnan(intercept):
            continue
        resid = compute_residual_returns(y, X, betas, float(intercept))
        if len(resid) < bars_24h:
            continue
        ret_24h = resid.rolling(bars_24h).apply(lambda x: np.exp(x.sum()) - 1.0 if len(x) == bars_24h else np.nan, raw=False)
        out[col] = ret_24h
    return out.replace([np.inf, -np.inf], np.nan)


def signal_beta_compression(
    returns_df: pd.DataFrame,
    factor_returns: pd.Series,
    short_window: int = 24,
    long_window: int = 72,
) -> pd.DataFrame:
    """
    Beta compression signal: beta_short - beta_long (negative = compressed) at each timestamp.
    Uses rolling covariance; factor_returns aligned to returns_df index.
    """
    if factor_returns is None or factor_returns.dropna().empty or returns_df.empty:
        return pd.DataFrame(index=returns_df.index, columns=returns_df.columns)
    out = pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    for col in returns_df.columns:
        r = returns_df[col]
        f = factor_returns.reindex(r.index).dropna()
        idx = r.dropna().index.intersection(f.index)
        if len(idx) < long_window:
            continue
        r = r.loc[idx].astype(float)
        f = f.loc[idx].astype(float)
        cov_s = r.rolling(short_window).cov(f)
        var_s = f.rolling(short_window).var()
        cov_l = r.rolling(long_window).cov(f)
        var_l = f.rolling(long_window).var()
        beta_short = (cov_s / var_s.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        beta_long = (cov_l / var_l.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        diff = beta_short - beta_long
        out[col] = diff.reindex(out.index)
    return out


def signal_dispersion_conditioned(
    momentum_signal_df: pd.DataFrame,
    dispersion_z_series: pd.Series,
) -> pd.DataFrame:
    """
    Dispersion-conditioned signal: momentum_24h * sign(dispersion_z).
    When dispersion_z > 0 (high dispersion), keep sign of momentum; when z < 0, flip.
    Simple regime switch: in low dispersion (macro beta) we may want to dampen or flip alpha.
    Here: signal = momentum * sign(dispersion_z) so that in low-dispersion regimes signal is negative
    when z<0 (interpretation: relative strength less relevant when z low). Documented and simple.
    """
    if momentum_signal_df.empty or dispersion_z_series.empty:
        return momentum_signal_df.copy()
    common = momentum_signal_df.index.intersection(dispersion_z_series.index)
    out = momentum_signal_df.reindex(common).copy()
    z = dispersion_z_series.reindex(common).ffill().bfill()
    sign_z = np.sign(z).replace(0, 1)
    for col in out.columns:
        out[col] = out[col] * sign_z.values
    return out


def compute_dispersion_series(returns_df: pd.DataFrame) -> pd.Series:
    """Cross-sectional std of returns at each timestamp."""
    if returns_df.empty or returns_df.shape[1] < 2:
        return pd.Series(dtype=float)
    return returns_df.std(axis=1)


def dispersion_zscore_series(dispersion_series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score of dispersion."""
    if len(dispersion_series) < window or window < 2:
        return pd.Series(dtype=float)
    mean = dispersion_series.rolling(window).mean()
    std = dispersion_series.rolling(window).std(ddof=1)
    return ((dispersion_series - mean) / std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
