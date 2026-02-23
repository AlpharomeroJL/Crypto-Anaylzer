#!/usr/bin/env python3
"""
Analyze Dexscreener snapshot data from SQLite:
- Resample to a consistent timeframe (e.g., 5min)
- Compute log returns, cumulative returns
- Rolling volatility
- Sharpe + Sortino (risk-free = 0 by default)
- Plots: cumulative returns, rolling vol, returns histogram

Uses the project's sol_monitor_snapshots table (dex_data.sqlite).
For a DB with a generic "snapshots" table, use --table snapshots.

Usage:
  python dex_analyze.py --db dex_data.sqlite --freq 5min --window 288
  python dex_analyze.py --db dex_data.sqlite --freq 1h --window 24 --top 10
  python dex_analyze.py --pair ethereum:0x.... --pair solana:....   # optional filtering
  python dex_analyze.py --table snapshots --db dex_snapshots.sqlite  # alternate table

Notes:
- window is in number of resampled bars (e.g. 288 bars of 5min = 1 day)
- Liquidity filter (default): liquidity_usd > 100k, vol_h24 > 500k. Use --no-liquidity-filter to disable.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from crypto_analyzer.data import append_spot_returns_to_returns_df, get_factor_returns, load_spot_price_resampled
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
    compute_excess_cum_return,
    compute_excess_log_returns,
    compute_excess_lookback_return,
    compute_lookback_return,
    compute_lookback_return_from_price,
    compute_ratio_series,
    compute_rolling_beta,
    compute_rolling_corr,
    dispersion_window_for_freq,
    period_return_bars,
    periods_per_year,
    rolling_windows_for_freq,
)

# Default liquidity filter: drop low-liquidity / low-volume pairs (garbage pairs)
DEFAULT_MIN_LIQUIDITY_USD = 100_000
DEFAULT_MIN_VOL_H24 = 500_000


@dataclass
class PairKey:
    chain_id: str
    pair_address: str

    @property
    def id(self) -> str:
        return f"{self.chain_id}:{self.pair_address}"


def parse_pair_arg(s: str) -> PairKey:
    if ":" not in s:
        raise ValueError("Pair must be formatted like chainId:pairAddress")
    c, p = s.split(":", 1)
    return PairKey(c.strip(), p.strip())


def load_snapshots(
    db_path: str,
    table: str = "sol_monitor_snapshots",
    price_col: str = "dex_price_usd",
    only_pairs: Optional[List[PairKey]] = None,
    min_liquidity_usd: Optional[float] = DEFAULT_MIN_LIQUIDITY_USD,
    min_vol_h24: Optional[float] = DEFAULT_MIN_VOL_H24,
) -> pd.DataFrame:
    """
    Load snapshot data. For sol_monitor_snapshots we use dex_price_usd;
    for a generic 'snapshots' table we expect a column named price_usd.
    Optionally filter by liquidity_usd and vol_h24 (None = no filter).
    """
    where = ""
    params: List[str] = []
    if only_pairs:
        clauses = []
        for pk in only_pairs:
            clauses.append("(chain_id=? AND pair_address=?)")
            params.extend([pk.chain_id, pk.pair_address])
        where = "WHERE " + " OR ".join(clauses)

    # Column mapping: project table has dex_price_usd; generic snapshots has price_usd
    select_price = f"{price_col} AS price_usd" if price_col != "price_usd" else "price_usd"

    query = f"""
      SELECT
        ts_utc,
        chain_id,
        pair_address,
        base_symbol,
        quote_symbol,
        {select_price},
        liquidity_usd,
        vol_h24
      FROM {table}
      {where}
      ORDER BY ts_utc ASC
    """

    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(query, con, params=params)

    # Parse time and numerics
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc", "chain_id", "pair_address", "price_usd"])
    df["price_usd"] = pd.to_numeric(df["price_usd"], errors="coerce")
    df = df.dropna(subset=["price_usd"])

    # Liquidity filter: drop garbage pairs (improves Sharpe ranking stability)
    if min_liquidity_usd is not None or min_vol_h24 is not None:
        mask = pd.Series(True, index=df.index)
        if min_liquidity_usd is not None and "liquidity_usd" in df.columns:
            liq = pd.to_numeric(df["liquidity_usd"], errors="coerce")
            mask = mask & (liq > min_liquidity_usd)
        if min_vol_h24 is not None and "vol_h24" in df.columns:
            vol = pd.to_numeric(df["vol_h24"], errors="coerce")
            mask = mask & (vol > min_vol_h24)
        df = df.loc[mask]

    return df


def compute_metrics(
    df: pd.DataFrame,
    freq: str,
    window: int,
    rf: float = 0.0,
    db_path_override: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """
    Returns:
      - panel: multi-index columns [pair_id -> fields]
      - summary: per-pair metrics table (DEX pairs only; includes annual_sharpe, max_drawdown, return_24h, beta_vs_btc, regime).
      - returns_df: index=ts_utc, columns=DEX pair_ids + ETH_spot, BTC_spot (for correlation; beta uses BTC_spot).
      - meta: pair_id/label -> display name.
    """
    periods_yr = periods_per_year(freq)
    lookback_24h = period_return_bars(freq)["24h"]
    medium_window = max(window * 2, 48)
    df = df.copy()
    df["pair_id"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    df = df.set_index("ts_utc")

    panels = []
    meta = {}

    for pair_id, g in df.groupby("pair_id"):
        g = g.sort_index()
        # Keep a representative label
        base = g["base_symbol"].dropna().iloc[-1] if g["base_symbol"].notna().any() else ""
        quote = g["quote_symbol"].dropna().iloc[-1] if g["quote_symbol"].notna().any() else ""
        meta[pair_id] = f"{base}/{quote}".strip("/")

        # resample to last price in interval
        s = g["price_usd"].resample(freq).last().dropna()
        if len(s) < max(20, window + 2):
            continue

        log_ret = np.log(s).diff()
        cum_log = log_ret.cumsum()
        cum_ret = np.exp(cum_log) - 1.0

        # rolling volatility (std of log returns) annualized-ish depends on freq; we also output raw
        roll_std = log_ret.rolling(window).std()

        # Sharpe/Sortino over the full period (using per-bar returns)
        # Convert risk-free to per-bar if you want; for now rf=0 simplifies.
        r = log_ret.dropna()
        if len(r) < 5:
            continue

        mean_r = r.mean()
        std_r = r.std(ddof=1)
        downside = r[r < 0]
        downside_std = downside.std(ddof=1) if len(downside) > 1 else np.nan

        sharpe = (mean_r - rf) / std_r if std_r and not np.isnan(std_r) else np.nan
        sortino = (mean_r - rf) / downside_std if downside_std and not np.isnan(downside_std) else np.nan

        tmp = pd.DataFrame(
            {
                "price": s,
                "log_return": log_ret,
                "cum_return": cum_ret,
                "roll_vol": roll_std,
            }
        )
        tmp.columns = pd.MultiIndex.from_product([[pair_id], tmp.columns])
        panels.append(tmp)

    if not panels:
        raise RuntimeError("No pairs had enough data after resampling. Try a larger timeframe (e.g., 15min/1h).")

    panel = pd.concat(panels, axis=1).sort_index()

    # Returns matrix: DEX bars + spot (ETH, BTC) for correlation and factor
    returns_df = pd.DataFrame({pid: panel[(pid, "log_return")].dropna() for pid in panel.columns.levels[0]}).dropna(
        how="all"
    )
    returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db_path_override, freq)
    factor_ret = (
        get_factor_returns(returns_df, meta, db_path_override, freq, factor_symbol="BTC")
        if returns_df.shape[1] >= 1
        else None
    )
    btc_price = (
        load_spot_price_resampled(db_path_override, "BTC", freq)
        if db_path_override
        else load_spot_price_resampled(None, "BTC", freq)
    )

    win_short, win_long = rolling_windows_for_freq(freq)
    beta_compress_threshold = 0.15

    # summary metrics
    summary_rows = []
    for pair_id in panel.columns.levels[0]:
        r = panel[(pair_id, "log_return")].dropna()
        if len(r) < 5:
            continue
        mean_r = r.mean()
        std_r = r.std(ddof=1)
        downside = r[r < 0]
        downside_std = downside.std(ddof=1) if len(downside) > 1 else np.nan
        sharpe = (mean_r - rf) / std_r if std_r and not np.isnan(std_r) else np.nan
        sortino = (mean_r - rf) / downside_std if downside_std and not np.isnan(downside_std) else np.nan

        vol = std_r
        annual_vol = float(vol * np.sqrt(periods_yr)) if vol is not None and not np.isnan(vol) else np.nan
        total_return = panel[(pair_id, "cum_return")].dropna().iloc[-1]
        _, max_dd = compute_drawdown_from_log_returns(r)
        return_24h = compute_lookback_return(r, lookback_24h) if len(r) >= lookback_24h else np.nan
        ann_sharpe = annualize_sharpe(float(sharpe) if not np.isnan(sharpe) else np.nan, freq)
        beta_btc = (
            compute_beta_vs_factor(r, factor_ret)
            if factor_ret is not None and not factor_ret.dropna().empty
            else np.nan
        )
        short_vol = r.rolling(window).std(ddof=1).iloc[-1] if len(r) >= window else np.nan
        medium_vol = (
            r.rolling(min(medium_window, len(r))).std(ddof=1).iloc[-1] if len(r) >= medium_window else short_vol
        )
        regime = (
            classify_vol_regime(short_vol, medium_vol)
            if short_vol is not None and not np.isnan(short_vol) and medium_vol and not np.isnan(medium_vol)
            else "unknown"
        )

        # Rolling corr/beta vs BTC_spot (latest non-NaN)
        corr_24 = corr_72 = beta_24 = beta_72 = np.nan
        if factor_ret is not None and not factor_ret.dropna().empty:
            roll_corr_24 = compute_rolling_corr(r, factor_ret, win_short)
            roll_corr_72 = compute_rolling_corr(r, factor_ret, win_long)
            roll_beta_24 = compute_rolling_beta(r, factor_ret, win_short)
            roll_beta_72 = compute_rolling_beta(r, factor_ret, win_long)
            if not roll_corr_24.empty:
                corr_24 = float(roll_corr_24.dropna().iloc[-1]) if roll_corr_24.notna().any() else np.nan
            if not roll_corr_72.empty:
                corr_72 = float(roll_corr_72.dropna().iloc[-1]) if roll_corr_72.notna().any() else np.nan
            if not roll_beta_24.empty:
                beta_24 = float(roll_beta_24.dropna().iloc[-1]) if roll_beta_24.notna().any() else np.nan
            if not roll_beta_72.empty:
                beta_72 = float(roll_beta_72.dropna().iloc[-1]) if roll_beta_72.notna().any() else np.nan

        beta_compression = compute_beta_compression(beta_24, beta_72)
        beta_state = classify_beta_state(beta_24, beta_72, beta_compress_threshold)

        ratio_return_24h = ratio_cum_return = np.nan
        if not btc_price.empty and btc_price is not None:
            price_series = panel[(pair_id, "price")].dropna()
            ratio_series = compute_ratio_series(price_series, btc_price)
            if len(ratio_series) >= 2:
                ratio_return_24h = (
                    compute_lookback_return_from_price(ratio_series, lookback_24h)
                    if len(ratio_series) >= lookback_24h
                    else np.nan
                )
                ratio_cum_return = float((ratio_series.iloc[-1] / ratio_series.iloc[0]) - 1.0)

        # BTC-hedged excess return (beta_hat = beta_btc_72, fallback beta_vs_btc)
        beta_hat_used = beta_72 if (beta_72 is not None and not np.isnan(beta_72)) else beta_btc
        beta_hat = beta_hat_used
        excess_return_24h = excess_total_cum_return = excess_max_drawdown = np.nan
        if factor_ret is not None and not factor_ret.dropna().empty and beta_hat is not None and not np.isnan(beta_hat):
            r_excess = compute_excess_log_returns(r, factor_ret, float(beta_hat))
            if len(r_excess) >= 2:
                excess_cum = compute_excess_cum_return(r_excess)
                excess_return_24h = (
                    compute_excess_lookback_return(r_excess, lookback_24h) if len(r_excess) >= lookback_24h else np.nan
                )
                excess_total_cum_return = float(excess_cum.iloc[-1]) if len(excess_cum) else np.nan
                excess_equity = np.exp(r_excess.cumsum())
                _, excess_max_drawdown = compute_drawdown_from_equity(excess_equity)

        # Factor/residual: BTC_spot (+ ETH_spot if present); align on ts_utc
        residual_return_24h = residual_total_cum_return = residual_annual_vol = residual_max_drawdown = np.nan
        factor_cols = [c for c in ["BTC_spot", "ETH_spot"] if c in returns_df.columns]
        if factor_cols and pair_id in returns_df.columns:
            X_factor = build_factor_matrix(returns_df, factor_cols=factor_cols)
            y_asset = returns_df[pair_id]
            if not X_factor.empty and len(X_factor) >= 2:
                betas, intercept = compute_ols_betas(y_asset, X_factor)
                if len(betas) > 0 and not np.isnan(intercept):
                    resid_series = compute_residual_returns(y_asset, X_factor, betas, float(intercept))
                    if len(resid_series) >= 2:
                        residual_return_24h = (
                            compute_residual_lookback_return(resid_series, lookback_24h)
                            if len(resid_series) >= lookback_24h
                            else np.nan
                        )
                        resid_cum = np.exp(resid_series.cumsum()) - 1.0
                        residual_total_cum_return = float(resid_cum.iloc[-1]) if len(resid_cum) else np.nan
                        residual_annual_vol = compute_residual_vol(resid_series, lookback_24h, freq)
                        resid_equity = np.exp(resid_series.cumsum())
                        _, residual_max_drawdown = compute_drawdown_from_equity(resid_equity)

        summary_rows.append(
            {
                "pair_id": pair_id,
                "label": meta.get(pair_id, ""),
                "bars": int(r.shape[0]),
                "total_cum_return": float(total_return),
                "mean_log_return": float(mean_r),
                "vol_log_return": float(vol) if not np.isnan(vol) else np.nan,
                "annual_vol": annual_vol,
                "sharpe": float(sharpe) if not np.isnan(sharpe) else np.nan,
                "annual_sharpe": ann_sharpe,
                "sortino": float(sortino) if not np.isnan(sortino) else np.nan,
                "max_drawdown": max_dd,
                "return_24h": return_24h,
                "beta_vs_btc": beta_btc,
                "corr_btc_24": corr_24,
                "corr_btc_72": corr_72,
                "beta_btc_24": beta_24,
                "beta_btc_72": beta_72,
                "beta_compression": beta_compression,
                "beta_state": beta_state,
                "beta_hat_used": beta_hat_used,
                "ratio_return_24h": ratio_return_24h,
                "ratio_cum_return": ratio_cum_return,
                "excess_return_24h": excess_return_24h,
                "excess_total_cum_return": excess_total_cum_return,
                "excess_max_drawdown": excess_max_drawdown,
                "residual_return_24h": residual_return_24h,
                "residual_total_cum_return": residual_total_cum_return,
                "residual_annual_vol": residual_annual_vol,
                "residual_max_drawdown": residual_max_drawdown,
                "regime": regime,
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values("sharpe", ascending=False)
    return panel, summary, returns_df, meta, factor_ret, btc_price


def plot_top(
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    top: int,
    window: int,
    freq: str,
    factor_ret: Optional[pd.Series] = None,
    btc_price: Optional[pd.Series] = None,
    disp_series: Optional[pd.Series] = None,
    disp_z_series: Optional[pd.Series] = None,
    returns_df: Optional[pd.DataFrame] = None,
) -> None:
    top_pairs = summary["pair_id"].head(top).tolist()

    # Cumulative returns
    plt.figure()
    for pid in top_pairs:
        s = panel[(pid, "cum_return")].dropna()
        if len(s):
            plt.plot(
                s.index,
                s.values,
                label=summary.loc[summary["pair_id"] == pid, "label"].iloc[0] or pid[:10],
            )
    plt.title(f"Cumulative Returns (log->cum) | freq={freq}")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Cumulative return")
    plt.legend(loc="best")
    plt.tight_layout()

    # Rolling vol
    plt.figure()
    for pid in top_pairs:
        s = panel[(pid, "roll_vol")].dropna()
        if len(s):
            plt.plot(
                s.index,
                s.values,
                label=summary.loc[summary["pair_id"] == pid, "label"].iloc[0] or pid[:10],
            )
    plt.title(f"Rolling Volatility (std of log returns) | window={window} bars | freq={freq}")
    plt.xlabel("Time (UTC)")
    plt.ylabel("Rolling vol")
    plt.legend(loc="best")
    plt.tight_layout()

    # SOL/BTC ratio (asset/BTC for each top pair)
    if btc_price is not None and not btc_price.empty and top_pairs:
        plt.figure()
        for pid in top_pairs:
            price_series = panel[(pid, "price")].dropna()
            if price_series.empty:
                continue
            ratio_series = compute_ratio_series(price_series, btc_price)
            if len(ratio_series) < 2:
                continue
            lbl = (
                summary.loc[summary["pair_id"] == pid, "label"].iloc[0]
                if len(summary.loc[summary["pair_id"] == pid])
                else pid[:10]
            )
            plt.plot(ratio_series.index, ratio_series.values, label=lbl or pid[:10])
        plt.title("Asset/BTC ratio")
        plt.xlabel("Time (UTC)")
        plt.ylabel("Ratio")
        plt.legend(loc="best")
        plt.tight_layout()

    # Dispersion index (cross-sectional std of returns)
    if disp_series is not None and not disp_series.empty:
        fig, ax1 = plt.subplots()
        ax1.plot(disp_series.index, disp_series.values, color="tab:blue", label="Dispersion")
        ax1.set_ylabel("Dispersion (std)")
        ax1.set_xlabel("Time (UTC)")
        if disp_z_series is not None and not disp_z_series.empty:
            ax2 = ax1.twinx()
            ax2.plot(
                disp_z_series.index, disp_z_series.values, color="tab:orange", alpha=0.8, label="Dispersion z-score"
            )
            ax2.set_ylabel("Z-score")
            ax2.axhline(1, color="gray", linestyle="--", alpha=0.5)
            ax2.axhline(-1, color="gray", linestyle="--", alpha=0.5)
        plt.title("Cross-asset dispersion index")
        plt.tight_layout()

    # BTC-hedged cumulative return (excess vs BTC_spot)
    if factor_ret is not None and not factor_ret.dropna().empty and top_pairs:
        plt.figure()
        for pid in top_pairs:
            r = panel[(pid, "log_return")].dropna()
            if len(r) < 2:
                continue
            row = summary.loc[summary["pair_id"] == pid].iloc[0]
            beta_hat = row.get("beta_btc_72")
            if beta_hat is None or (isinstance(beta_hat, float) and np.isnan(beta_hat)):
                beta_hat = row.get("beta_vs_btc")
            if beta_hat is None or (isinstance(beta_hat, float) and np.isnan(beta_hat)):
                continue
            r_excess = compute_excess_log_returns(r, factor_ret, float(beta_hat))
            if len(r_excess) < 2:
                continue
            excess_cum = compute_excess_cum_return(r_excess)
            lbl = row.get("label") or pid[:10]
            plt.plot(excess_cum.index, excess_cum.values, label=lbl)
        plt.title(f"BTC-hedged cumulative return (excess vs BTC_spot) | freq={freq}")
        plt.xlabel("Time (UTC)")
        plt.ylabel("Excess cum return")
        plt.legend(loc="best")
        plt.tight_layout()

    # Residual cumulative return (top pair; factor model residual)
    if top_pairs and returns_df is not None:
        factor_cols = [c for c in ["BTC_spot", "ETH_spot"] if c in returns_df.columns]
        pid = top_pairs[0]
        if factor_cols and pid in returns_df.columns:
            X_factor = build_factor_matrix(returns_df, factor_cols=factor_cols)
            y_asset = returns_df[pid]
            if not X_factor.empty and len(X_factor) >= 2:
                betas, intercept = compute_ols_betas(y_asset, X_factor)
                if len(betas) > 0 and not np.isnan(intercept):
                    resid_series = compute_residual_returns(y_asset, X_factor, betas, float(intercept))
                    if len(resid_series) >= 2:
                        resid_cum = np.exp(resid_series.cumsum()) - 1.0
                        lbl = (
                            summary.loc[summary["pair_id"] == pid, "label"].iloc[0]
                            if len(summary.loc[summary["pair_id"] == pid])
                            else pid[:10]
                        )
                        plt.figure()
                        plt.plot(resid_cum.index, resid_cum.values, label=lbl or pid[:10])
                        plt.title(
                            "Residual cumulative return (vs BTC_spot"
                            + (" + ETH_spot" if "ETH_spot" in factor_cols else "")
                            + f") | {lbl or pid} | freq={freq}"
                        )
                        plt.xlabel("Time (UTC)")
                        plt.ylabel("Residual cum return")
                        plt.legend(loc="best")
                        plt.tight_layout()

    # Histogram of returns for best Sharpe
    if top_pairs:
        pid = top_pairs[0]
        r = panel[(pid, "log_return")].dropna()
        plt.figure()
        plt.hist(r.values, bins=60)
        plt.title(f"Returns Histogram (log returns) | {summary.loc[summary['pair_id'] == pid, 'label'].iloc[0] or pid}")
        plt.xlabel("Log return")
        plt.ylabel("Count")
        plt.tight_layout()

    plt.show()


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--db",
        default="dex_data.sqlite",
        help="Path to SQLite DB (default: dex_data.sqlite)",
    )
    ap.add_argument(
        "--table",
        default="sol_monitor_snapshots",
        help="Table name (default: sol_monitor_snapshots; use 'snapshots' for generic)",
    )
    ap.add_argument(
        "--freq",
        default="5min",
        help="Resample frequency: 1min,5min,15min,1h,1D ...",
    )
    ap.add_argument(
        "--window",
        type=int,
        default=288,
        help="Rolling vol window in bars (default 288 ~ 1 day at 5min)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many pairs to plot (by Sharpe)",
    )
    ap.add_argument(
        "--rf",
        type=float,
        default=0.0,
        help="Risk-free rate per bar (default 0.0)",
    )
    ap.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Filter to a pair: chainId:pairAddress (repeatable)",
    )
    ap.add_argument(
        "--no-liquidity-filter",
        action="store_true",
        help="Disable liquidity/vol filter (default: liquidity_usd>100k, vol_h24>500k)",
    )
    ap.add_argument(
        "--min-liquidity",
        type=float,
        default=DEFAULT_MIN_LIQUIDITY_USD,
        metavar="USD",
        help=f"Min liquidity_usd (default: {DEFAULT_MIN_LIQUIDITY_USD:,.0f})",
    )
    ap.add_argument(
        "--min-vol-h24",
        type=float,
        default=DEFAULT_MIN_VOL_H24,
        metavar="USD",
        help=f"Min vol_h24 (default: {DEFAULT_MIN_VOL_H24:,.0f})",
    )
    args = ap.parse_args(argv)

    only_pairs = [parse_pair_arg(p) for p in args.pair] if args.pair else None
    min_liq = None if args.no_liquidity_filter else args.min_liquidity
    min_vol = None if args.no_liquidity_filter else args.min_vol_h24

    df = load_snapshots(
        args.db,
        table=args.table,
        price_col="dex_price_usd" if args.table == "sol_monitor_snapshots" else "price_usd",
        only_pairs=only_pairs,
        min_liquidity_usd=min_liq,
        min_vol_h24=min_vol,
    )
    panel, summary, returns_df, meta, factor_ret, btc_price = compute_metrics(
        df, freq=args.freq, window=args.window, rf=args.rf, db_path_override=args.db
    )

    disp_series = pd.Series(dtype=float)
    disp_z_series = pd.Series(dtype=float)
    if returns_df.shape[1] >= 2:
        disp_series = compute_dispersion_index(returns_df)
        w_disp = dispersion_window_for_freq(args.freq)
        if len(disp_series) >= w_disp:
            disp_z_series = compute_dispersion_zscore(disp_series, w_disp)
    dispersion_latest = float(disp_series.iloc[-1]) if not disp_series.empty and disp_series.notna().any() else np.nan
    dispersion_z_latest = (
        float(disp_z_series.iloc[-1]) if not disp_z_series.empty and disp_z_series.notna().any() else np.nan
    )
    if not np.isnan(dispersion_latest):
        print(
            f"Dispersion (latest): {dispersion_latest:.6f}"
            + (f"  dispersion_z: {dispersion_z_latest:.2f}" if not np.isnan(dispersion_z_latest) else "")
        )
        print()

    # Correlation matrix (DEX + ETH_spot, BTC_spot)
    if returns_df.shape[1] >= 2:
        corr = compute_correlation_matrix(returns_df)
        corr_display = corr.rename(index=meta, columns=meta)
        print("Correlation matrix (log returns):")
        print(corr_display.round(3).to_string())
        print()

    # Print leaderboard with trading-grade metrics
    cols = [
        "label",
        "bars",
        "total_cum_return",
        "return_24h",
        "vol_log_return",
        "annual_vol",
        "sharpe",
        "annual_sharpe",
        "sortino",
        "max_drawdown",
        "beta_vs_btc",
        "corr_btc_24",
        "corr_btc_72",
        "beta_btc_24",
        "beta_btc_72",
        "beta_compression",
        "beta_state",
        "beta_hat_used",
        "ratio_return_24h",
        "ratio_cum_return",
        "excess_return_24h",
        "excess_total_cum_return",
        "excess_max_drawdown",
        "residual_return_24h",
        "residual_total_cum_return",
        "residual_annual_vol",
        "residual_max_drawdown",
        "regime",
    ]
    cols = [c for c in cols if c in summary.columns]
    print(summary[["pair_id"] + cols].head(25).to_string(index=False))

    plot_top(
        panel,
        summary,
        top=args.top,
        window=args.window,
        freq=args.freq,
        factor_ret=factor_ret,
        btc_price=btc_price,
        disp_series=disp_series,
        disp_z_series=disp_z_series,
        returns_df=returns_df,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
