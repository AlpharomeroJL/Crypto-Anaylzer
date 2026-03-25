"""
Cross-sectional signal framework: z-score, winsorize, neutralize, orthogonalize.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .features import period_return_bars


def _resolve_market_factor_cols(returns_df: pd.DataFrame) -> List[str]:
    """
    Prefer majors-native factor legs first, then spot fallbacks.
    """
    preferred = ["BTC-USD", "ETH-USD", "BTC_spot", "ETH_spot"]
    return [c for c in preferred if c in returns_df.columns]


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
    """y and X aligned; return residual y - X @ beta (with const in X). Robust to singular X'X."""
    from .factors import _solve_normal_equations

    if X.size == 0 or len(y) < 3 or X.shape[0] != len(y):
        return y.copy()
    beta = _solve_normal_equations(X, y)
    if np.any(np.isnan(beta)):
        return y.copy()
    return y - X @ beta


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
        y = signal_df.loc[t].values.astype(float)
        if not np.isfinite(y).any():
            out.loc[t] = signal_df.loc[t]
            continue
        X_rows: List[np.ndarray] = []
        for xdf in X_list:
            row = xdf.loc[t].values if t in xdf.index else np.full(len(cols), np.nan)
            X_rows.append(row.astype(float))
        if not X_rows:
            out.loc[t] = signal_df.loc[t]
            continue
        X_no_const = np.column_stack(X_rows)
        valid = np.isfinite(y) & np.all(np.isfinite(X_no_const), axis=1)
        if valid.sum() < 3:
            out.loc[t] = signal_df.loc[t]
            continue
        X_valid = np.column_stack([np.ones(valid.sum()), X_no_const[valid]])
        y_valid = y[valid]
        resid_valid = _ols_residual_cross_section(y_valid, X_valid)
        resid_full = np.full(len(cols), np.nan, dtype=float)
        resid_full[valid] = resid_valid
        out.loc[t] = resid_full
    return out


def _flatten_pair(df1: pd.DataFrame, df2: pd.DataFrame, idx: pd.Index) -> Optional[Tuple[np.ndarray, np.ndarray]]:
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
            # Regress only on valid cross-section rows; keep invalid assets as NaN.
            y_valid = y[valid]
            X_valid = X[valid]
            resid_valid = _ols_residual_cross_section(y_valid, X_valid)
            resid_full = np.full(len(y), np.nan, dtype=float)
            resid_full[valid] = resid_valid
            out.loc[t] = resid_full
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

    factor_cols = _resolve_market_factor_cols(returns_df)
    sig = signal_residual_momentum_24h(returns_df, freq, factor_cols=factor_cols)
    if sig is None or sig.empty:
        return None
    # Native value/reversion direction for majors: opposite of residual momentum.
    sig = -sig
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
    # Do not score benchmark factor legs in cross-section.
    factor_cols = _resolve_market_factor_cols(returns_df)
    for fcol in factor_cols:
        if fcol in mom.columns:
            mom[fcol] = np.nan
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


def xs_low_vol_tilt(returns_df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Majors-native low-volatility tilt: signal = -rolling std of log returns (same window as 24h bar count).

    Higher values => lower recent realized volatility. Cross-sectionally rankable; not a return-momentum
    or residual-momentum family — uses second-moment path only. Factor benchmark legs excluded from scoring.
    """
    if returns_df.empty:
        return returns_df.copy()
    bars_24 = period_return_bars(freq).get("24h", 24)
    vol = returns_df.rolling(bars_24).std(ddof=1)
    out = -vol
    factor_cols = _resolve_market_factor_cols(returns_df)
    for fcol in factor_cols:
        if fcol in out.columns:
            out[fcol] = np.nan
    return out.replace([np.inf, -np.inf], np.nan)


def xs_low_vol_dispersion_conditional(
    returns_df: pd.DataFrame,
    freq: str,
    dispersion_window: int = 24,
) -> pd.DataFrame:
    """
    Low-vol tilt conditioned on cross-sectional dispersion regime (majors-native).

    Base is ``xs_low_vol_tilt`` (second moment only). Dispersion state uses the same
    cross-sectional return dispersion and rolling z-score as reportv2's regime section
    (``compute_dispersion_series`` + ``dispersion_zscore_series``; default window 24 bars).

    Row-wise: ``signal = base * sign(dispersion_z)``, with ``sign(0) -> +1``. This mirrors
    ``alpha_research.signal_dispersion_conditioned`` (momentum × sign(z)) but swaps in
    low-vol tilt so the family is regime-conditioned rather than an unconditional vol factor.
    Uses only information available at each bar (no forward dispersion).
    """
    from .alpha_research import compute_dispersion_series, dispersion_zscore_series

    base = xs_low_vol_tilt(returns_df, freq)
    if base.empty:
        return base
    disp = compute_dispersion_series(returns_df)
    if disp.empty or len(disp.dropna()) < max(dispersion_window, 2):
        return base.replace([np.inf, -np.inf], np.nan)
    dz = dispersion_zscore_series(disp, dispersion_window)
    common = base.index.intersection(dz.index)
    if len(common) == 0:
        return base.replace([np.inf, -np.inf], np.nan)
    out = base.reindex(common).copy()
    z = dz.reindex(common).ffill().bfill()
    sign_z = np.sign(z.to_numpy(dtype=float))
    sign_z = np.where(sign_z == 0.0, 1.0, sign_z)
    out = out.mul(sign_z, axis=0)
    return out.replace([np.inf, -np.inf], np.nan)


def short_horizon_reversal(returns_df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Cross-sectional short-horizon mean-reversion tilt (majors-native).

    Signal = minus rolling sum of log returns over ``short_bars``, where
    ``short_bars = max(2, bars_24 // 4)`` and ``bars_24`` is the same 24h bar count as
    ``period_return_bars(freq)`` (e.g. 6 bars at 1h vs 24 for the day-momentum window).

    Higher values => assets that lost over the lookback (reversion candidates). Uses
    only past returns at each bar. Distinct from 24h momentum (longer cumulative return,
    different construction in ``signal_momentum_24h`` / ``clean_momentum``), from
    low-vol tilt (second moment), and from dispersion-conditioned low-vol. Factor legs
    excluded via ``_resolve_market_factor_cols``.
    """
    if returns_df.empty:
        return returns_df.copy()
    bars_24 = period_return_bars(freq).get("24h", 24)
    short_bars = max(2, bars_24 // 4)
    cum = returns_df.rolling(short_bars, min_periods=short_bars).sum()
    out = -cum
    factor_cols = _resolve_market_factor_cols(returns_df)
    for fcol in factor_cols:
        if fcol in out.columns:
            out[fcol] = np.nan
    return out.replace([np.inf, -np.inf], np.nan)


def majors_venue_volume_surprise_research_v1(
    returns_df: pd.DataFrame,
    volume_df: pd.DataFrame,
    freq: str,
) -> pd.DataFrame:
    """
    Majors-native **participation / flow** family (v1): unexpected venue volume vs each asset's
    own trailing history — not a pure price transform.

    Construction (causal within the bar timeline):
    - ``lv = log(volume + 1)`` on venue-reported bar volume.
    - ``baseline = rolling_mean(lv, 24h window).shift(1)`` so the benchmark uses **past** bars only.
    - ``surprise = lv - baseline``
    - Cross-sectional z-score per bar, then **negate** → research tilt that **fades** unusually high
      volume vs recent participation (interpretable as crowded-attention / pressure mean-reversion).

    Benchmark factor columns (e.g. BTC-USD, ETH-USD) are nulled for cross-sectional scoring.
    Requires a volume panel aligned to ``returns_df`` (e.g. from ``venue_bars_1h``); empty if missing.
    """
    if returns_df.empty or volume_df is None or volume_df.empty:
        return pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    v = volume_df.reindex(index=returns_df.index, columns=returns_df.columns).astype(float)
    v = v.clip(lower=0.0)
    lv = np.log(v + 1.0)
    bars_24 = period_return_bars(freq).get("24h", 24)
    w = max(2, int(bars_24))
    baseline = lv.rolling(window=w, min_periods=w).mean().shift(1)
    surprise = lv - baseline
    z = zscore_cross_section(surprise)
    out = -z
    factor_cols = _resolve_market_factor_cols(returns_df)
    for fcol in factor_cols:
        if fcol in out.columns:
            out[fcol] = np.nan
    return out.replace([np.inf, -np.inf], np.nan)


def majors_composite_research_v1(returns_df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Small majors research composite (v1): equal-weight blend of cross-sectional z-scores of
    ``short_horizon_reversal`` and ``xs_low_vol_tilt`` — short-horizon first moment vs
    rolling-vol second moment, both already majors-native and factor-leg nulled in the
    underlying builders.

    ``value_vs_beta`` is **not** folded in; pair this composite with ``value_vs_beta`` in
    ``--signals`` for the usual two-leg orthogonalized layout vs single-family baselines.
    No meta-model: plain mean of two z-scored panels.
    """
    sh = short_horizon_reversal(returns_df, freq)
    lv = xs_low_vol_tilt(returns_df, freq)
    if sh.empty or lv.empty:
        return pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    z_sh = zscore_cross_section(sh)
    z_lv = zscore_cross_section(lv)
    idx = z_sh.index.intersection(z_lv.index)
    cols = z_sh.columns.intersection(z_lv.columns)
    if len(idx) == 0 or len(cols) == 0:
        return pd.DataFrame(index=returns_df.index, columns=returns_df.columns, dtype=float)
    blended = (z_sh.reindex(idx).reindex(columns=cols) + z_lv.reindex(idx).reindex(columns=cols)) / 2.0
    out = blended.reindex(index=returns_df.index, columns=returns_df.columns)
    return out.replace([np.inf, -np.inf], np.nan)


# --- Liquidity shock reversion (case study) ---

LIQSHOCK_LIQUIDITY_FLOOR = 1.0
LIQSHOCK_ROLL_VOL_EPS = 1e-10
LIQSHOCK_GRID_N = (6, 12, 24, 48)
LIQSHOCK_GRID_WINSOR_P = (0.01, 0.05)
LIQSHOCK_GRID_CLIP = (3, 5)


def liquidity_shock_reversion_single(
    liquidity_panel: pd.DataFrame,
    target_index: pd.Index,
    target_columns: pd.Index,
    N: int,
    winsor_p: float = 0.01,
    clip: float = 5.0,
    roll_vol_panel: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Single variant: dlogL over N bars, cross-sectional winsorize/zscore, negate (mean reversion).
    No leakage: only t and t-N used. Aligns to target_index and target_columns.
    """
    if liquidity_panel is None or liquidity_panel.empty:
        return pd.DataFrame(index=target_index, columns=target_columns, dtype=float)
    common_cols = liquidity_panel.columns.intersection(target_columns)
    if len(common_cols) == 0:
        return pd.DataFrame(index=target_index, columns=target_columns, dtype=float)
    liq = liquidity_panel.reindex(index=target_index, columns=common_cols)
    L = liq.clip(lower=LIQSHOCK_LIQUIDITY_FLOOR)
    log_L = np.log(L)
    dlogL = log_L.diff(N)
    if roll_vol_panel is not None and not roll_vol_panel.empty:
        roll = roll_vol_panel.reindex(index=target_index, columns=common_cols)
        roll = roll.replace(0, np.nan).clip(lower=LIQSHOCK_ROLL_VOL_EPS)
        dlogL = dlogL / roll
    dlogL = winsorize_cross_section(dlogL, p=winsor_p)
    zscore_df = zscore_cross_section(dlogL, clip=clip)
    out = -zscore_df
    return out.reindex(index=target_index, columns=target_columns)


def liquidity_shock_reversion_variants(
    liquidity_panel: pd.DataFrame,
    target_index: pd.Index,
    target_columns: pd.Index,
    roll_vol_panel: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Sixteen deterministic variants: N in {6,12,24,48}, winsor_p in {0.01, 0.05}, clip in {3, 5}.
    Keys e.g. liqshock_N6_w0.01_clip3. Order: N, winsor_p, clip.
    """
    if liquidity_panel is None or liquidity_panel.empty:
        return {}
    out: Dict[str, pd.DataFrame] = {}
    for N in LIQSHOCK_GRID_N:
        for winsor_p in LIQSHOCK_GRID_WINSOR_P:
            for clip_val in LIQSHOCK_GRID_CLIP:
                name = f"liqshock_N{N}_w{winsor_p}_clip{int(clip_val)}"
                df = liquidity_shock_reversion_single(
                    liquidity_panel=liquidity_panel,
                    target_index=target_index,
                    target_columns=target_columns,
                    N=N,
                    winsor_p=winsor_p,
                    clip=clip_val,
                    roll_vol_panel=roll_vol_panel,
                )
                out[name] = df
    return out
