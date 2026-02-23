#!/usr/bin/env python3
"""
Daily report: markdown + CSV. Top momentum, top vol, regime shifts, notable liquidity drops.
Optional: save charts as PNG for top 5. Designed for cron/Task Scheduler.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from crypto_analyzer.config import db_path, default_freq
from crypto_analyzer.config import min_bars as config_min_bars
from crypto_analyzer.data import (
    append_spot_returns_to_returns_df,
    get_factor_returns,
    load_bars,
    load_snapshots,
    load_spot_price_resampled,
)
from crypto_analyzer.factors import (
    build_factor_matrix,
    compute_ols_betas,
    compute_residual_lookback_return,
    compute_residual_returns,
    compute_residual_vol,
)
from crypto_analyzer.features import (
    annualize_sharpe,
    classify_beta_state,
    classify_vol_regime,
    compute_beta_compression,
    compute_beta_vs_factor,
    compute_correlation_matrix,
    compute_dispersion_index,
    compute_dispersion_zscore,
    compute_drawdown_from_equity,
    compute_drawdown_from_log_returns,
    compute_excess_log_returns,
    compute_excess_lookback_return,
    compute_lookback_return,
    compute_lookback_return_from_price,
    compute_ratio_series,
    compute_rolling_beta,
    compute_rolling_corr,
    dispersion_window_for_freq,
    log_returns,
    period_return_bars,
    periods_per_year,
    rolling_windows_for_freq,
)
from crypto_analyzer.regimes import classify_market_regime, explain_regime
from crypto_analyzer.signals import detect_signals, load_signals, log_signals


def _vol_window_bars(freq: str) -> int:
    """Standard vol window for report: 24h of bars (same as return_24h lookback)."""
    return period_return_bars(freq)["24h"]


def run_momentum_scan(bars: pd.DataFrame, freq: str, top: int = 10) -> pd.DataFrame:
    """Top N by 24h return; include return_24h, annual_vol (24h rolling), annual_sharpe, max_drawdown."""
    if bars.empty:
        return pd.DataFrame()
    n_24h = period_return_bars(freq)["24h"]
    vol_window = _vol_window_bars(freq)
    periods_yr = periods_per_year(freq)
    out = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if "log_return" not in g.columns:
            g = g.copy()
            g["log_return"] = log_returns(g["close"])
        r = g["log_return"].dropna()
        if len(r) < max(vol_window, n_24h):
            continue
        return_24h = compute_lookback_return(r, n_24h)
        vol = r.rolling(vol_window).std(ddof=1).iloc[-1]
        annual_vol = float(vol * np.sqrt(periods_yr)) if not np.isnan(vol) and vol else np.nan
        sharpe = (r.mean() / r.std(ddof=1)) if r.std(ddof=1) and r.std(ddof=1) != 0 else np.nan
        annual_sharpe = annualize_sharpe(float(sharpe) if not np.isnan(sharpe) else np.nan, freq)
        _, max_dd = compute_drawdown_from_log_returns(r)
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        out.append(
            {
                "chain_id": cid,
                "pair_address": addr,
                "label": label,
                "return_24h": return_24h,
                "annual_vol": annual_vol,
                "annual_sharpe": annual_sharpe,
                "max_drawdown": max_dd,
            }
        )
    return pd.DataFrame(out).sort_values("return_24h", ascending=False).head(top)


def run_vol_scan(bars: pd.DataFrame, freq: str, top: int = 10) -> pd.DataFrame:
    """Top N by annual_vol (24h rolling); include return_24h, annual_sharpe, max_drawdown. Same vol definition as momentum table."""
    if bars.empty:
        return pd.DataFrame()
    vol_window = _vol_window_bars(freq)
    n_24h = period_return_bars(freq)["24h"]
    periods_yr = periods_per_year(freq)
    out = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if "log_return" not in g.columns:
            g = g.copy()
            g["log_return"] = log_returns(g["close"])
        r = g["log_return"].dropna()
        if len(r) < vol_window:
            continue
        vol = r.rolling(vol_window).std(ddof=1).iloc[-1]
        annual_vol = float(vol * np.sqrt(periods_yr)) if not np.isnan(vol) else np.nan
        return_24h = compute_lookback_return(r, n_24h) if len(r) >= n_24h else np.nan
        sharpe = (r.mean() / r.std(ddof=1)) if r.std(ddof=1) and r.std(ddof=1) != 0 else np.nan
        annual_sharpe = annualize_sharpe(float(sharpe) if not np.isnan(sharpe) else np.nan, freq)
        _, max_dd = compute_drawdown_from_log_returns(r)
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        out.append(
            {
                "chain_id": cid,
                "pair_address": addr,
                "label": label,
                "return_24h": return_24h,
                "annual_vol": annual_vol,
                "annual_sharpe": annual_sharpe,
                "max_drawdown": max_dd,
            }
        )
    return pd.DataFrame(out).sort_values("annual_vol", ascending=False).head(top)


def run_residual_leaders(bars: pd.DataFrame, freq: str, db_path_override: str, top: int = 10) -> pd.DataFrame:
    """Top N by residual_return_24h (factor model vs BTC_spot/ETH_spot). Same 24h vol definition."""
    if bars.empty:
        return pd.DataFrame()
    bars = bars.copy()
    bars["pair_id"] = bars["chain_id"].astype(str) + ":" + bars["pair_address"].astype(str)
    bars["label"] = bars["base_symbol"].fillna("").astype(str) + "/" + bars["quote_symbol"].fillna("").astype(str)
    returns_df = bars.pivot_table(index="ts_utc", columns="pair_id", values="log_return").dropna(how="all")
    meta = bars.groupby("pair_id")["label"].last().to_dict()
    if returns_df.empty:
        return pd.DataFrame()
    returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db_path_override, freq)
    factor_cols = [c for c in ["BTC_spot", "ETH_spot"] if c in returns_df.columns]
    if not factor_cols:
        return pd.DataFrame()
    X_factor = build_factor_matrix(returns_df, factor_cols=factor_cols)
    if X_factor.empty or len(X_factor) < 2:
        return pd.DataFrame()
    n_24h = period_return_bars(freq)["24h"]
    rows = []
    for pair_id in returns_df.columns:
        if str(pair_id).endswith("_spot"):
            continue
        y_asset = returns_df[pair_id]
        betas, intercept = compute_ols_betas(y_asset, X_factor)
        if len(betas) == 0 or np.isnan(intercept):
            continue
        resid_series = compute_residual_returns(y_asset, X_factor, betas, float(intercept))
        if len(resid_series) < n_24h:
            continue
        res_24 = compute_residual_lookback_return(resid_series, n_24h)
        res_vol = compute_residual_vol(resid_series, n_24h, freq)
        resid_equity = np.exp(resid_series.cumsum())
        _, res_dd = compute_drawdown_from_equity(resid_equity)
        rows.append(
            {
                "label": meta.get(pair_id, pair_id),
                "residual_return_24h": res_24,
                "residual_annual_vol": res_vol,
                "residual_max_drawdown": res_dd,
            }
        )
    df = (
        pd.DataFrame(rows)
        .dropna(subset=["residual_return_24h"])
        .sort_values("residual_return_24h", ascending=False)
        .head(top)
    )
    return df


def run_risk_snapshot(bars: pd.DataFrame, freq: str, top_vol: int = 10, top_dd: int = 10) -> tuple:
    """Top top_vol by annual_vol (24h rolling); worst top_dd by max_drawdown. Same vol definition as momentum/vol tables."""
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()
    vol_window = _vol_window_bars(freq)
    periods_yr = periods_per_year(freq)
    rows = []
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc")
        if "log_return" not in g.columns:
            g = g.copy()
            g["log_return"] = log_returns(g["close"])
        r = g["log_return"].dropna()
        if len(r) < vol_window:
            continue
        vol = r.rolling(vol_window).std(ddof=1).iloc[-1]
        annual_vol = float(vol * np.sqrt(periods_yr)) if not np.isnan(vol) else np.nan
        _, max_dd = compute_drawdown_from_log_returns(r)
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        rows.append(
            {
                "chain_id": cid,
                "pair_address": addr,
                "label": label,
                "annual_vol": annual_vol,
                "max_drawdown": max_dd,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    by_vol = df.dropna(subset=["annual_vol"]).nlargest(top_vol, "annual_vol")
    by_dd = df.dropna(subset=["max_drawdown"]).nsmallest(top_dd, "max_drawdown")
    return by_vol, by_dd


def run_market_structure(bars: pd.DataFrame, freq: str, db_path_override: str) -> tuple:
    """Correlation, beta, rolling, regime, beta_state table, ratio table, dispersion stats."""
    if bars.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            np.nan,
            np.nan,
        )
    bars = bars.copy()
    bars["pair_id"] = bars["chain_id"].astype(str) + ":" + bars["pair_address"].astype(str)
    bars["label"] = bars["base_symbol"].fillna("").astype(str) + "/" + bars["quote_symbol"].fillna("").astype(str)
    returns_df = bars.pivot_table(index="ts_utc", columns="pair_id", values="log_return").dropna(how="all")
    meta = bars.groupby("pair_id")["label"].last().to_dict()
    if returns_df.empty or returns_df.shape[1] < 1:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            np.nan,
            np.nan,
        )
    returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db_path_override, freq)
    factor_ret = get_factor_returns(returns_df, meta, db_path_override, freq)
    btc_price = load_spot_price_resampled(db_path_override, "BTC", freq)
    corr_df = (
        compute_correlation_matrix(returns_df).rename(index=meta, columns=meta)
        if returns_df.shape[1] >= 2
        else pd.DataFrame()
    )
    win_short, win_long = rolling_windows_for_freq(freq)
    beta_compress_threshold = 0.15
    rows_beta = []
    rows_rolling = []
    rows_regime = []
    rows_beta_state = []
    rows_ratio = []
    vol_short, vol_medium = 24, 48
    n_24h = period_return_bars(freq)["24h"]
    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        if "log_return" not in g.columns:
            g = g.copy()
            g["log_return"] = log_returns(g["close"])
        r = g["log_return"].dropna()
        if len(r) < 2:
            continue
        label = meta.get(f"{cid}:{addr}", f"{cid}/{addr}")
        factor_aligned = factor_ret.reindex(r.index).dropna() if factor_ret is not None else None
        beta = (
            compute_beta_vs_factor(r, factor_aligned)
            if factor_aligned is not None and len(factor_aligned) >= 2
            else np.nan
        )
        rows_beta.append({"label": label, "beta_vs_btc": beta})
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
        beta_compression = compute_beta_compression(beta_24, beta_72)
        beta_state = classify_beta_state(beta_24, beta_72, beta_compress_threshold)
        rows_beta_state.append(
            {
                "label": label,
                "beta_btc_24": beta_24,
                "beta_btc_72": beta_72,
                "beta_compression": beta_compression,
                "beta_state": beta_state,
            }
        )
        beta_hat = beta_72 if (beta_72 is not None and not np.isnan(beta_72)) else beta
        excess_return_24h = np.nan
        if factor_aligned is not None and len(factor_aligned) >= 2 and beta_hat is not None and not np.isnan(beta_hat):
            r_excess = compute_excess_log_returns(r, factor_aligned, float(beta_hat))
            if len(r_excess) >= 2:
                excess_return_24h = (
                    compute_excess_lookback_return(r_excess, n_24h) if len(r_excess) >= n_24h else np.nan
                )
        rows_rolling.append(
            {
                "label": label,
                "corr_btc_24": corr_24,
                "corr_btc_72": corr_72,
                "beta_btc_24": beta_24,
                "beta_btc_72": beta_72,
                "excess_return_24h": excess_return_24h,
            }
        )
        ratio_return_24h = ratio_level = np.nan
        if not btc_price.empty:
            price_series = g["close"].dropna()
            ratio_series = compute_ratio_series(price_series, btc_price)
            if len(ratio_series) >= 2:
                ratio_return_24h = (
                    compute_lookback_return_from_price(ratio_series, n_24h) if len(ratio_series) >= n_24h else np.nan
                )
                ratio_level = float(ratio_series.iloc[-1])
        rows_ratio.append({"label": label, "ratio_return_24h": ratio_return_24h, "ratio_level": ratio_level})
        short_vol = r.rolling(vol_short).std(ddof=1).iloc[-1] if len(r) >= vol_short else np.nan
        medium_vol = r.rolling(min(vol_medium, len(r))).std(ddof=1).iloc[-1] if len(r) >= vol_medium else short_vol
        regime = (
            classify_vol_regime(short_vol, medium_vol)
            if not (np.isnan(short_vol) or np.isnan(medium_vol) or medium_vol == 0)
            else "unknown"
        )
        rows_regime.append({"label": label, "regime": regime})
    beta_df = pd.DataFrame(rows_beta)
    rolling_df = pd.DataFrame(rows_rolling)
    regime_df = pd.DataFrame(rows_regime)
    beta_state_df = pd.DataFrame(rows_beta_state)
    ratio_df = pd.DataFrame(rows_ratio)
    disp_latest = disp_z_latest = np.nan
    if returns_df.shape[1] >= 2:
        disp_series = compute_dispersion_index(returns_df)
        if not disp_series.empty:
            disp_latest = float(disp_series.iloc[-1])
        w_disp = dispersion_window_for_freq(freq)
        if len(disp_series) >= w_disp:
            disp_z = compute_dispersion_zscore(disp_series, w_disp)
            if not disp_z.empty and disp_z.notna().any():
                disp_z_latest = float(disp_z.iloc[-1])
    return corr_df, beta_df, rolling_df, regime_df, beta_state_df, ratio_df, disp_latest, disp_z_latest


def liquidity_drops(snap: pd.DataFrame, pct_threshold: float = 0.20) -> pd.DataFrame:
    """Pairs with liquidity drop > threshold (last vs prior day)."""
    if snap.empty or "liquidity_usd" not in snap.columns:
        return pd.DataFrame()
    snap = snap.copy()
    snap["ts_utc"] = pd.to_datetime(snap["ts_utc"], utc=True)
    snap["date"] = snap["ts_utc"].dt.date
    last = snap[snap["date"] == snap["date"].max()].groupby(["chain_id", "pair_address"])["liquidity_usd"].median()
    prev = snap[snap["date"] < snap["date"].max()].groupby(["chain_id", "pair_address"])["liquidity_usd"].median()
    join = (last / prev - 1.0).dropna()
    join = join[join < -pct_threshold]
    df = join.reset_index()
    df.columns = ["chain_id", "pair_address", "liquidity_change_pct"]
    return df


def regime_shift(bars: pd.DataFrame, window: int = 24) -> str:
    """Simple regime: vol trend (rising/falling)."""
    if bars.empty or len(bars) < window * 2:
        return "insufficient_data"
    close = bars.sort_values("ts_utc")["close"]
    lr = log_returns(close)
    vol = lr.rolling(window).std(ddof=1).dropna()
    if len(vol) < 2:
        return "unknown"
    recent = vol.tail(window).mean()
    prior = vol.iloc[:-window].tail(window).mean()
    if recent > prior * 1.2:
        return "vol_rising"
    if recent < prior * 0.8:
        return "vol_falling"
    return "stable"


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser(description="Daily report")
    ap.add_argument("--db", default=None)
    ap.add_argument("--freq", default=None)
    ap.add_argument("--out-dir", default="reports", help="Output directory for report and CSV")
    ap.add_argument("--save-charts", action="store_true", help="Save PNG charts for top 5 momentum")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)

    db = args.db or (db_path() if callable(db_path) else db_path())
    freq = args.freq or (default_freq() if callable(default_freq) else "1h")
    min_bars_count = config_min_bars() if callable(config_min_bars) else 48
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        bars = load_bars(freq, db_path_override=db, min_bars=min_bars_count)
    except FileNotFoundError:
        bars = pd.DataFrame()
    snap = load_snapshots(db_path_override=db, apply_filters=True)

    momentum_df = run_momentum_scan(bars, freq, top=args.top)
    vol_df = run_vol_scan(bars, freq, top=args.top)
    top_vol_df, worst_dd_df = run_risk_snapshot(bars, freq, top_vol=10, top_dd=10)
    corr_df, beta_df, rolling_btc_df, regime_summary_df, beta_state_df, ratio_df, disp_latest, disp_z_latest = (
        run_market_structure(bars, freq, db)
    )
    residual_leaders_df = run_residual_leaders(bars, freq, db, top=args.top)

    # Market regime: one label from dispersion_z, vol_regime, beta_state
    vol_regime = (
        regime_summary_df["regime"].mode().iloc[0]
        if not regime_summary_df.empty and "regime" in regime_summary_df.columns
        else "unknown"
    )
    beta_state = (
        beta_state_df["beta_state"].mode().iloc[0]
        if not beta_state_df.empty and "beta_state" in beta_state_df.columns
        else "unknown"
    )
    market_regime_label = classify_market_regime(disp_z_latest, vol_regime, beta_state)
    regime_explanation = explain_regime(market_regime_label)

    # Signals: detect from latest metrics, log, then load last 24h
    signal_rows = []
    res_by_label = (
        residual_leaders_df.set_index("label")["residual_return_24h"]
        if not residual_leaders_df.empty
        else pd.Series(dtype=float)
    )
    if not rolling_btc_df.empty:
        for _, row in rolling_btc_df.iterrows():
            lbl = row.get("label", "")
            b24 = row.get("beta_btc_24")
            b72 = row.get("beta_btc_72")
            res_24 = res_by_label.get(lbl, np.nan) if not res_by_label.empty else np.nan
            signal_rows.extend(
                detect_signals(
                    beta_btc_24=b24, beta_btc_72=b72, dispersion_z=disp_z_latest, residual_return_24h=res_24, label=lbl
                )
            )
    if signal_rows:
        log_signals(db, signal_rows)
    signals_24h = load_signals(db, last_n=500)
    if not signals_24h.empty and "ts_utc" in signals_24h.columns:
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        signals_24h = signals_24h[signals_24h["ts_utc"] >= cutoff]

    liq_drops = liquidity_drops(snap, pct_threshold=0.20)
    regime = regime_shift(bars, window=24) if not bars.empty else "no_data"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def _table(df: pd.DataFrame) -> str:
        if df.empty:
            return "*No data*"
        return df.to_string(index=False)

    lines = [
        "# Daily Crypto Quant Report",
        f"Generated: {ts}",
        "",
        "## Top momentum (return_24h, annual_vol, annual_sharpe, max_drawdown)",
        "*(annual_vol = 24h rolling realized vol, annualized; same definition in all tables below)*",
        _table(momentum_df),
        "",
        "## Top volatility (annual_vol, return_24h, annual_sharpe, max_drawdown)",
        _table(vol_df),
        "",
        "## Residual leaders (top by residual_return_24h vs BTC_spot/ETH_spot)",
        _table(residual_leaders_df.round(4))
        if not residual_leaders_df.empty
        else "*No factor data or insufficient overlap*",
        "",
        "## Market Regime",
        f"dispersion_z: {disp_z_latest:.2f}" if not np.isnan(disp_z_latest) else "dispersion_z: N/A",
        f"vol_regime: {vol_regime}  |  beta_state: {beta_state}",
        f"**Regime:** {market_regime_label}",
        regime_explanation,
        "",
        "## Signals triggered (last 24h)",
        _table(signals_24h) if not signals_24h.empty else "*None*",
        "",
        "## Risk snapshot",
        "### Top 10 by annual_vol (24h rolling)",
        _table(top_vol_df),
        "",
        "### Worst 10 by max_drawdown (most negative)",
        _table(worst_dd_df),
        "",
        "## Market structure",
        "### Correlation matrix (log returns)",
        _table(corr_df.round(3)) if not corr_df.empty else "*Need 2+ pairs*",
        "",
        "### Beta vs BTC",
        _table(beta_df),
        "",
        "### Latest rolling corr/beta vs BTC_spot (top pairs)",
        _table(rolling_btc_df.round(4)) if not rolling_btc_df.empty else "*No data*",
        "",
        "### Excess return (BTC-hedged) — label, excess_return_24h, beta_btc_72, corr_btc_24",
        _table(
            rolling_btc_df[["label", "excess_return_24h", "beta_btc_72", "corr_btc_24"]]
            .sort_values("excess_return_24h", ascending=False)
            .round(4)
        )
        if not rolling_btc_df.empty and "excess_return_24h" in rolling_btc_df.columns
        else "*No data*",
        "",
        "### Volatility regime summary",
        _table(regime_summary_df),
        "",
        "### Beta state vs BTC",
        _table(beta_state_df.round(4)) if not beta_state_df.empty else "*No data*",
        "",
        "## Relative strength (SOL/BTC)",
        _table(ratio_df.round(4)) if not ratio_df.empty else "*No data*",
        "",
        "## Dispersion",
        f"Latest dispersion: {disp_latest:.6f}" if not np.isnan(disp_latest) else "*N/A*",
        f"Latest dispersion z-score: {disp_z_latest:.2f}" if not np.isnan(disp_z_latest) else "*N/A*",
        "Interpretation: z > +1 → high dispersion (relative value); z < -1 → low dispersion (macro beta)."
        if not np.isnan(disp_z_latest)
        else "",
        "",
        "## Regime (vol trend)",
        regime,
        "",
        "## Notable liquidity drops (>20%)",
        _table(liq_drops),
    ]
    report_text = "\n".join(lines)

    report_path = out_dir / f"report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Report: {report_path}")

    csv_path = out_dir / f"daily_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    combined = pd.DataFrame()
    if not momentum_df.empty:
        momentum_df["metric"] = "momentum"
        combined = pd.concat([combined, momentum_df], ignore_index=True)
    if not vol_df.empty:
        vol_df["metric"] = "volatility"
        combined = pd.concat([combined, vol_df], ignore_index=True)
    if not combined.empty:
        combined.to_csv(csv_path, index=False)
        print(f"CSV: {csv_path}")

    if args.save_charts and not momentum_df.empty and not bars.empty:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            for i, row in momentum_df.head(5).iterrows():
                g = bars[
                    (bars["chain_id"] == row["chain_id"]) & (bars["pair_address"] == row["pair_address"])
                ].sort_values("ts_utc")
                if g.empty:
                    continue
                fig, ax = plt.subplots(1, 1)
                ax.plot(g["ts_utc"], g["close"])
                ax.set_title(f"{row['label']} — close")
                ax.tick_params(axis="x", rotation=45)
                plt.tight_layout()
                safe = "".join(c for c in row["label"] if c.isalnum() or c in "/_")[:30]
                plt.savefig(out_dir / f"chart_{safe}.png", dpi=150)
                plt.close()
            print(f"Charts saved to {out_dir}")
        except Exception as e:
            print(f"Charts skip: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
