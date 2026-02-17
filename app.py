#!/usr/bin/env python3
"""
Crypto quant monitoring + research dashboard.
Pages: Overview (leaderboard), Pair detail, Scanner, Backtest.
Run: streamlit run app.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    db_path,
    default_freq,
    min_bars as config_min_bars,
    min_liquidity_usd as config_min_liq,
    min_vol_h24 as config_min_vol,
)
from data import append_spot_returns_to_returns_df, get_factor_returns, load_bars, load_snapshots, load_spot_price_resampled
from report_daily import run_momentum_scan, run_risk_snapshot, run_vol_scan
from dex_scan import run_scan as dex_run_scan
from crypto_analyzer.ui import _safe_df as _safe_df
from crypto_analyzer.regimes import classify_market_regime, explain_regime
from crypto_analyzer.signals import load_signals
from crypto_analyzer.walkforward import bars_per_day, run_walkforward_backtest
from crypto_analyzer.research_universe import get_research_assets
from crypto_analyzer.alpha_research import (
    compute_forward_returns,
    information_coefficient,
    ic_summary,
    ic_decay,
    rank_signal_df,
    signal_momentum_24h,
    signal_residual_momentum_24h,
    compute_dispersion_series,
    dispersion_zscore_series,
)
from crypto_analyzer.portfolio import (
    long_short_from_ranks,
    portfolio_returns_from_weights,
    turnover_from_weights,
    apply_costs_to_portfolio,
)
from crypto_analyzer.statistics import significance_summary
from features import (
    bars_per_year,
    classify_beta_state,
    classify_vol_regime,
    compute_beta_compression,
    compute_beta_vs_factor,
    compute_correlation_matrix,
    compute_dispersion_index,
    compute_dispersion_zscore,
    compute_drawdown_from_equity,
    compute_excess_cum_return,
    compute_excess_lookback_return,
    compute_excess_log_returns,
    compute_lookback_return_from_price,
    compute_ratio_series,
    compute_rolling_beta,
    compute_rolling_corr,
    compute_rolling_correlation,
    dispersion_window_for_freq,
    drawdown,
    log_returns,
    max_drawdown,
    rolling_volatility,
    rolling_windows_for_freq,
    period_return_bars,
)


def get_db_path() -> str:
    p = db_path() if callable(db_path) else db_path
    return p() if callable(p) else str(p)


def load_leaderboard(freq: str, min_liq: float, min_vol: float, min_bars_count: int):
    """Load snapshots, resample, compute metrics; return summary DataFrame."""
    df = load_snapshots(
        db_path_override=get_db_path(),
        min_liquidity_usd=min_liq,
        min_vol_h24=min_vol,
        apply_filters=True,
    )
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df["pair_id"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    window = 288 if "5" in freq else 24
    rows = []
    for pid, g in df.groupby("pair_id"):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        close = g["price_usd"].resample(freq).last().dropna()
        if len(close) < max(min_bars_count, window + 2):
            continue
        lr = log_returns(close)
        cum = np.exp(lr.cumsum()) - 1.0
        vol = lr.rolling(window).std(ddof=1)
        bars_yr = bars_per_year(freq)
        ann_vol = vol.iloc[-1] * np.sqrt(bars_yr) if not pd.isna(vol.iloc[-1]) else np.nan
        sharpe = (lr.mean() / lr.std(ddof=1)) * np.sqrt(bars_yr) if lr.std(ddof=1) and lr.std(ddof=1) != 0 else np.nan
        total_ret = cum.iloc[-1] if len(cum) else np.nan
        label = f"{g['base_symbol'].iloc[-1]}/{g['quote_symbol'].iloc[-1]}"
        rows.append({
            "pair_id": pid,
            "label": label,
            "chain_id": g['chain_id'].iloc[0],
            "pair_address": g['pair_address'].iloc[0],
            "bars": len(close),
            "total_cum_return": total_ret,
            "annual_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown(cum),
        })
    summary = pd.DataFrame(rows).sort_values("sharpe", ascending=False) if rows else pd.DataFrame()
    return df, summary


def main():
    st.set_page_config(page_title="Crypto Quant", layout="wide")
    st.title("Crypto Quant Monitoring & Research")

    db_path_str = st.sidebar.text_input("DB path", value=get_db_path())
    page = st.sidebar.radio("Page", ["Overview", "Pair detail", "Scanner", "Backtest", "Walk-Forward", "Market Structure", "Signals", "Research", "Institutional Research"])

    if page == "Overview":
        st.header("Overview")
        with st.sidebar.expander("Filters", expanded=True):
            freq = st.selectbox("Freq", ["5min", "15min", "1h", "1D"], index=2, key="overview_freq")
            min_liq = st.number_input("Min liquidity USD", value=float(config_min_liq() if callable(config_min_liq) else 250_000), min_value=0.0, step=50_000.0, key="overview_liq")
            min_vol = st.number_input("Min vol_h24 USD", value=float(config_min_vol() if callable(config_min_vol) else 500_000), min_value=0.0, step=50_000.0, key="overview_vol")
            _min_bars = int(config_min_bars() if callable(config_min_bars) else 48)
            min_bars_count = st.number_input("Min bars", value=_min_bars, min_value=10, max_value=10000, step=1, key="overview_bars")
            top_n = st.number_input("Top N", value=10, min_value=1, max_value=50, step=1, key="overview_top")
        snap_df, summary = load_leaderboard(freq, min_liq, min_vol, int(min_bars_count))
        try:
            bars_overview = load_bars(freq, db_path_override=db_path_str, min_bars=int(min_bars_count))
        except FileNotFoundError:
            bars_overview = pd.DataFrame()
        if summary.empty and (bars_overview.empty or bars_overview is None):
            st.warning("No data. Check DB path and run poller + materialize_bars if needed.")
        else:
            if not summary.empty:
                st.subheader("Leaderboard (snapshots)")
                st.dataframe(_safe_df(summary.head(50)), use_container_width=True)
            if not bars_overview.empty:
                st.subheader("Top momentum (return_24h, annual_vol, annual_sharpe, max_drawdown)")
                st.caption("annual_vol = 24h rolling realized vol, annualized.")
                momentum_df = run_momentum_scan(bars_overview, freq, top=int(top_n))
                if not momentum_df.empty:
                    st.dataframe(_safe_df(momentum_df.round(4)), use_container_width=True)
                else:
                    st.write("No momentum data.")
                st.subheader("Top volatility (annual_vol, return_24h, annual_sharpe, max_drawdown)")
                vol_df = run_vol_scan(bars_overview, freq, top=int(top_n))
                if not vol_df.empty:
                    st.dataframe(_safe_df(vol_df.round(4)), use_container_width=True)
                else:
                    st.write("No volatility data.")
                st.subheader("Risk snapshot")
                top_vol_df, worst_dd_df = run_risk_snapshot(bars_overview, freq, top_vol=10, top_dd=10)
                st.caption("Top 10 by annual_vol (24h rolling)")
                if not top_vol_df.empty:
                    st.dataframe(_safe_df(top_vol_df.round(4)), use_container_width=True)
                st.caption("Worst 10 by max_drawdown")
                if not worst_dd_df.empty:
                    st.dataframe(_safe_df(worst_dd_df.round(4)), use_container_width=True)

    elif page == "Pair detail":
        st.header("Pair detail")
        freq = st.selectbox("Freq", ["5min", "15min", "1h", "1D"], key="pair_freq")
        try:
            bars = load_bars(freq, db_path_override=db_path_str)
        except FileNotFoundError:
            bars = pd.DataFrame()
        if bars.empty:
            st.warning("No bars. Run materialize_bars.py --freq " + freq)
        else:
            pairs = bars.groupby(["chain_id", "pair_address"]).first().reset_index()
            pairs["label"] = pairs["base_symbol"].fillna("") + "/" + pairs["quote_symbol"].fillna("")
            sel = st.selectbox("Pair", options=range(len(pairs)), format_func=lambda i: pairs.iloc[i]["label"] or f"{pairs.iloc[i]['chain_id']}/{pairs.iloc[i]['pair_address'][:8]}")
            r = pairs.iloc[sel]
            g = bars[(bars["chain_id"] == r["chain_id"]) & (bars["pair_address"] == r["pair_address"])].sort_values("ts_utc")
            close = g.set_index("ts_utc")["close"]
            lr = log_returns(close)
            cum = np.exp(lr.cumsum()) - 1.0
            dd_ser = drawdown(cum)
            vol = rolling_volatility(lr, 24)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=close.index, y=close.values, name="Close"))
            st.plotly_chart(fig, use_container_width=True)
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=cum.index, y=cum.values, name="Cum return"))
            st.plotly_chart(fig2, use_container_width=True)
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(x=vol.index, y=vol.values, name="Rolling vol"))
            st.plotly_chart(fig3, use_container_width=True)
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=dd_ser.index, y=dd_ser.values, name="Drawdown"))
            st.plotly_chart(fig4, use_container_width=True)
            st.subheader("Returns histogram")
            fig5 = px.histogram(x=lr.dropna().values, nbins=50, labels={"x": "Log return"})
            st.plotly_chart(fig5, use_container_width=True)
            st.subheader("Latest metrics")
            last_vol = float(vol.iloc[-1]) if not vol.empty and vol.notna().any() else np.nan
            last_dd = float(dd_ser.iloc[-1]) if not dd_ser.empty and dd_ser.notna().any() else np.nan
            latest_metrics = pd.DataFrame([
                {"metric": "last_close", "value": float(close.iloc[-1])},
                {"metric": "rolling_vol_24", "value": round(last_vol, 6) if not np.isnan(last_vol) else "—"},
                {"metric": "current_drawdown", "value": round(last_dd, 4) if not np.isnan(last_dd) else "—"},
            ])
            st.dataframe(_safe_df(latest_metrics), use_container_width=True, hide_index=True)

    elif page == "Scanner":
        st.header("Scanner")
        with st.sidebar.expander("Filters", expanded=True):
            mode = st.selectbox("Mode", ["momentum", "residual_momentum", "volatility_breakout", "mean_reversion"], key="scan_mode")
            freq = st.selectbox("Freq", ["5min", "15min", "1h", "1D"], index=2, key="scan_freq")
            top = st.number_input("Top N", value=20, min_value=1, max_value=100, step=1, key="scan_top")
        with st.sidebar.expander("Risk Filters", expanded=False):
            min_corr_val = st.number_input("Min corr vs BTC", value=0.0, step=0.05, key="scan_min_corr")
            corr_window = st.radio("Corr window (bars)", [24, 72], index=0, key="scan_corr_win")
            min_beta_val = st.number_input("Min beta vs BTC", value=0.0, step=0.05, key="scan_min_beta")
            beta_window = st.radio("Beta window (bars)", [24, 72], index=1, key="scan_beta_win")
            min_excess_val = st.number_input("Min excess return 24h", value=0.0, step=0.0001, format="%.4f", key="scan_min_excess")
            min_disp_z_val = st.number_input("Min dispersion z", value=-999.0, step=0.1, key="scan_min_disp_z")
            only_beta_compressed = st.checkbox("Only beta compressed", value=False, key="scan_only_comp")
            only_beta_expanded = st.checkbox("Only beta expanded", value=False, key="scan_only_exp")
        min_corr = float(min_corr_val) if min_corr_val != 0.0 else None
        min_beta = float(min_beta_val) if min_beta_val != 0.0 else None
        min_excess_return = float(min_excess_val) if min_excess_val != 0.0 else None
        min_dispersion_z = float(min_disp_z_val) if min_disp_z_val > -900 else None
        run_scan_clicked = st.sidebar.button("Run scan", key="scan_run")
        if run_scan_clicked:
            with st.spinner("Running scan…"):
                try:
                    res, disp_latest, disp_z_latest, reasons = dex_run_scan(
                        db=db_path_str,
                        mode=mode,
                        freq=freq,
                        top=int(top),
                        min_corr=min_corr,
                        corr_window=int(corr_window),
                        min_beta=min_beta,
                        beta_window=int(beta_window),
                        min_excess_return=min_excess_return,
                        only_beta_compressed=only_beta_compressed,
                        only_beta_expanded=only_beta_expanded,
                        min_dispersion_z=min_dispersion_z,
                        z=2.0,
                    )
                    st.session_state["scan_result"] = (res, disp_latest, disp_z_latest, reasons)
                except Exception as e:
                    st.session_state["scan_result"] = (pd.DataFrame(), np.nan, np.nan, ["__error__", str(e)])
        if "scan_result" in st.session_state:
            res, disp_latest, disp_z_latest, reasons = st.session_state["scan_result"]
            st.caption("Dispersion (global): " + (f"{disp_latest:.6f}" if not np.isnan(disp_latest) else "—") + "  |  z: " + (f"{disp_z_latest:.2f}" if not np.isnan(disp_z_latest) else "—"))
            if res.empty:
                if reasons and reasons[0] == "__error__":
                    st.error(reasons[1] if len(reasons) > 1 else "Scan failed.")
                elif reasons:
                    st.warning("Filtered out because: " + "; ".join(reasons))
                else:
                    st.info("No signals.")
            else:
                display_cols = [c for c in ["chain_id", "pair_address", "label", "close", "liquidity_usd", "vol_h24", "return_24h", "return_zscore", "residual_return_24h", "residual_annual_vol", "residual_max_drawdown", "capacity_usd", "est_slippage_bps", "tradable", "annual_vol", "annual_sharpe", "max_drawdown", "beta_vs_btc", "corr_btc_24", "corr_btc_72", "beta_btc_24", "beta_btc_72", "excess_return_24h", "excess_total_cum_return", "excess_max_drawdown", "beta_compression", "beta_state", "regime"] if c in res.columns]
                out = res[display_cols] if display_cols else res
                st.dataframe(_safe_df(out.round(4)), use_container_width=True)
            sample_csv = (res.to_csv(index=False).encode("utf-8") if not res.empty else pd.DataFrame(columns=["chain_id", "pair_address", "label"]).to_csv(index=False).encode("utf-8"))
            st.download_button("Download scan CSV", data=sample_csv, file_name="scan_export.csv", mime="text/csv", key="scan_dl")
        else:
            st.info("Use sidebar filters and click **Run scan** to run.")

    elif page == "Backtest":
        st.header("Backtest")
        with st.sidebar.expander("Backtest settings", expanded=True):
            strategy = st.selectbox("Strategy", ["trend", "volatility_breakout"], key="bt_strategy")
            freq_bt = st.selectbox("Freq", ["5min", "15min", "1h", "1D"], index=2, key="bt_freq")
        run_bt_clicked = st.sidebar.button("Run backtest", key="bt_run")
        if run_bt_clicked:
            import traceback
            from backtest import metrics as backtest_metrics, run_trend_strategy, run_vol_breakout_strategy
            try:
                bars_bt = load_bars(freq_bt, db_path_override=db_path_str, min_bars=int(config_min_bars() if callable(config_min_bars) else 48))
                if bars_bt.empty:
                    st.session_state["bt_result"] = (None, None, None, "No bars. Run materialize_bars.py for this freq.")
                else:
                    if strategy == "trend":
                        _, equity_gross = run_trend_strategy(bars_bt, freq_bt, fee_bps=0, slippage_bps_fixed=0)
                        trades_df, equity = run_trend_strategy(bars_bt, freq_bt)
                    else:
                        _, equity_gross = run_vol_breakout_strategy(bars_bt, freq_bt, fee_bps=0, slippage_bps_fixed=0)
                        trades_df, equity = run_vol_breakout_strategy(bars_bt, freq_bt)
                    if equity is None or (hasattr(equity, "empty") and equity.empty):
                        st.session_state["bt_result"] = (None, None, None, "Not enough data for strategy.")
                    else:
                        met = backtest_metrics(equity, freq_bt)
                        met["n_trades"] = len(trades_df) if trades_df is not None and not trades_df.empty else 0
                        if not (equity_gross is None or (hasattr(equity_gross, "empty") and equity_gross.empty)) and len(equity_gross) >= 2:
                            met["gross_total_return"] = float(equity_gross.iloc[-1] / equity_gross.iloc[0] - 1.0)
                            met["net_total_return"] = met["total_return"]
                            met["cost_drag_pct"] = (met["gross_total_return"] - met["total_return"]) * 100.0
                        else:
                            met["gross_total_return"] = met["total_return"]
                            met["net_total_return"] = met["total_return"]
                            met["cost_drag_pct"] = 0.0
                        st.session_state["bt_result"] = (trades_df, equity, met, None)
            except Exception as e:
                st.session_state["bt_result"] = (None, None, None, traceback.format_exc())
        if "bt_result" in st.session_state:
            trades_df, equity, met, err = st.session_state["bt_result"]
            if err:
                st.error(err)
                with st.expander("Traceback"):
                    st.code(err)
            else:
                if met:
                    st.subheader("Summary")
                    summary_df = pd.DataFrame([{"metric": k, "value": round(v, 4) if isinstance(v, float) and not np.isnan(v) else v} for k, v in met.items()])
                    if "gross_total_return" in met and "cost_drag_pct" in met:
                        st.caption("Gross vs net return; cost_drag_pct = (gross - net) in %.")
                    st.dataframe(_safe_df(summary_df), use_container_width=True, hide_index=True)
                if equity is not None and not (hasattr(equity, "empty") and equity.empty):
                    st.subheader("Equity curve")
                    fig_equity = go.Figure()
                    fig_equity.add_trace(go.Scatter(x=equity.index, y=equity.values, name="Equity", mode="lines"))
                    fig_equity.update_layout(height=350, yaxis_title="Equity")
                    st.plotly_chart(fig_equity, use_container_width=True)
                if trades_df is not None and not trades_df.empty:
                    st.subheader("Trades")
                    st.dataframe(_safe_df(trades_df), use_container_width=True)
                elif trades_df is not None and trades_df.empty:
                    st.caption("No trades.")
        else:
            st.info("Use sidebar settings and click **Run backtest** to run.")

    elif page == "Walk-Forward":
        st.header("Walk-Forward Backtest")
        with st.sidebar.expander("Walk-Forward settings", expanded=True):
            wf_strategy = st.selectbox("Strategy", ["trend", "volatility_breakout"], key="wf_strategy")
            wf_freq = st.selectbox("Freq", ["5min", "15min", "1h", "1D"], index=2, key="wf_freq")
            train_days = st.number_input("Train (days)", value=30.0, min_value=1.0, max_value=365.0, step=1.0, key="wf_train")
            test_days = st.number_input("Test (days)", value=7.0, min_value=1.0, max_value=90.0, step=1.0, key="wf_test")
            step_days = st.number_input("Step (days)", value=7.0, min_value=1.0, max_value=90.0, step=1.0, key="wf_step")
            wf_expanding = st.checkbox("Expanding train", value=False, key="wf_expanding")
            wf_fee_bps = st.number_input("Fee (bps)", value=30.0, min_value=0.0, step=5.0, key="wf_fee")
            wf_slip_bps = st.number_input("Slippage (bps)", value=10.0, min_value=0.0, step=5.0, key="wf_slip")
        run_wf = st.sidebar.button("Run walk-forward", key="wf_run")
        if run_wf:
            try:
                bars_wf = load_bars(wf_freq, db_path_override=db_path_str, min_bars=int(config_min_bars() if callable(config_min_bars) else 48))
                if bars_wf.empty:
                    st.session_state["wf_result"] = (None, None, None, "No bars.")
                else:
                    bpd = bars_per_day(wf_freq)
                    train_bars = max(1, int(train_days * bpd))
                    test_bars = max(1, int(test_days * bpd))
                    step_bars = max(1, int(step_days * bpd))
                    costs = {"fee_bps": wf_fee_bps, "slippage_bps": wf_slip_bps}
                    stitched, fold_df, fold_metrics = run_walkforward_backtest(
                        bars_wf, wf_freq, wf_strategy, train_bars=train_bars, test_bars=test_bars, step_bars=step_bars, params={}, costs=costs, expanding=wf_expanding,
                    )
                    st.session_state["wf_result"] = (stitched, fold_df, fold_metrics, None)
            except Exception as e:
                import traceback
                st.session_state["wf_result"] = (None, None, None, traceback.format_exc())
        if "wf_result" in st.session_state:
            stitched, fold_df, fold_metrics, wf_err = st.session_state["wf_result"]
            if wf_err:
                st.error(wf_err)
            elif stitched is not None and not stitched.empty:
                st.subheader("Stitched equity")
                fig_wf = go.Figure()
                fig_wf.add_trace(go.Scatter(x=stitched.index, y=stitched.values, name="Equity", mode="lines"))
                fig_wf.update_layout(height=350, yaxis_title="Equity")
                st.plotly_chart(fig_wf, use_container_width=True)
                total_ret = float(stitched.iloc[-1] / stitched.iloc[0] - 1.0)
                st.metric("Stitched total return", f"{total_ret:.2%}")
                if fold_df is not None and not fold_df.empty:
                    st.subheader("Per-fold metrics")
                    st.dataframe(_safe_df(fold_df), use_container_width=True)
                    st.download_button("Download fold CSV", data=fold_df.to_csv(index=False).encode("utf-8"), file_name="walkforward_folds.csv", mime="text/csv", key="wf_dl")
            else:
                st.info("No folds (not enough data) or run again.")
        else:
            st.info("Configure sidebar and click **Run walk-forward**.")

    elif page == "Market Structure":
        st.header("Market Structure")
        freq_ms = st.selectbox("Freq (1h recommended for beta/correlation)", ["5min", "15min", "1h", "1D"], index=2, key="ms_freq")
        try:
            bars_ms = load_bars(freq_ms, db_path_override=db_path_str)
        except FileNotFoundError:
            bars_ms = pd.DataFrame()
        if bars_ms.empty:
            st.warning("No bars. Run materialize_bars.py --freq " + freq_ms)
        else:
            bars_ms = bars_ms.copy()
            bars_ms["pair_id"] = bars_ms["chain_id"].astype(str) + ":" + bars_ms["pair_address"].astype(str)
            bars_ms["label"] = bars_ms["base_symbol"].fillna("").astype(str) + "/" + bars_ms["quote_symbol"].fillna("").astype(str)
            if "log_return" not in bars_ms.columns:
                out = []
                for (c, a), g in bars_ms.groupby(["chain_id", "pair_address"]):
                    g = g.sort_values("ts_utc").copy()
                    g["log_return"] = log_returns(g["close"]).values
                    out.append(g)
                bars_ms = pd.concat(out, ignore_index=True)
            returns_df = bars_ms.pivot_table(index="ts_utc", columns="pair_id", values="log_return").dropna(how="all")
            meta = bars_ms.groupby("pair_id")["label"].last().to_dict()
            returns_df, meta = append_spot_returns_to_returns_df(returns_df, meta, db_path_str, freq_ms)
            factor_ret = get_factor_returns(returns_df, meta, db_path_str, freq_ms, factor_symbol="BTC") if not returns_df.empty else None

            if returns_df.shape[1] >= 2:
                corr = compute_correlation_matrix(returns_df)
                corr_display = corr.rename(index=meta, columns=meta)
                st.subheader("Correlation matrix (log returns)")
                fig_corr = go.Figure(data=go.Heatmap(z=corr_display.values, x=corr_display.columns, y=corr_display.index, colorscale="RdBu", zmid=0, zmin=-1, zmax=1))
                fig_corr.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig_corr, use_container_width=True)

                # Market Regime card (dispersion_z + vol_regime + beta_state)
                disp_series_ms = compute_dispersion_index(returns_df)
                disp_z_latest_ms = np.nan
                if not disp_series_ms.empty:
                    w_disp_ms = dispersion_window_for_freq(freq_ms)
                    if len(disp_series_ms) >= w_disp_ms:
                        disp_z_ms = compute_dispersion_zscore(disp_series_ms, w_disp_ms)
                        if not disp_z_ms.empty and disp_z_ms.notna().any():
                            disp_z_latest_ms = float(disp_z_ms.iloc[-1])
                vol_regime_ms = "unknown"
                beta_state_ms = "unknown"
                dex_cols_early = [c for c in returns_df.columns if not str(c).endswith("_spot")]
                if dex_cols_early and factor_ret is not None and not factor_ret.dropna().empty:
                    first_pair = dex_cols_early[0]
                    r_first = returns_df[first_pair].dropna()
                    if len(r_first) >= 48:
                        vol_short = r_first.rolling(24).std(ddof=1).iloc[-1]
                        vol_med = r_first.rolling(48).std(ddof=1).iloc[-1]
                        vol_regime_ms = classify_vol_regime(vol_short, vol_med)
                        roll_b24 = compute_rolling_beta(r_first, factor_ret, 24)
                        roll_b72 = compute_rolling_beta(r_first, factor_ret, 72)
                        b24 = float(roll_b24.dropna().iloc[-1]) if not roll_b24.empty and roll_b24.notna().any() else np.nan
                        b72 = float(roll_b72.dropna().iloc[-1]) if not roll_b72.empty and roll_b72.notna().any() else np.nan
                        beta_state_ms = classify_beta_state(b24, b72, 0.15)
                regime_label_ms = classify_market_regime(disp_z_latest_ms, vol_regime_ms, beta_state_ms)
                regime_explanation_ms = explain_regime(regime_label_ms)
                st.subheader("Market Regime")
                st.info(f"**{regime_label_ms}** — dispersion_z: {disp_z_latest_ms:.2f} | vol_regime: {vol_regime_ms} | beta_state: {beta_state_ms}. {regime_explanation_ms}")
            else:
                st.info("Need 2+ pairs for correlation matrix.")

            btc_price = load_spot_price_resampled(db_path_str, "BTC", freq_ms)
            dex_cols_for_ratio = [c for c in returns_df.columns if not str(c).endswith("_spot")]
            if not btc_price.empty and dex_cols_for_ratio:
                st.subheader("Asset/BTC ratio")
                pair_ratio_options = dex_cols_for_ratio
                default_idx = 0
                for i, c in enumerate(pair_ratio_options):
                    if "SOL" in (meta.get(c, c) or "") and "USDC" in (meta.get(c, c) or ""):
                        default_idx = i
                        break
                pair_ratio_sel = st.selectbox("Pair (vs BTC_spot)", options=pair_ratio_options, index=default_idx, format_func=lambda x: meta.get(x, x), key="pair_ratio")
                g_ratio = bars_ms[bars_ms["pair_id"] == pair_ratio_sel].sort_values("ts_utc").set_index("ts_utc")
                if not g_ratio.empty and "close" in g_ratio.columns:
                    price_series = g_ratio["close"].dropna()
                    ratio_series = compute_ratio_series(price_series, btc_price)
                    if len(ratio_series) >= 2:
                        n_24h = period_return_bars(freq_ms)["24h"]
                        ratio_return_24h = compute_lookback_return_from_price(ratio_series, n_24h) if len(ratio_series) >= n_24h else np.nan
                        ratio_cum_return = (float(ratio_series.iloc[-1]) / float(ratio_series.iloc[0])) - 1.0
                        ratio_metrics = pd.DataFrame([
                            {"metric": "ratio_return_24h", "value": round(ratio_return_24h, 4) if pd.notna(ratio_return_24h) else "—"},
                            {"metric": "ratio_cum_return", "value": round(ratio_cum_return, 4) if pd.notna(ratio_cum_return) else "—"},
                        ])
                        st.caption(f"Metrics for {meta.get(pair_ratio_sel, pair_ratio_sel)} / BTC. Ratio = asset price / BTC price; strength vs BTC.")
                        st.dataframe(_safe_df(ratio_metrics), use_container_width=True, hide_index=True)
                        fig_ratio = go.Figure()
                        fig_ratio.add_trace(go.Scatter(x=ratio_series.index, y=ratio_series.values, name="Ratio", mode="lines"))
                        fig_ratio.update_layout(title=f"Asset/BTC ratio — {meta.get(pair_ratio_sel, pair_ratio_sel)}", height=300, yaxis_title="Ratio")
                        st.plotly_chart(fig_ratio, use_container_width=True)
                    else:
                        st.info("Not enough aligned ratio points.")
                else:
                    st.info("No price series for selected pair.")
            elif not dex_cols_for_ratio:
                st.caption("No DEX pairs for ratio.")
            else:
                st.caption("BTC_spot price not available for ratio.")

            roll_window = st.number_input("Rolling correlation window (bars)", value=24, min_value=2, step=1, key="roll_win")
            if returns_df.shape[1] >= 2 and len(returns_df) >= roll_window:
                pair_sel = st.selectbox("Pair for rolling correlation", options=list(returns_df.columns), format_func=lambda x: meta.get(x, x), key="roll_pair")
                ref_col = returns_df[pair_sel]
                roll_corr = pd.DataFrame(index=returns_df.index)
                for c in returns_df.columns:
                    if c != pair_sel:
                        roll_corr[c] = ref_col.rolling(roll_window).corr(returns_df[c])
                roll_corr = roll_corr.rename(columns=meta)
                fig_roll = go.Figure()
                for col in roll_corr.columns:
                    fig_roll.add_trace(go.Scatter(x=roll_corr.index, y=roll_corr[col], name=col, mode="lines"))
                fig_roll.update_layout(title=f"Rolling correlation vs {meta.get(pair_sel, pair_sel)} (window={roll_window})", height=350, yaxis_title="Correlation")
                st.plotly_chart(fig_roll, use_container_width=True)

            st.subheader("Rolling corr / beta vs BTC_spot")
            dex_cols = [c for c in returns_df.columns if not str(c).endswith("_spot")]
            if dex_cols and factor_ret is not None and not factor_ret.dropna().empty:
                win_short, win_long = rolling_windows_for_freq(freq_ms)
                roll_win_sel = st.selectbox("Window (bars)", options=[win_short, win_long], format_func=lambda w: f"{w} bars", key="roll_btc_win")
                pair_btc_sel = st.selectbox("Pair for rolling vs BTC_spot", options=dex_cols, format_func=lambda x: meta.get(x, x), key="pair_btc")
                asset_ret = returns_df[pair_btc_sel].dropna()
                roll_corr_btc = compute_rolling_corr(asset_ret, factor_ret, roll_win_sel)
                roll_beta_btc = compute_rolling_beta(asset_ret, factor_ret, roll_win_sel)
                roll_corr_24 = compute_rolling_corr(asset_ret, factor_ret, win_short)
                roll_corr_72 = compute_rolling_corr(asset_ret, factor_ret, win_long)
                roll_beta_24 = compute_rolling_beta(asset_ret, factor_ret, win_short)
                roll_beta_72 = compute_rolling_beta(asset_ret, factor_ret, win_long)
                beta_hat_72 = float(roll_beta_72.dropna().iloc[-1]) if not roll_beta_72.empty and roll_beta_72.notna().any() else None
                beta_hat_24 = float(roll_beta_24.dropna().iloc[-1]) if not roll_beta_24.empty and roll_beta_24.notna().any() else None
                beta_hat_sel = st.radio("Beta for hedged return", options=["72", "24"], format_func=lambda x: f"beta_btc_{x} (default)" if x == "72" else f"beta_btc_{x}", key="beta_hat_radio", horizontal=True)
                beta_hat = beta_hat_72 if beta_hat_sel == "72" and beta_hat_72 is not None else (beta_hat_24 if beta_hat_24 is not None else beta_hat_72)
                corr_24 = float(roll_corr_24.dropna().iloc[-1]) if not roll_corr_24.empty and roll_corr_24.notna().any() else np.nan
                corr_72 = float(roll_corr_72.dropna().iloc[-1]) if not roll_corr_72.empty and roll_corr_72.notna().any() else np.nan
                beta_24 = float(roll_beta_24.dropna().iloc[-1]) if not roll_beta_24.empty and roll_beta_24.notna().any() else np.nan
                beta_72 = float(roll_beta_72.dropna().iloc[-1]) if not roll_beta_72.empty and roll_beta_72.notna().any() else np.nan
                beta_compress_threshold = 0.15
                beta_compression = compute_beta_compression(beta_24, beta_72)
                beta_state = classify_beta_state(beta_24, beta_72, beta_compress_threshold)
                n_24h = period_return_bars(freq_ms)["24h"]
                excess_return_24h = excess_max_drawdown = np.nan
                if beta_hat is not None and len(asset_ret) >= 2:
                    r_excess = compute_excess_log_returns(asset_ret, factor_ret, beta_hat)
                    if len(r_excess) >= 2:
                        excess_return_24h = compute_excess_lookback_return(r_excess, n_24h) if len(r_excess) >= n_24h else np.nan
                        excess_equity = np.exp(r_excess.cumsum())
                        _, excess_max_drawdown = compute_drawdown_from_equity(excess_equity)
                metrics_card = pd.DataFrame([
                    {"metric": "corr_btc_24", "value": round(corr_24, 4) if pd.notna(corr_24) else "—"},
                    {"metric": "corr_btc_72", "value": round(corr_72, 4) if pd.notna(corr_72) else "—"},
                    {"metric": "beta_btc_24", "value": round(beta_24, 4) if pd.notna(beta_24) else "—"},
                    {"metric": "beta_btc_72", "value": round(beta_72, 4) if pd.notna(beta_72) else "—"},
                    {"metric": "beta_compression", "value": round(beta_compression, 4) if pd.notna(beta_compression) else "—"},
                    {"metric": "beta_state", "value": beta_state},
                    {"metric": "excess_return_24h", "value": round(excess_return_24h, 4) if pd.notna(excess_return_24h) else "—"},
                    {"metric": "excess_max_drawdown", "value": round(excess_max_drawdown, 4) if pd.notna(excess_max_drawdown) else "—"},
                ])
                st.caption(f"Metrics for {meta.get(pair_btc_sel, pair_btc_sel)}")
                st.caption("beta_state: compressed = short-window beta below long − threshold (often pre-vol shift); expanded = above; stable = in between.")
                st.dataframe(_safe_df(metrics_card), use_container_width=True, hide_index=True)
                fig_rc = go.Figure()
                if not roll_corr_btc.empty:
                    fig_rc.add_trace(go.Scatter(x=roll_corr_btc.index, y=roll_corr_btc.values, name="Rolling corr", mode="lines"))
                fig_rc.update_layout(title=f"Rolling correlation vs BTC_spot — {meta.get(pair_btc_sel, pair_btc_sel)} (window={roll_win_sel})", height=300, yaxis_title="Correlation")
                st.plotly_chart(fig_rc, use_container_width=True)
                fig_rb = go.Figure()
                if not roll_beta_btc.empty:
                    fig_rb.add_trace(go.Scatter(x=roll_beta_btc.index, y=roll_beta_btc.values, name="Rolling beta", mode="lines"))
                fig_rb.update_layout(title=f"Rolling beta vs BTC_spot — {meta.get(pair_btc_sel, pair_btc_sel)} (window={roll_win_sel})", height=300, yaxis_title="Beta")
                st.plotly_chart(fig_rb, use_container_width=True)
                if beta_hat is not None and len(asset_ret) >= 2:
                    r_excess = compute_excess_log_returns(asset_ret, factor_ret, beta_hat)
                    if len(r_excess) >= 2:
                        excess_cum = compute_excess_cum_return(r_excess)
                        fig_ex = go.Figure()
                        fig_ex.add_trace(go.Scatter(x=excess_cum.index, y=excess_cum.values, name="Excess cum return", mode="lines"))
                        fig_ex.update_layout(title=f"BTC-hedged cumulative return — {meta.get(pair_btc_sel, pair_btc_sel)} (beta_hat={beta_hat_sel})", height=300, yaxis_title="Excess cum return")
                        st.plotly_chart(fig_ex, use_container_width=True)
            else:
                st.info("Need DEX pairs and BTC_spot (run poller with spot).")

            st.subheader("Beta vs BTC")
            rows_beta = []
            for (cid, addr), g in bars_ms.groupby(["chain_id", "pair_address"]):
                g = g.sort_values("ts_utc").set_index("ts_utc")
                r = g["log_return"].dropna()
                if len(r) < 2:
                    continue
                factor_aligned = factor_ret.reindex(r.index).dropna() if factor_ret is not None else None
                beta = compute_beta_vs_factor(r, factor_aligned) if factor_aligned is not None and not (factor_aligned.dropna().empty) else np.nan
                label = meta.get(f"{cid}:{addr}", f"{cid}/{addr}")
                rows_beta.append({"label": label, "beta_vs_btc": beta})
            if rows_beta:
                st.dataframe(_safe_df(pd.DataFrame(rows_beta)), use_container_width=True)
            else:
                st.write("No data or no BTC factor.")

            if returns_df.shape[1] >= 2:
                st.subheader("Cross-asset dispersion index")
                disp_series = compute_dispersion_index(returns_df)
                if not disp_series.empty:
                    disp_latest = float(disp_series.iloc[-1])
                    w_disp = dispersion_window_for_freq(freq_ms)
                    disp_z_series = pd.Series(dtype=float)
                    disp_z_latest = np.nan
                    if len(disp_series) >= w_disp:
                        disp_z_series = compute_dispersion_zscore(disp_series, w_disp)
                        if not disp_z_series.empty and disp_z_series.notna().any():
                            disp_z_latest = float(disp_z_series.iloc[-1])
                    disp_metrics = pd.DataFrame([
                        {"metric": "dispersion_latest", "value": round(disp_latest, 6)},
                        {"metric": "dispersion_z_latest", "value": round(disp_z_latest, 2) if not np.isnan(disp_z_latest) else "—"},
                    ])
                    st.caption("Dispersion: cross-sectional std of returns. z > +1: high dispersion (relative value); z < -1: low dispersion (macro beta).")
                    st.dataframe(_safe_df(disp_metrics), use_container_width=True, hide_index=True)
                    fig_disp = go.Figure()
                    fig_disp.add_trace(go.Scatter(x=disp_series.index, y=disp_series.values, name="Dispersion (std)", mode="lines"))
                    if not disp_z_series.empty:
                        fig_disp.add_trace(go.Scatter(x=disp_z_series.index, y=disp_z_series.values, name="Dispersion z-score", mode="lines", yaxis="y2"))
                        fig_disp.update_layout(yaxis2=dict(title="z-score", overlaying="y", side="right"))
                    fig_disp.update_layout(title="Cross-asset dispersion index (std across assets)", height=300, yaxis_title="Dispersion")
                    st.plotly_chart(fig_disp, use_container_width=True)
                else:
                    st.write("Dispersion series empty.")
            else:
                st.caption("Need 2+ assets for dispersion.")

            st.subheader("Volatility regime")
            vol_short, vol_medium = 24, 48
            rows_regime = []
            for (cid, addr), g in bars_ms.groupby(["chain_id", "pair_address"]):
                g = g.sort_values("ts_utc")
                r = g["log_return"].dropna()
                if len(r) < vol_short:
                    continue
                short_vol = r.rolling(vol_short).std(ddof=1).iloc[-1]
                medium_vol = r.rolling(min(vol_medium, len(r))).std(ddof=1).iloc[-1] if len(r) >= vol_medium else short_vol
                regime = classify_vol_regime(short_vol, medium_vol)
                label = meta.get(f"{cid}:{addr}", f"{cid}/{addr}")
                rows_regime.append({"label": label, "regime": regime})
            if rows_regime:
                st.dataframe(_safe_df(pd.DataFrame(rows_regime)), use_container_width=True)
            else:
                st.write("No data.")

    elif page == "Signals":
        st.header("Signals (research journal)")
        signal_type_filter = st.sidebar.selectbox("Signal type", ["all", "beta_compression_trigger", "dispersion_extreme", "residual_momentum"], key="sig_type")
        last_n = st.sidebar.number_input("Last N signals", value=100, min_value=1, max_value=1000, step=10, key="sig_n")
        sig_type = None if signal_type_filter == "all" else signal_type_filter
        signals_df = load_signals(db_path_str, signal_type=sig_type, last_n=int(last_n))
        if not signals_df.empty:
            st.dataframe(_safe_df(signals_df), use_container_width=True)
            st.download_button("Download signals CSV", data=signals_df.to_csv(index=False).encode("utf-8"), file_name="signals_export.csv", mime="text/csv", key="sig_dl")
        else:
            st.info("No signals in journal. Run report_daily.py to detect and log signals.")

    elif page == "Research":
        st.header("Research (cross-sectional alpha)")
        freq_res = st.sidebar.selectbox("Freq", ["5min", "15min", "1h", "1D"], index=2, key="res_freq")
        try:
            returns_df_res, meta_df_res = get_research_assets(db_path_str, freq_res, include_spot=True)
        except Exception as e:
            returns_df_res = pd.DataFrame()
            meta_df_res = pd.DataFrame()
            st.warning(f"Universe load failed: {e}")
        n_assets = returns_df_res.shape[1] if not returns_df_res.empty else 0
        if n_assets < 3:
            st.info(f"Need >= 3 assets for cross-sectional research. Current: {n_assets}. Add more DEX pairs or ensure spot series exist.")
            meta_dict_res = {}
        else:
            meta_dict_res = meta_df_res.set_index("asset_id")["label"].to_dict() if not meta_df_res.empty else {}
        tab_univ, tab_ic, tab_decay, tab_port, tab_regime = st.tabs(["Universe", "IC Summary", "IC Decay", "Portfolio", "Regime Conditioning"])
        with tab_univ:
            st.subheader("Universe")
            if not meta_df_res.empty:
                st.dataframe(_safe_df(meta_df_res), use_container_width=True)
                st.caption(f"Assets: {n_assets} | Bars: {len(returns_df_res)}")
            else:
                st.write("No universe data.")
        with tab_ic:
            st.subheader("IC Summary")
            if n_assets >= 3 and not returns_df_res.empty:
                sig_mom_res = signal_momentum_24h(returns_df_res, freq_res)
                if not sig_mom_res.empty:
                    fwd1 = compute_forward_returns(returns_df_res, 1)
                    ic_ts_res = information_coefficient(sig_mom_res, fwd1, method="spearman")
                    s_res = ic_summary(ic_ts_res)
                    st.dataframe(_safe_df(pd.DataFrame([s_res])), use_container_width=True, hide_index=True)
                    if not ic_ts_res.empty and ic_ts_res.notna().any():
                        fig_ic = go.Figure()
                        fig_ic.add_trace(go.Scatter(x=ic_ts_res.dropna().index, y=ic_ts_res.dropna().values, name="IC", mode="lines"))
                        fig_ic.update_layout(title="IC over time (momentum_24h vs fwd 1-bar)", height=300)
                        st.plotly_chart(fig_ic, use_container_width=True)
                else:
                    st.write("Signal empty.")
            else:
                st.write("Need >= 3 assets.")
        with tab_decay:
            st.subheader("IC Decay")
            if n_assets >= 3 and not returns_df_res.empty:
                sig_mom_res = signal_momentum_24h(returns_df_res, freq_res)
                horizons_res = [1, 2, 3, 6, 12, 24]
                decay_df_res = ic_decay(sig_mom_res, returns_df_res, horizons_res, method="spearman")
                if not decay_df_res.empty:
                    st.dataframe(_safe_df(decay_df_res.round(4)), use_container_width=True)
                    fig_dec = go.Figure()
                    fig_dec.add_trace(go.Scatter(x=decay_df_res["horizon_bars"], y=decay_df_res["mean_ic"], mode="lines+markers", name="Mean IC"))
                    fig_dec.update_layout(title="IC decay (momentum_24h)", xaxis_title="Horizon (bars)", height=300)
                    st.plotly_chart(fig_dec, use_container_width=True)
                else:
                    st.write("No decay data.")
            else:
                st.write("Need >= 3 assets.")
        with tab_port:
            st.subheader("Portfolio (L/S research)")
            if n_assets >= 3 and not returns_df_res.empty:
                top_k = st.number_input("Top K", value=3, min_value=1, max_value=10, step=1, key="res_topk")
                bot_k = st.number_input("Bottom K", value=3, min_value=1, max_value=10, step=1, key="res_botk")
                sig_mom_res = signal_momentum_24h(returns_df_res, freq_res)
                ranks_res = rank_signal_df(sig_mom_res)
                weights_res = long_short_from_ranks(ranks_res, int(top_k), int(bot_k), gross_leverage=1.0)
                port_ret_res = portfolio_returns_from_weights(weights_res, returns_df_res).dropna()
                turnover_res = turnover_from_weights(weights_res)
                fee_bps = 30.0
                slip_bps = 10.0
                port_net_res = apply_costs_to_portfolio(port_ret_res, turnover_res.reindex(port_ret_res.index).fillna(0), fee_bps, slip_bps)
                if len(port_net_res) >= 2:
                    summ_res = significance_summary(port_net_res, freq_res)
                    eq_res = (1 + port_net_res).cumprod()
                    dd_res = eq_res.cummax() - eq_res
                    st.metric("Sharpe (net)", f"{summ_res['sharpe_annual']:.3f}")
                    st.metric("Max DD", f"{dd_res.max():.3f}")
                    st.metric("Avg turnover", f"{turnover_res.mean():.3f}")
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(x=eq_res.index, y=eq_res.values, name="Equity", mode="lines"))
                    fig_eq.update_layout(title="L/S momentum equity", height=300)
                    st.plotly_chart(fig_eq, use_container_width=True)
                else:
                    st.write("Insufficient return data.")
            else:
                st.write("Need >= 3 assets.")
        with tab_regime:
            st.subheader("Regime conditioning")
            if n_assets >= 3 and not returns_df_res.empty:
                disp_ser = compute_dispersion_series(returns_df_res)
                disp_z_ser = dispersion_zscore_series(disp_ser, 24) if len(disp_ser) >= 24 else pd.Series(dtype=float)
                sig_mom_res = signal_momentum_24h(returns_df_res, freq_res)
                ranks_res = rank_signal_df(sig_mom_res)
                weights_res = long_short_from_ranks(ranks_res, 3, 3, gross_leverage=1.0)
                port_ret_res = portfolio_returns_from_weights(weights_res, returns_df_res).dropna()
                common_r = port_ret_res.index.intersection(disp_z_ser.index)
                if len(common_r) >= 10:
                    port_r = port_ret_res.loc[common_r]
                    z_r = disp_z_ser.reindex(common_r).ffill().bfill()
                    high = (z_r > 1).fillna(False)
                    low = (z_r < -1).fillna(False)
                    mid = (~high & ~low).fillna(False)
                    rows_r = []
                    for label, mask in [("z > +1", high), ("z in [-1,+1]", mid), ("z < -1", low)]:
                        r = port_r.loc[mask]
                        if len(r) >= 2 and r.std() and r.std() != 0:
                            sh = float(r.mean() / r.std() * np.sqrt(bars_per_year(freq_res)))
                            rows_r.append({"regime": label, "n_bars": len(r), "mean_ret": r.mean(), "sharpe_approx": sh})
                    if rows_r:
                        st.dataframe(_safe_df(pd.DataFrame(rows_r).round(4)), use_container_width=True)
                    else:
                        st.write("No regime splits.")
                else:
                    st.write("Insufficient overlap for regime split.")
            else:
                st.write("Need >= 3 assets.")

    elif page == "Institutional Research":
        st.header("Institutional Research (M4)")
        try:
            returns_inst, meta_inst = get_research_assets(db_path_str, "1h", include_spot=True)
        except Exception as e:
            returns_inst = pd.DataFrame()
            meta_inst = pd.DataFrame()
            st.warning(f"Universe load failed: {e}")
        n_inst = returns_inst.shape[1] if not returns_inst.empty else 0
        meta_dict_inst = meta_inst.set_index("asset_id")["label"].to_dict() if not meta_inst.empty else {}
        factor_inst = get_factor_returns(returns_inst, meta_dict_inst, db_path_str, "1h") if meta_dict_inst else None

        tab_hygiene, tab_adv_port, tab_overfit, tab_cond, tab_exp = st.tabs(
            ["Signal Hygiene", "Advanced Portfolio", "Overfitting Defenses", "Conditional Performance", "Experiments"]
        )
        with tab_hygiene:
            st.subheader("Signal Hygiene (cross-corr before/after)")
            if n_inst < 2:
                st.info("Need at least 2 assets for cross-sectional hygiene. Add more DEX pairs.")
            else:
                try:
                    from crypto_analyzer.signals_xs import clean_momentum, value_vs_beta, orthogonalize_signals
                    from crypto_analyzer.alpha_research import signal_momentum_24h
                    sig_mom_i = signal_momentum_24h(returns_inst, "1h")
                    sig_clean_i = clean_momentum(returns_inst, "1h", factor_inst) if not returns_inst.empty else pd.DataFrame()
                    sig_value_i = value_vs_beta(returns_inst, "1h", factor_inst)
                    signals_dict_i = {}
                    if not sig_mom_i.empty:
                        signals_dict_i["momentum_24h"] = sig_mom_i
                    if not sig_clean_i.empty:
                        signals_dict_i["clean_momentum"] = sig_clean_i
                    if sig_value_i is not None and not sig_value_i.empty:
                        signals_dict_i["value_vs_beta"] = sig_value_i
                    if len(signals_dict_i) >= 2:
                        orth_i, report_i = orthogonalize_signals(signals_dict_i)
                        if report_i:
                            st.dataframe(_safe_df(pd.DataFrame([report_i]).T.round(4)), use_container_width=True)
                            st.caption("Avg absolute cross-correlation before/after orthogonalization.")
                        else:
                            st.write("Orthogonalization report empty.")
                    else:
                        st.write("Need at least 2 signals for orthogonalization.")
                except Exception as e:
                    st.error(str(e))
        with tab_adv_port:
            st.subheader("Advanced Portfolio (constraints, diagnostics)")
            if n_inst < 2:
                st.info("Need at least 2 assets for advanced portfolio.")
            else:
                try:
                    from crypto_analyzer.signals_xs import build_exposure_panel
                    from crypto_analyzer.alpha_research import signal_momentum_24h, rank_signal_df
                    from crypto_analyzer.portfolio_advanced import optimize_long_short_portfolio
                    from crypto_analyzer.risk_model import estimate_covariance
                    sig_mom_i = signal_momentum_24h(returns_inst, "1h")
                    if sig_mom_i.empty:
                        st.write("No signal.")
                    else:
                        ranks_i = rank_signal_df(sig_mom_i)
                        last_t = ranks_i.index[-1] if len(ranks_i) else None
                        if last_t is None:
                            st.write("No timestamps.")
                        else:
                            er_i = ranks_i.loc[last_t].astype(float)
                            cov_i = estimate_covariance(returns_inst.tail(72) if len(returns_inst) >= 72 else returns_inst, method="ewma", halflife=24.0)
                            constraints_i = {"dollar_neutral": True, "target_gross_leverage": 1.0, "max_weight_per_asset": 0.25}
                            if factor_inst is not None:
                                exp_i = build_exposure_panel(returns_inst, meta_inst, factor_returns=factor_inst, freq="1h")
                                if "beta_btc_72" in exp_i and not exp_i["beta_btc_72"].empty:
                                    b_ser = exp_i["beta_btc_72"].loc[last_t] if last_t in exp_i["beta_btc_72"].index else exp_i["beta_btc_72"].iloc[-1]
                                    constraints_i["betas"] = b_ser
                            w_i, diag_i = optimize_long_short_portfolio(er_i, cov_i, constraints_i)
                            st.caption("Diagnostics")
                            st.json({k: v for k, v in diag_i.items() if k not in ("top_long", "top_short")})
                            if not w_i.empty:
                                w_df = pd.DataFrame({"weight": w_i}).round(4)
                                st.dataframe(_safe_df(w_df), use_container_width=True)
                except Exception as e:
                    st.error(str(e))
        with tab_overfit:
            st.subheader("Overfitting Defenses")
            if n_inst < 2:
                st.info("Need at least 2 assets.")
            else:
                try:
                    from crypto_analyzer.alpha_research import signal_momentum_24h, rank_signal_df
                    from crypto_analyzer.portfolio import long_short_from_ranks, portfolio_returns_from_weights, turnover_from_weights, apply_costs_to_portfolio
                    from crypto_analyzer.multiple_testing import deflated_sharpe_ratio, reality_check_warning, pbo_proxy_walkforward
                    sig_mom_i = signal_momentum_24h(returns_inst, "1h")
                    if sig_mom_i.empty:
                        st.write("No signal.")
                    else:
                        ranks_i = rank_signal_df(sig_mom_i)
                        weights_i = long_short_from_ranks(ranks_i, 3, 3, gross_leverage=1.0)
                        port_ret_i = portfolio_returns_from_weights(weights_i, returns_inst).dropna()
                        turnover_i = turnover_from_weights(weights_i)
                        port_net_i = apply_costs_to_portfolio(port_ret_i, turnover_i.reindex(port_ret_i.index).fillna(0), 30, 10)
                        if len(port_net_i) >= 10:
                            dsr = deflated_sharpe_ratio(port_net_i, "1h", 50, skew_kurtosis_optional=True)
                            st.dataframe(_safe_df(pd.DataFrame([dsr]).T), use_container_width=True)
                            st.caption("Deflated Sharpe (n_trials=50). Use for research screening only.")
                            st.info(reality_check_warning(3, 1))
                            wf_df = pd.DataFrame([{"train_sharpe": np.nan, "test_sharpe": float(port_net_i.mean() / port_net_i.std()) if port_net_i.std() and port_net_i.std() > 0 else np.nan}])
                            pbo = pbo_proxy_walkforward(wf_df)
                            st.write("PBO proxy:", pbo.get("pbo_proxy", np.nan), "—", pbo.get("explanation", ""))
                        else:
                            st.write("Insufficient pnl for deflated Sharpe.")
                except Exception as e:
                    st.error(str(e))
        with tab_cond:
            st.subheader("Conditional Performance (regime)")
            if n_inst < 2:
                st.info("Need at least 2 assets.")
            else:
                try:
                    from crypto_analyzer.evaluation import conditional_metrics
                    from crypto_analyzer.alpha_research import signal_momentum_24h, rank_signal_df, compute_dispersion_series, dispersion_zscore_series
                    from crypto_analyzer.portfolio import long_short_from_ranks, portfolio_returns_from_weights, turnover_from_weights, apply_costs_to_portfolio
                    disp_ser = compute_dispersion_series(returns_inst)
                    disp_z_ser = dispersion_zscore_series(disp_ser, 24) if len(disp_ser) >= 24 else pd.Series(dtype=float)
                    regime_ser = disp_z_ser.apply(lambda z: "high_disp" if z > 1 else ("low_disp" if z < -1 else "mid")) if not disp_z_ser.empty else pd.Series(dtype=str)
                    sig_mom_i = signal_momentum_24h(returns_inst, "1h")
                    if sig_mom_i.empty or regime_ser.empty:
                        st.write("No signal or regime.")
                    else:
                        ranks_i = rank_signal_df(sig_mom_i)
                        weights_i = long_short_from_ranks(ranks_i, 3, 3, gross_leverage=1.0)
                        port_ret_i = portfolio_returns_from_weights(weights_i, returns_inst).dropna()
                        turnover_i = turnover_from_weights(weights_i)
                        port_net_i = apply_costs_to_portfolio(port_ret_i, turnover_i.reindex(port_ret_i.index).fillna(0), 30, 10)
                        cm = conditional_metrics(port_net_i, regime_ser)
                        if not cm.empty:
                            st.dataframe(_safe_df(cm.round(4)), use_container_width=True)
                        else:
                            st.write("No regime breakdown.")
                except Exception as e:
                    st.error(str(e))
        with tab_exp:
            st.subheader("Experiments (past runs)")
            try:
                from crypto_analyzer.experiments import load_experiments
                exp_dir = Path("reports/experiments")
                df_exp = load_experiments(str(exp_dir))
                if df_exp.empty:
                    st.info("No experiments logged. Run research_report_v2.py to log.")
                else:
                    st.dataframe(_safe_df(df_exp.tail(50)), use_container_width=True)
                    sel_run = st.selectbox("View run", options=df_exp["run_name"].astype(str).tolist() if "run_name" in df_exp.columns else [], key="exp_sel")
                    if sel_run:
                        st.json(df_exp[df_exp["run_name"].astype(str) == str(sel_run)].iloc[0].to_dict())
            except Exception as e:
                st.error(str(e))

if __name__ == "__main__":
    main()
