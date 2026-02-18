#!/usr/bin/env python3
"""
Scanner: Top Opportunities from DEX bar data.
Modes: momentum, volatility_breakout, mean_reversion.
Output: terminal table, CSV, JSON. Optional --alert for threshold-crossing signals only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_analyzer.config import (
    STABLE_SYMBOLS,
    db_path,
    exclude_stable_pairs,
    min_bars as config_min_bars,
    min_liquidity_usd as config_min_liq,
    min_vol_h24 as config_min_vol,
)
from crypto_analyzer.data import append_spot_returns_to_returns_df, get_factor_returns, load_bars, load_snapshots
from crypto_analyzer.factors import (
    build_factor_matrix,
    compute_ols_betas,
    compute_residual_returns,
    compute_residual_lookback_return,
    compute_residual_vol,
)
from crypto_analyzer.features import (
    annualize_sharpe,
    bars_for_lookback_hours,
    classify_beta_state,
    classify_vol_regime,
    compute_beta_compression,
    compute_beta_vs_factor,
    compute_correlation_matrix,
    compute_dispersion_index,
    compute_dispersion_zscore,
    compute_drawdown_from_equity,
    compute_drawdown_from_log_returns,
    compute_excess_cum_return,
    compute_excess_lookback_return,
    compute_excess_log_returns,
    compute_lookback_return,
    compute_rolling_beta,
    compute_rolling_corr,
    dispersion_window_for_freq,
    log_returns,
    period_return_bars,
    periods_per_year,
    rolling_volatility,
    rolling_windows_for_freq,
)

# Capacity/slippage (research-only proxies)
DEFAULT_MAX_POS_LIQ_PCT = 0.01
DEFAULT_REF_POSITION_USD = 10_000.0
DEFAULT_SLIPPAGE_BPS_AT_FULL = 10.0
DEFAULT_MAX_SLIPPAGE_BPS_TRADABLE = 50.0


def _get_bars_or_from_snapshots(
    freq: str,
    db: str,
    min_liq: float,
    min_vol: float,
    min_bars_count: int,
) -> pd.DataFrame:
    """Load bars table if exists; else build from snapshots in memory (no materialize)."""
    try:
        return load_bars(freq, db_path_override=db, min_bars=min_bars_count)
    except FileNotFoundError:
        pass
    # Build from snapshots: resample per pair
    snap = load_snapshots(
        db_path_override=db,
        min_liquidity_usd=min_liq,
        min_vol_h24=min_vol,
        apply_filters=True,
    )
    if snap.empty:
        return snap
    from crypto_analyzer.features import cumulative_returns_log

    window = 24 if freq == "1h" else 288
    rows = []
    for (cid, addr), g in snap.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        close = g["price_usd"].resample(freq).last().dropna()
        if len(close) < max(min_bars_count, window + 2):
            continue
        lr = log_returns(close)
        cr = cumulative_returns_log(lr)
        rv = rolling_volatility(lr, window)
        liq = g["liquidity_usd"].resample(freq).last().reindex(close.index).ffill().bfill()
        v24 = g["vol_h24"].resample(freq).last().reindex(close.index).ffill().bfill()
        for ts in close.index:
            rows.append({
                "ts_utc": ts,
                "chain_id": cid,
                "pair_address": addr,
                "base_symbol": g["base_symbol"].iloc[-1],
                "quote_symbol": g["quote_symbol"].iloc[-1],
                "close": close.loc[ts],
                "log_return": lr.get(ts, np.nan),
                "cum_return": cr.get(ts, np.nan),
                "roll_vol": rv.get(ts, np.nan),
                "liquidity_usd": liq.get(ts, np.nan),
                "vol_h24": v24.get(ts, np.nan),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _apply_quality_filters(
    df: pd.DataFrame,
    min_liq: float,
    min_vol: float,
    min_bars_count: int,
    exclude_stable: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    if "liquidity_usd" in df.columns:
        df = df[pd.to_numeric(df["liquidity_usd"], errors="coerce") >= min_liq]
    if "vol_h24" in df.columns:
        df = df[pd.to_numeric(df["vol_h24"], errors="coerce") >= min_vol]
    if min_bars_count and "chain_id" in df.columns:
        cnt = df.groupby(["chain_id", "pair_address"]).size()
        valid = cnt[cnt >= min_bars_count].index
        df = df[df.set_index(["chain_id", "pair_address"]).index.isin(valid)].reset_index(drop=True)
    if exclude_stable and "base_symbol" in df.columns and "quote_symbol" in df.columns:
        def is_stable(r):
            b, q = str(r.get("base_symbol", "")).upper(), str(r.get("quote_symbol", "")).upper()
            return b in STABLE_SYMBOLS and q in STABLE_SYMBOLS
        df = df[~df.apply(is_stable, axis=1)]
    return df


def _last_bars_per_pair(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Last n bars per (chain_id, pair_address)."""
    if df.empty or n <= 0:
        return df
    return df.groupby(["chain_id", "pair_address"], group_keys=False).tail(n).reset_index(drop=True)


def _compute_trading_metrics(
    bars: pd.DataFrame,
    freq: str,
    ret_lookback_bars: Optional[int] = None,
    dd_lookback_bars: Optional[int] = None,
    factor_returns: Optional[pd.Series] = None,
    vol_short_window: int = 24,
    vol_medium_window: int = 48,
    beta_compress_threshold: float = 0.15,
) -> pd.DataFrame:
    """Per-pair return_24h, ..., beta_btc_24/72, beta_compression, beta_state, beta_hat_used, excess_*, regime."""
    base_cols = ["chain_id", "pair_address", "return_24h", "annual_vol", "annual_sharpe", "max_drawdown", "beta_vs_btc",
                 "corr_btc_24", "beta_btc_24", "corr_btc_72", "beta_btc_72",
                 "beta_compression", "beta_state", "beta_hat_used",
                 "excess_return_24h", "excess_total_cum_return", "excess_max_drawdown", "regime"]
    if bars.empty:
        return pd.DataFrame(columns=base_cols)
    periods_yr = periods_per_year(freq)
    n_24h = ret_lookback_bars if ret_lookback_bars is not None else period_return_bars(freq)["24h"]
    win_short, win_long = rolling_windows_for_freq(freq)
    rows = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        if "log_return" not in g.columns:
            g = g.copy()
            g["log_return"] = log_returns(g["close"])
        r = g["log_return"].dropna()
        if len(r) < 2:
            continue
        return_24h = compute_lookback_return(r, n_24h) if len(r) >= n_24h else np.nan
        vol = r.std(ddof=1)
        annual_vol = float(vol * np.sqrt(periods_yr)) if vol and not np.isnan(vol) else np.nan
        sharpe = (r.mean() / vol) if vol and vol != 0 and not np.isnan(vol) else np.nan
        annual_sharpe = annualize_sharpe(float(sharpe) if not np.isnan(sharpe) else np.nan, freq)
        r_dd = r.tail(dd_lookback_bars) if dd_lookback_bars and len(r) >= dd_lookback_bars else r
        _, max_dd = compute_drawdown_from_log_returns(r_dd)
        factor_aligned = factor_returns.reindex(r.index).dropna() if factor_returns is not None else None
        beta_btc = compute_beta_vs_factor(r, factor_aligned) if factor_aligned is not None and len(factor_aligned) >= 2 else np.nan
        corr_24 = corr_72 = beta_24 = beta_72 = np.nan
        if factor_aligned is not None and len(factor_aligned) >= 2:
            rc24 = compute_rolling_corr(r, factor_aligned, win_short)
            rc72 = compute_rolling_corr(r, factor_aligned, win_long)
            rb24 = compute_rolling_beta(r, factor_aligned, win_short)
            rb72 = compute_rolling_beta(r, factor_aligned, win_long)
            if not rc24.empty and rc24.notna().any():
                corr_24 = float(rc24.dropna().iloc[-1])
            if not rc72.empty and rc72.notna().any():
                corr_72 = float(rc72.dropna().iloc[-1])
            if not rb24.empty and rb24.notna().any():
                beta_24 = float(rb24.dropna().iloc[-1])
            if not rb72.empty and rb72.notna().any():
                beta_72 = float(rb72.dropna().iloc[-1])
        short_vol = r.rolling(vol_short_window).std(ddof=1).iloc[-1] if len(r) >= vol_short_window else np.nan
        medium_vol = r.rolling(min(vol_medium_window, len(r))).std(ddof=1).iloc[-1] if len(r) >= vol_medium_window else short_vol
        regime = classify_vol_regime(short_vol, medium_vol) if not (np.isnan(short_vol) or np.isnan(medium_vol) or medium_vol == 0) else "unknown"
        beta_compression = compute_beta_compression(beta_24, beta_72)
        beta_state = classify_beta_state(beta_24, beta_72, beta_compress_threshold)
        beta_hat_used = beta_72 if (beta_72 is not None and not np.isnan(beta_72)) else beta_btc
        beta_hat = beta_hat_used
        excess_return_24h = excess_total_cum_return = excess_max_drawdown = np.nan
        if factor_aligned is not None and len(factor_aligned) >= 2 and beta_hat is not None and not np.isnan(beta_hat):
            r_excess = compute_excess_log_returns(r, factor_aligned, float(beta_hat))
            if len(r_excess) >= 2:
                excess_cum = compute_excess_cum_return(r_excess)
                excess_return_24h = compute_excess_lookback_return(r_excess, n_24h) if len(r_excess) >= n_24h else np.nan
                excess_total_cum_return = float(excess_cum.iloc[-1]) if len(excess_cum) else np.nan
                excess_equity = np.exp(r_excess.cumsum())
                _, excess_max_drawdown = compute_drawdown_from_equity(excess_equity)
        rows.append({
            "chain_id": cid,
            "pair_address": addr,
            "return_24h": return_24h,
            "annual_vol": annual_vol,
            "annual_sharpe": annual_sharpe,
            "max_drawdown": max_dd,
            "beta_vs_btc": beta_btc,
            "corr_btc_24": corr_24,
            "beta_btc_24": beta_24,
            "corr_btc_72": corr_72,
            "beta_btc_72": beta_72,
            "beta_compression": beta_compression,
            "beta_state": beta_state,
            "beta_hat_used": beta_hat_used,
            "excess_return_24h": excess_return_24h,
            "excess_total_cum_return": excess_total_cum_return,
            "excess_max_drawdown": excess_max_drawdown,
            "regime": regime,
        })
    return pd.DataFrame(rows)


def _bars_to_returns_df_and_meta(bars: pd.DataFrame) -> tuple:
    """Build returns_df (index=ts_utc, columns=pair_id) and meta dict pair_id -> label."""
    if bars.empty or "log_return" not in bars.columns:
        return pd.DataFrame(), {}
    bars = bars.copy()
    bars["pair_id"] = bars["chain_id"].astype(str) + ":" + bars["pair_address"].astype(str)
    bars["label"] = bars["base_symbol"].fillna("").astype(str) + "/" + bars["quote_symbol"].fillna("").astype(str)
    returns_df = bars.pivot_table(index="ts_utc", columns="pair_id", values="log_return").dropna(how="all")
    meta = bars.groupby("pair_id")["label"].last().to_dict()
    return returns_df, meta


def _add_residual_columns(
    metrics_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    freq: str,
    lookback_bars: int,
) -> pd.DataFrame:
    """Add residual_return_24h, residual_annual_vol, residual_max_drawdown when factor cols exist. In-place style; returns metrics_df."""
    factor_cols = [c for c in ["BTC_spot", "ETH_spot"] if c in returns_df.columns]
    if not factor_cols or metrics_df.empty:
        return metrics_df
    X_factor = build_factor_matrix(returns_df, factor_cols=factor_cols)
    if X_factor.empty or len(X_factor) < 2:
        return metrics_df
    out = metrics_df.copy()
    out["residual_return_24h"] = np.nan
    out["residual_annual_vol"] = np.nan
    out["residual_max_drawdown"] = np.nan
    for i, row in out.iterrows():
        cid, addr = row["chain_id"], row["pair_address"]
        pair_id = f"{cid}:{addr}"
        if pair_id not in returns_df.columns:
            continue
        y_asset = returns_df[pair_id]
        betas, intercept = compute_ols_betas(y_asset, X_factor)
        if len(betas) == 0 or np.isnan(intercept):
            continue
        resid_series = compute_residual_returns(y_asset, X_factor, betas, float(intercept))
        if len(resid_series) < 2:
            continue
        out.at[i, "residual_return_24h"] = compute_residual_lookback_return(resid_series, lookback_bars)
        out.at[i, "residual_annual_vol"] = compute_residual_vol(resid_series, lookback_bars, freq)
        resid_equity = np.exp(resid_series.cumsum())
        _, r_dd = compute_drawdown_from_equity(resid_equity)
        out.at[i, "residual_max_drawdown"] = r_dd
    return out


def _add_capacity_slippage_tradable(
    df: pd.DataFrame,
    max_pos_liq_pct: float = DEFAULT_MAX_POS_LIQ_PCT,
    ref_position_usd: float = DEFAULT_REF_POSITION_USD,
    slippage_bps_at_full: float = DEFAULT_SLIPPAGE_BPS_AT_FULL,
    max_slippage_bps_tradable: float = DEFAULT_MAX_SLIPPAGE_BPS_TRADABLE,
) -> pd.DataFrame:
    """Add capacity_usd, est_slippage_bps, tradable. Research-only proxies."""
    if df.empty:
        return df
    out = df.copy()
    liq = pd.to_numeric(out.get("liquidity_usd", 0), errors="coerce").fillna(0)
    capacity_usd = (max_pos_liq_pct * liq).values
    out["capacity_usd"] = capacity_usd
    with np.errstate(divide="ignore", invalid="ignore"):
        est_bps = np.where(capacity_usd > 0, np.minimum(500.0, slippage_bps_at_full * ref_position_usd / capacity_usd), 500.0)
    out["est_slippage_bps"] = est_bps
    out["tradable"] = est_bps <= max_slippage_bps_tradable
    return out


def scan_momentum(
    bars: pd.DataFrame,
    freq: str,
    top: int,
    lookback_bars: Optional[int] = None,
) -> pd.DataFrame:
    """Top N by 24h return (or last lookback_bars return)."""
    if bars.empty:
        return pd.DataFrame()
    periods = {"1h": 24, "5min": 288, "15min": 96, "1D": 1}
    n_bars = lookback_bars or periods.get(freq, 24)
    bars = _last_bars_per_pair(bars, n_bars + 50)
    out = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if len(g) < min(n_bars, 2):
            continue
        close = g["close"].iloc[-n_bars:]
        if len(close) < 2:
            continue
        ret_24h = (close.iloc[-1] / close.iloc[0]) - 1.0
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        out.append({
            "chain_id": cid,
            "pair_address": addr,
            "label": label,
            "return_24h": ret_24h,
            "return_zscore": np.nan,
            "close": g["close"].iloc[-1],
            "liquidity_usd": g["liquidity_usd"].iloc[-1] if "liquidity_usd" in g.columns else None,
            "vol_h24": g["vol_h24"].iloc[-1] if "vol_h24" in g.columns else None,
        })
    res = pd.DataFrame(out).sort_values("return_24h", ascending=False).head(top)
    return res


def scan_volatility_breakout(
    bars: pd.DataFrame,
    freq: str,
    top: int,
    z_threshold: float = 2.0,
    vol_window: int = 24,
) -> pd.DataFrame:
    """Return z-score > threshold AND rolling vol slope positive, liquidity stable."""
    if bars.empty:
        return pd.DataFrame()
    bars = _last_bars_per_pair(bars, vol_window + 50)
    out = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if "log_return" not in g.columns or g["log_return"].dropna().empty:
            continue
        r = g["log_return"].dropna()
        if len(r) < vol_window:
            continue
        mean_r, std_r = r.mean(), r.std(ddof=1)
        if std_r == 0 or np.isnan(std_r):
            continue
        z = (r.iloc[-1] - mean_r) / std_r
        if z < z_threshold:
            continue
        roll_vol = rolling_volatility(r, vol_window)
        if len(roll_vol) < 2:
            continue
        vol_slope = (roll_vol.iloc[-1] - roll_vol.iloc[-2]) if not np.isnan(roll_vol.iloc[-2]) else 0
        if vol_slope <= 0:
            continue
        liq = g["liquidity_usd"].dropna()
        liq_stable = liq.iloc[-1] >= 0.8 * liq.iloc[0] if len(liq) >= 2 else True
        if not liq_stable:
            continue
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        out.append({
            "chain_id": cid,
            "pair_address": addr,
            "label": label,
            "return_zscore": z,
            "last_log_return": r.iloc[-1],
            "close": g["close"].iloc[-1],
            "liquidity_usd": g["liquidity_usd"].iloc[-1] if "liquidity_usd" in g.columns else None,
        })
    return pd.DataFrame(out).sort_values("return_zscore", ascending=False).head(top)


def scan_residual_momentum(
    bars: pd.DataFrame,
    freq: str,
    top: int,
    returns_df: pd.DataFrame,
    lookback_bars: int,
    factor_returns: Optional[pd.Series] = None,
    beta_compress_threshold: float = 0.15,
) -> pd.DataFrame:
    """Top N by residual_return_24h (factor-model residual). Same liquidity/vol/min-bars/stable rules as momentum."""
    if bars.empty or returns_df.empty:
        return pd.DataFrame()
    metrics_df = _compute_trading_metrics(
        bars, freq, ret_lookback_bars=lookback_bars, factor_returns=factor_returns, beta_compress_threshold=beta_compress_threshold,
    )
    metrics_df = _add_residual_columns(metrics_df, returns_df, freq, lookback_bars)
    if "residual_return_24h" not in metrics_df.columns or metrics_df["residual_return_24h"].isna().all():
        return pd.DataFrame()
    last = _last_bars_per_pair(bars, lookback_bars + 10)
    rows = []
    for (cid, addr), g in last.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        m = metrics_df[(metrics_df["chain_id"] == cid) & (metrics_df["pair_address"] == addr)]
        if m.empty:
            continue
        m = m.iloc[0]
        res_24 = m.get("residual_return_24h")
        if pd.isna(res_24):
            continue
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        rows.append({
            "chain_id": cid,
            "pair_address": addr,
            "label": label,
            "return_24h": m.get("return_24h"),
            "return_zscore": np.nan,
            "residual_return_24h": res_24,
            "close": g["close"].iloc[-1],
            "liquidity_usd": g["liquidity_usd"].iloc[-1] if "liquidity_usd" in g.columns else None,
            "vol_h24": g["vol_h24"].iloc[-1] if "vol_h24" in g.columns else None,
        })
    res = pd.DataFrame(rows).sort_values("residual_return_24h", ascending=False).head(top)
    return res


def scan_mean_reversion(
    bars: pd.DataFrame,
    freq: str,
    top: int,
    z_threshold: float = -2.0,
    min_positive_candles: int = 1,
) -> pd.DataFrame:
    """Big negative z-score (oversold) with at least one positive candle recently (reversion condition)."""
    if bars.empty:
        return pd.DataFrame()
    bars = _last_bars_per_pair(bars, 100)
    out = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if "log_return" not in g.columns:
            continue
        r = g["log_return"].dropna()
        if len(r) < 10:
            continue
        mean_r, std_r = r.mean(), r.std(ddof=1)
        if std_r == 0 or np.isnan(std_r):
            continue
        z = (r.iloc[-1] - mean_r) / std_r
        if z > z_threshold:
            continue
        recent = r.iloc[-min_positive_candles - 5 :]
        if not (recent > 0).any():
            continue
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        out.append({
            "chain_id": cid,
            "pair_address": addr,
            "label": label,
            "return_zscore": z,
            "last_log_return": r.iloc[-1],
            "close": g["close"].iloc[-1],
            "liquidity_usd": g["liquidity_usd"].iloc[-1] if "liquidity_usd" in g.columns else None,
        })
    return pd.DataFrame(out).sort_values("return_zscore").head(top)


def run_scan(
    db: str,
    mode: str,
    freq: str,
    top: int,
    min_liquidity: Optional[float] = None,
    min_vol_h24: Optional[float] = None,
    min_bars: Optional[int] = None,
    min_corr: Optional[float] = None,
    corr_window: int = 24,
    min_beta: Optional[float] = None,
    beta_window: int = 72,
    min_excess_return: Optional[float] = None,
    beta_compress_threshold: float = 0.15,
    only_beta_compressed: bool = False,
    only_beta_expanded: bool = False,
    min_dispersion_z: Optional[float] = None,
    z: float = 2.0,
    exclude_stable: bool = True,
    ret_lookback_bars: Optional[int] = None,
    max_pos_liq_pct: float = DEFAULT_MAX_POS_LIQ_PCT,
    max_slippage_bps_tradable: float = DEFAULT_MAX_SLIPPAGE_BPS_TRADABLE,
) -> Tuple[pd.DataFrame, float, float, List[str]]:
    """Run scan pipeline; return (result_df, disp_latest, disp_z_latest, filter_reasons)."""
    min_liq = min_liquidity if min_liquidity is not None else (config_min_liq() if callable(config_min_liq) else 250_000)
    min_vol = min_vol_h24 if min_vol_h24 is not None else (config_min_vol() if callable(config_min_vol) else 500_000)
    min_bars_count = min_bars if min_bars is not None else (config_min_bars() if callable(config_min_bars) else 48)
    exclude = exclude_stable and (exclude_stable_pairs() if callable(exclude_stable_pairs) else True)

    bars = _get_bars_or_from_snapshots(freq, db, min_liq, min_vol, min_bars_count)
    bars = _apply_quality_filters(bars, min_liq, min_vol, min_bars_count, exclude)
    if bars.empty:
        return pd.DataFrame(), np.nan, np.nan, []

    returns_df, meta = _bars_to_returns_df_and_meta(bars)
    returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db, freq)
    factor_ret = get_factor_returns(returns_df, meta, db, freq, factor_symbol="BTC") if not returns_df.empty else None

    ret_lb = ret_lookback_bars if ret_lookback_bars is not None else bars_for_lookback_hours(freq, 24)
    if mode == "momentum":
        res = scan_momentum(bars, freq, top, lookback_bars=ret_lb)
    elif mode == "residual_momentum":
        res = scan_residual_momentum(bars, freq, top, returns_df=returns_df, lookback_bars=ret_lb, factor_returns=factor_ret, beta_compress_threshold=beta_compress_threshold)
    elif mode == "volatility_breakout":
        res = scan_volatility_breakout(bars, freq, top, z_threshold=z)
    else:
        res = scan_mean_reversion(bars, freq, top, z_threshold=-abs(z))

    if res.empty:
        return pd.DataFrame(), np.nan, np.nan, []

    metrics_df = _compute_trading_metrics(
        bars, freq, ret_lookback_bars=ret_lb, factor_returns=factor_ret, beta_compress_threshold=beta_compress_threshold,
    )
    metrics_df = _add_residual_columns(metrics_df, returns_df, freq, ret_lb)
    if not metrics_df.empty:
        metric_cols = (
            "return_24h", "annual_vol", "annual_sharpe", "max_drawdown", "beta_vs_btc",
            "corr_btc_24", "beta_btc_24", "corr_btc_72", "beta_btc_72",
            "beta_compression", "beta_state", "beta_hat_used",
            "excess_return_24h", "excess_total_cum_return", "excess_max_drawdown",
            "residual_return_24h", "residual_annual_vol", "residual_max_drawdown",
            "regime",
        )
        for c in metric_cols:
            if c in res.columns:
                res = res.drop(columns=[c])
        res = res.merge(metrics_df, on=["chain_id", "pair_address"], how="left")

    res = _add_capacity_slippage_tradable(res, max_pos_liq_pct=max_pos_liq_pct, max_slippage_bps_tradable=max_slippage_bps_tradable)

    res_pre = res.copy()
    pre_filter_count = len(res)
    corr_col = "corr_btc_24" if corr_window == 24 else "corr_btc_72"
    beta_col = "beta_btc_24" if beta_window == 24 else "beta_btc_72"
    if min_corr is not None and corr_col in res.columns:
        res = res[res[corr_col].notna() & (res[corr_col] >= min_corr)]
    if min_beta is not None and beta_col in res.columns:
        res = res[res[beta_col].notna() & (res[beta_col] >= min_beta)]
    if min_excess_return is not None and "excess_return_24h" in res.columns:
        res = res[res["excess_return_24h"].notna() & (res["excess_return_24h"] >= min_excess_return)]
    if only_beta_compressed and "beta_state" in res.columns:
        res = res[res["beta_state"] == "compressed"]
    if only_beta_expanded and "beta_state" in res.columns:
        res = res[res["beta_state"] == "expanded"]

    disp_latest = np.nan
    disp_z_latest = np.nan
    if returns_df.shape[1] >= 2:
        disp_series = compute_dispersion_index(returns_df)
        if not disp_series.empty:
            disp_latest = float(disp_series.iloc[-1])
        w_disp = dispersion_window_for_freq(freq)
        if len(disp_series) >= w_disp:
            disp_z = compute_dispersion_zscore(disp_series, w_disp)
            if not disp_z.empty and disp_z.notna().any():
                disp_z_latest = float(disp_z.iloc[-1])
    if min_dispersion_z is not None and (np.isnan(disp_z_latest) or disp_z_latest < min_dispersion_z):
        res = res.iloc[0:0]

    reasons = []
    if res.empty and pre_filter_count > 0:
        row = res_pre.iloc[0]
        if min_corr is not None and corr_col in res_pre.columns:
            v = row.get(corr_col)
            if pd.notna(v) and v < min_corr:
                reasons.append(f"{corr_col}={float(v):.2f} < min_corr={min_corr}")
        if min_beta is not None and beta_col in res_pre.columns:
            v = row.get(beta_col)
            if pd.notna(v) and v < min_beta:
                reasons.append(f"{beta_col}={float(v):.2f} < min_beta={min_beta}")
        if min_excess_return is not None and "excess_return_24h" in res_pre.columns:
            v = row.get("excess_return_24h")
            if pd.notna(v) and v < min_excess_return:
                reasons.append(f"excess_return_24h={float(v):.4f} < min_excess_return={min_excess_return}")
        if min_dispersion_z is not None and (np.isnan(disp_z_latest) or disp_z_latest < min_dispersion_z):
            reasons.append(f"dispersion_z_latest={disp_z_latest:.2f} < min_dispersion_z={min_dispersion_z}")

    return res, disp_latest, disp_z_latest, reasons


def main() -> int:
    ap = argparse.ArgumentParser(description="DEX scanner: top opportunities")
    ap.add_argument("--mode", choices=["momentum", "residual_momentum", "volatility_breakout", "mean_reversion"], default="momentum")
    ap.add_argument("--db", default=None, help="SQLite path")
    ap.add_argument("--freq", default="1h", help="Bar frequency (5min, 15min, 1h, 1D)")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-liquidity", type=float, default=None)
    ap.add_argument("--min-vol-h24", type=float, default=None)
    ap.add_argument("--min-bars", type=int, default=None)
    ap.add_argument("--no-exclude-stable", action="store_true", help="Include stable/stable pairs")
    ap.add_argument("--z", type=float, default=2.0, help="Z-score threshold (vol breakout or mean rev)")
    ap.add_argument("--ret-lookback-hours", type=float, default=24, help="Lookback hours for return_24h (default 24)")
    ap.add_argument("--ret-lookback-bars", type=int, default=None, help="Override: lookback bars for return (advanced)")
    ap.add_argument("--dd-lookback", type=int, default=None, help="Max drawdown over last N bars only (default: full history)")
    ap.add_argument("--include-correlation", action="store_true", help="Print correlation matrix (per freq)")
    ap.add_argument(
        "--corr-window",
        type=int,
        choices=[24, 72],
        default=24,
        help="Which rolling corr column to use for --min-corr/--alert (24 or 72 bars; default 24)",
    )
    ap.add_argument(
        "--beta-window",
        type=int,
        choices=[24, 72],
        default=72,
        help="Which rolling beta column to use for --min-beta/--alert (24 or 72 bars; default 72)",
    )
    ap.add_argument("--min-corr", type=float, default=None, metavar="R",
                    help="Filter: min rolling corr vs BTC_spot (uses --corr-window)")
    ap.add_argument("--min-beta", type=float, default=None, metavar="B",
                    help="Filter: min rolling beta vs BTC_spot (uses --beta-window)")
    ap.add_argument("--min-excess-return", type=float, default=None, metavar="R",
                    help="Filter: min excess_return_24h (BTC-hedged)")
    ap.add_argument("--beta-compress-threshold", type=float, default=0.15, metavar="T",
                    help="Threshold for beta_state: compressed if beta_24 < beta_72 - T (default 0.15)")
    ap.add_argument("--only-beta-compressed", action="store_true",
                    help="Keep only rows where beta_state == compressed")
    ap.add_argument("--only-beta-expanded", action="store_true",
                    help="Keep only rows where beta_state == expanded")
    ap.add_argument("--min-dispersion-z", type=float, default=None, metavar="Z",
                    help="Require dispersion z-score >= Z (global; no rows if below)")
    ap.add_argument("--alert", action="store_true", help="Print only signals crossing thresholds")
    ap.add_argument("--debug", action="store_true", help="Print pre-filter table and row count")
    ap.add_argument("--csv", default=None, metavar="FILE", help="Export CSV path")
    ap.add_argument("--json", default=None, metavar="FILE", help="Export JSON path")
    args = ap.parse_args()

    db = args.db or (db_path() if callable(db_path) else db_path())
    min_liq = args.min_liquidity if args.min_liquidity is not None else (config_min_liq() if callable(config_min_liq) else 250_000)
    min_vol = args.min_vol_h24 if args.min_vol_h24 is not None else (config_min_vol() if callable(config_min_vol) else 500_000)
    min_bars_count = args.min_bars if args.min_bars is not None else (config_min_bars() if callable(config_min_bars) else 48)
    exclude_stable = not args.no_exclude_stable and (exclude_stable_pairs() if callable(exclude_stable_pairs) else True)

    bars = _get_bars_or_from_snapshots(args.freq, db, min_liq, min_vol, min_bars_count)
    bars = _apply_quality_filters(bars, min_liq, min_vol, min_bars_count, exclude_stable)

    if bars.empty:
        print("No bar data. Run materialize_bars.py or ensure poller has run.", file=sys.stderr)
        return 1

    # Build returns_df (DEX bars), then add spot columns so factor = BTC_spot; do this before any metrics.
    returns_df, meta = _bars_to_returns_df_and_meta(bars)
    returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db, args.freq)
    factor_ret = get_factor_returns(returns_df, meta, db, args.freq, factor_symbol="BTC") if not returns_df.empty else None

    # Print correlation matrix once per run (before scan/filter output).
    if args.include_correlation and returns_df.shape[1] >= 2:
        corr = compute_correlation_matrix(returns_df)
        corr_display = corr.rename(index=meta, columns=meta)
        print("Correlation matrix (log returns):")
        print(corr_display.round(3).to_string())
        print()

    ret_lookback_bars = args.ret_lookback_bars
    if ret_lookback_bars is None:
        ret_lookback_bars = bars_for_lookback_hours(args.freq, args.ret_lookback_hours)

    if args.mode == "momentum":
        res = scan_momentum(bars, args.freq, args.top, lookback_bars=ret_lookback_bars)
    elif args.mode == "residual_momentum":
        res = scan_residual_momentum(bars, args.freq, args.top, returns_df=returns_df, lookback_bars=ret_lookback_bars, factor_returns=factor_ret, beta_compress_threshold=getattr(args, "beta_compress_threshold", 0.15))
    elif args.mode == "volatility_breakout":
        res = scan_volatility_breakout(bars, args.freq, args.top, z_threshold=args.z)
    else:
        res = scan_mean_reversion(bars, args.freq, args.top, z_threshold=-abs(args.z))

    if res.empty:
        print("No signals.")
        return 0

    metrics_df = _compute_trading_metrics(
        bars, args.freq,
        ret_lookback_bars=ret_lookback_bars,
        dd_lookback_bars=args.dd_lookback,
        factor_returns=factor_ret,
        beta_compress_threshold=getattr(args, "beta_compress_threshold", 0.15),
    )
    metrics_df = _add_residual_columns(metrics_df, returns_df, args.freq, ret_lookback_bars)
    if not metrics_df.empty:
        metric_cols = (
            "return_24h", "annual_vol", "annual_sharpe", "max_drawdown", "beta_vs_btc",
            "corr_btc_24", "beta_btc_24", "corr_btc_72", "beta_btc_72",
            "beta_compression", "beta_state", "beta_hat_used",
            "excess_return_24h", "excess_total_cum_return", "excess_max_drawdown",
            "residual_return_24h", "residual_annual_vol", "residual_max_drawdown",
            "regime",
        )
        for c in metric_cols:
            if c in res.columns:
                res = res.drop(columns=[c])
        res = res.merge(metrics_df, on=["chain_id", "pair_address"], how="left")

    res = _add_capacity_slippage_tradable(
        res,
        max_pos_liq_pct=getattr(args, "max_pos_liq_pct", DEFAULT_MAX_POS_LIQ_PCT),
        max_slippage_bps_tradable=getattr(args, "max_slippage_bps_tradable", DEFAULT_MAX_SLIPPAGE_BPS_TRADABLE),
    )

    res_pre = res.copy()
    pre_filter_count = len(res)
    corr_col = "corr_btc_24" if args.corr_window == 24 else "corr_btc_72"
    beta_col = "beta_btc_24" if args.beta_window == 24 else "beta_btc_72"
    if args.min_corr is not None and corr_col in res.columns:
        res = res[res[corr_col].notna() & (res[corr_col] >= args.min_corr)]
    if args.min_beta is not None and beta_col in res.columns:
        res = res[res[beta_col].notna() & (res[beta_col] >= args.min_beta)]
    if getattr(args, "min_excess_return", None) is not None and "excess_return_24h" in res.columns:
        res = res[res["excess_return_24h"].notna() & (res["excess_return_24h"] >= args.min_excess_return)]
    if getattr(args, "only_beta_compressed", False) and "beta_state" in res.columns:
        res = res[res["beta_state"] == "compressed"]
    if getattr(args, "only_beta_expanded", False) and "beta_state" in res.columns:
        res = res[res["beta_state"] == "expanded"]

    disp_series = pd.Series(dtype=float)
    disp_z_latest = np.nan
    if returns_df.shape[1] >= 2:
        disp_series = compute_dispersion_index(returns_df)
        w_disp = dispersion_window_for_freq(args.freq)
        if len(disp_series) >= w_disp:
            disp_z = compute_dispersion_zscore(disp_series, w_disp)
            disp_z_latest = float(disp_z.iloc[-1]) if not disp_z.empty and disp_z.notna().any() else np.nan
    if getattr(args, "min_dispersion_z", None) is not None and (np.isnan(disp_z_latest) or disp_z_latest < args.min_dispersion_z):
        res = res.iloc[0:0]

    if getattr(args, "debug", False) and not res_pre.empty:
        print(f"Pre-filter results: {len(res_pre)} row(s)")
        print(res_pre.to_string(index=False))
        print()

    if res.empty and pre_filter_count > 0:
        print(f"No results after filters. Pre-filter rows: {pre_filter_count}.")
        row = res_pre.iloc[0]
        reasons = []
        if args.min_corr is not None and corr_col in res_pre.columns:
            v = row.get(corr_col)
            if pd.notna(v) and v < args.min_corr:
                reasons.append(f"{corr_col}={float(v):.2f} < min-corr={args.min_corr} (corr-window={args.corr_window})")
        if args.min_beta is not None and beta_col in res_pre.columns:
            v = row.get(beta_col)
            if pd.notna(v) and v < args.min_beta:
                reasons.append(f"{beta_col}={float(v):.2f} < min-beta={args.min_beta} (beta-window={args.beta_window})")
        if getattr(args, "min_excess_return", None) is not None and "excess_return_24h" in res_pre.columns:
            v = row.get("excess_return_24h")
            if pd.notna(v) and v < args.min_excess_return:
                reasons.append(f"excess_return_24h={float(v):.4f} < min-excess-return={args.min_excess_return}")
        if getattr(args, "min_dispersion_z", None) is not None and (np.isnan(disp_z_latest) or disp_z_latest < args.min_dispersion_z):
            reasons.append(f"dispersion_z_latest={disp_z_latest:.2f} < min-dispersion-z={args.min_dispersion_z}")
        if reasons:
            print("Filtered out because", "; ".join(reasons) + ".")
    if (getattr(args, "debug", False) or pre_filter_count > 0) and returns_df.shape[1] >= 2 and not disp_series.empty:
        print(f"Dispersion latest: {float(disp_series.iloc[-1]):.6f}" + (f"  z: {disp_z_latest:.2f}" if not np.isnan(disp_z_latest) else ""))

    if args.alert and args.mode == "momentum" and not res.empty and (res["return_24h"] < 0.01).all():
        return 0
    if args.alert and args.mode == "volatility_breakout" and res.empty:
        return 0

    # Ensure display columns exist so CLI/Streamlit can show one consistent table
    if not res.empty:
        required_cols = ["chain_id", "pair_address", "label"]
        if args.mode in ("volatility_breakout", "mean_reversion"):
            required_cols.append("return_zscore")
        if args.mode == "residual_momentum":
            required_cols.append("residual_return_24h")
        missing = [c for c in required_cols if c not in res.columns]
        if missing:
            raise ValueError(f"Scan mode {args.mode}: output missing columns {missing}")

    if not res.empty:
        print(res.to_string(index=False))

    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(args.csv, index=False)
        print(f"Wrote {args.csv}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(res.to_dict(orient="records"), f, indent=2)
        print(f"Wrote {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
