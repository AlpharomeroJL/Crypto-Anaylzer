#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB_PATH_DEFAULT = "dex_data.sqlite"
SOL_MONITOR_TABLE = "sol_monitor_snapshots"
SPOT_TABLE = "spot_price_snapshots"


# -----------------------------
# Helpers / Math
# -----------------------------
def sharpe_ratio(r: pd.Series, periods_per_year: float) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    s = r.std(ddof=1)
    if s == 0 or np.isnan(s):
        return float("nan")
    return float((r.mean() / s) * np.sqrt(periods_per_year))


def sortino_ratio(r: pd.Series, periods_per_year: float) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    downside = r.clip(upper=0)
    dd = np.sqrt((downside**2).mean())
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float((r.mean() / dd) * np.sqrt(periods_per_year))


def downside_deviation(r: pd.Series, periods_per_year: float) -> float:
    """Downside deviation (annualized) using only negative returns."""
    r = r.dropna()
    if r.empty:
        return float("nan")
    downside = r.clip(upper=0)
    dd = np.sqrt((downside**2).mean())
    return float(dd * np.sqrt(periods_per_year))


def rolling_beta(asset_r: pd.Series, bench_r: pd.Series, window: int) -> pd.Series:
    """Rolling beta = Cov(asset, bench) / Var(bench)."""
    df = pd.concat([asset_r, bench_r], axis=1).dropna()
    if df.empty:
        return pd.Series(dtype=float)

    a = df.iloc[:, 0]
    b = df.iloc[:, 1]
    cov = a.rolling(window).cov(b)
    var = b.rolling(window).var(ddof=1)
    beta = cov / var
    return beta


def annualization_factor(freq: str) -> float:
    """
    freq options we’ll use:
      - "10s", "30s"
      - "1min", "5min", "15min"
      - "1H"
      - "1D"
    """
    if freq.endswith("s"):
        seconds = int(freq[:-1])
        return (365 * 24 * 60 * 60) / seconds
    if freq.endswith("min"):
        minutes = int(freq[:-3])
        return (365 * 24 * 60) / minutes
    if freq.upper() == "1H":
        return 365 * 24
    if freq.upper() == "1D":
        return 365
    # fallback: assume minute
    return 365 * 24 * 60


def to_dt_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def load_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return [r[0] for r in rows]


def load_spot_prices(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        f"""
        SELECT ts_utc, symbol, spot_price_usd
        FROM {SPOT_TABLE}
        ORDER BY ts_utc ASC
        """,
        conn,
    )


def load_sol_monitor(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        f"""
        SELECT ts_utc, spot_price_usd, liquidity_usd, vol_h24,
               txns_h24_buys, txns_h24_sells
        FROM {SOL_MONITOR_TABLE}
        ORDER BY ts_utc ASC
        """,
        conn,
    )


def resample_prices_wide(spot_df: pd.DataFrame, freq: str) -> pd.DataFrame:
    spot_df = spot_df.copy()
    spot_df["ts_utc"] = to_dt_utc(spot_df["ts_utc"])
    spot_df = spot_df.dropna(subset=["ts_utc", "symbol", "spot_price_usd"])
    spot_df["spot_price_usd"] = pd.to_numeric(spot_df["spot_price_usd"], errors="coerce")
    spot_df = spot_df.dropna(subset=["spot_price_usd"])

    # per-symbol series
    out: Dict[str, pd.Series] = {}
    for sym in sorted(spot_df["symbol"].unique().tolist()):
        sub = spot_df[spot_df["symbol"] == sym].set_index("ts_utc").sort_index()
        s = sub["spot_price_usd"].resample(freq).last().dropna()
        if len(s) >= 2:
            out[sym] = s

    if not out:
        return pd.DataFrame()

    wide = pd.DataFrame(out).dropna(how="any")  # inner-join alignment
    return wide


def resample_liquidity(sol_df: pd.DataFrame, freq: str) -> pd.Series:
    sol_df = sol_df.copy()
    sol_df["ts_utc"] = to_dt_utc(sol_df["ts_utc"])
    sol_df = sol_df.dropna(subset=["ts_utc"])
    sol_df = sol_df.set_index("ts_utc").sort_index()
    liq = pd.to_numeric(sol_df["liquidity_usd"], errors="coerce").resample(freq).last()
    return liq


def add_regime_from_percentile(vol: pd.Series) -> pd.DataFrame:
    """
    Regime by percentile of rolling vol:
      Low < 33%
      Mid 33–66%
      High > 66%
    """
    v = vol.dropna()
    if v.empty:
        return pd.DataFrame(index=vol.index)

    pct = v.rank(pct=True)
    # align back to full index
    pct_full = pd.Series(index=vol.index, dtype=float)
    pct_full.loc[pct.index] = pct.values

    regime = pd.Series(index=vol.index, dtype=object)
    regime[pct_full < 0.33] = "Low"
    regime[(pct_full >= 0.33) & (pct_full <= 0.66)] = "Mid"
    regime[pct_full > 0.66] = "High"

    return pd.DataFrame({"vol_percentile": pct_full, "regime": regime})


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Crypto Analyzer Dashboard", layout="wide")

st.title("Crypto Analyzer — Multi-Asset Quant Dashboard")

with st.sidebar:
    st.header("Data Source")
    db_path = st.text_input("SQLite DB path", DB_PATH_DEFAULT)

    st.header("Chart Theme")
    template = st.selectbox(
        "Plotly template",
        [
            "plotly",
            "plotly_white",
            "plotly_dark",
            "ggplot2",
            "seaborn",
            "simple_white",
            "presentation",
        ],
        index=2,  # dark default
    )
    colorway = st.selectbox(
        "Color set",
        ["Plotly default", "Vivid", "Pastel", "Bold"],
        index=1,
    )

    st.header("Analysis Controls")
    freq = st.selectbox("Resample frequency (analysis bars)", ["10s", "30s", "1min", "5min", "15min", "1H", "1D"], index=2)
    roll_window = st.slider("Rolling window (bars)", min_value=5, max_value=300, value=30, step=1)
    min_ratio_points = st.slider("Min points to show ratios", min_value=10, max_value=2000, value=300, step=10)

    st.header("Beta / Regimes")
    beta_window = st.slider("Rolling beta window (bars)", min_value=10, max_value=500, value=60, step=5)
    regime_window = st.slider("Regime vol window (bars)", min_value=10, max_value=500, value=60, step=5)

    st.caption("Tip: For stable metrics, use 1min bars and run the poller for hours+.")


def apply_colorway(fig: go.Figure, colorway_choice: str) -> go.Figure:
    palettes = {
        "Plotly default": None,
        "Vivid": ["#00E5FF", "#FF2D55", "#34C759", "#AF52DE", "#FF9F0A", "#5AC8FA"],
        "Pastel": ["#A7C7E7", "#FADADD", "#C1E1C1", "#E6E6FA", "#FFE5B4", "#BEE3DB"],
        "Bold": ["#00C2FF", "#FF3B30", "#30D158", "#BF5AF2", "#FFD60A", "#64D2FF"],
    }
    palette = palettes.get(colorway_choice)
    if palette:
        fig.update_layout(colorway=palette)
    return fig


def make_layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        template=template,
        title=title,
        margin=dict(l=20, r=20, t=50, b=20),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return apply_colorway(fig, colorway)


# -----------------------------
# Load data
# -----------------------------
try:
    conn = sqlite3.connect(db_path)
    tables = load_tables(conn)

    if SOL_MONITOR_TABLE not in tables:
        st.error(f"Missing table: {SOL_MONITOR_TABLE}. Your poller should create it.")
        st.stop()

    sol_df = load_sol_monitor(conn)

    spot_df = None
    if SPOT_TABLE in tables:
        spot_df = load_spot_prices(conn)

finally:
    try:
        conn.close()
    except Exception:
        pass

if spot_df is None or spot_df.empty:
    st.warning("spot_price_snapshots is missing/empty — showing SOL-only from sol_monitor_snapshots.")
    # Build a single-symbol wide frame from sol_df
    sol_df2 = sol_df.copy()
    sol_df2["ts_utc"] = to_dt_utc(sol_df2["ts_utc"])
    sol_df2 = sol_df2.dropna(subset=["ts_utc"])
    sol_df2 = sol_df2.set_index("ts_utc").sort_index()
    prices_wide = pd.DataFrame({"SOL": pd.to_numeric(sol_df2["spot_price_usd"], errors="coerce")}).resample(freq).last().dropna()
else:
    prices_wide = resample_prices_wide(spot_df, freq)

liq = resample_liquidity(sol_df, freq)
periods_per_year = annualization_factor(freq)

if prices_wide.empty or len(prices_wide) < 3:
    st.error("Not enough aligned price data yet. Let the poller run longer.")
    st.stop()

symbols = list(prices_wide.columns)
st.caption(f"Symbols aligned: {symbols} | Bars: {len(prices_wide)} | Annualization factor: {periods_per_year:.1f}")

# Returns + rolling stats
rets = prices_wide.pct_change()
cum = (1.0 + rets.fillna(0)).cumprod() - 1.0
roll_vol = rets.rolling(roll_window).std(ddof=1) * np.sqrt(periods_per_year)

# Downside deviation per asset (annualized) — rolling
downside = rets.clip(upper=0)
roll_down_dev = downside.rolling(roll_window).apply(lambda x: np.sqrt((x * x).mean()), raw=True) * np.sqrt(periods_per_year)

# Rolling Sharpe (time-varying)
roll_sharpe = (rets.rolling(roll_window).mean() / rets.rolling(roll_window).std(ddof=1)) * np.sqrt(periods_per_year)

# Beta (SOL vs BTC) — rolling + static
beta_series = pd.Series(dtype=float)
beta_static = float("nan")
if "SOL" in symbols and "BTC" in symbols:
    beta_series = rolling_beta(rets["SOL"], rets["BTC"], beta_window)
    df_beta = pd.concat([rets["SOL"], rets["BTC"]], axis=1).dropna()
    if len(df_beta) >= 10:
        cov = df_beta.iloc[:, 0].cov(df_beta.iloc[:, 1])
        var = df_beta.iloc[:, 1].var(ddof=1)
        beta_static = float(cov / var) if var and not np.isnan(var) else float("nan")

# Volatility regime detection (SOL) based on rolling vol percentile
sol_vol_for_regime = rets["SOL"].rolling(regime_window).std(ddof=1) * np.sqrt(periods_per_year) if "SOL" in symbols else None
regime_df = add_regime_from_percentile(sol_vol_for_regime) if sol_vol_for_regime is not None else pd.DataFrame()


# -----------------------------
# Top KPIs
# -----------------------------
kpi_cols = st.columns(5)
kpi_cols[0].metric("Bars", f"{len(prices_wide)}")
kpi_cols[1].metric("Resample", freq)
kpi_cols[2].metric("Roll window", f"{roll_window} bars")
if not np.isnan(beta_static):
    kpi_cols[3].metric("β(SOL vs BTC)", f"{beta_static:.2f}")
else:
    kpi_cols[3].metric("β(SOL vs BTC)", "n/a")
kpi_cols[4].metric("Dex liquidity latest", f"{liq.dropna().iloc[-1]:,.0f}" if liq.dropna().shape[0] else "n/a")


# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Prices & Returns", "Risk & Ratios", "Beta", "Vol Regimes", "Dex Liquidity vs Vol"]
)

with tab1:
    st.subheader("Multi-asset normalized price + cumulative return")

    norm = (prices_wide / prices_wide.iloc[0]) * 100.0

    fig = px.line(norm, x=norm.index, y=norm.columns)
    fig = make_layout(fig, "Normalized price (start = 100)")
    st.plotly_chart(fig, use_container_width=True)

    fig = px.line(cum, x=cum.index, y=cum.columns)
    fig = make_layout(fig, "Cumulative return")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Return distributions")
    pick = st.selectbox("Histogram asset", symbols, index=0)
    r = rets[pick].dropna()
    fig = px.histogram(r, nbins=60, marginal="rug")
    fig = make_layout(fig, f"{pick} return histogram ({freq} bars)")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Downside deviation, rolling volatility, rolling Sharpe")

    # Rolling vol
    fig = px.line(roll_vol, x=roll_vol.index, y=roll_vol.columns)
    fig = make_layout(fig, f"Rolling volatility (annualized, window={roll_window} bars)")
    st.plotly_chart(fig, use_container_width=True)

    # Downside deviation
    fig = px.line(roll_down_dev, x=roll_down_dev.index, y=roll_down_dev.columns)
    fig = make_layout(fig, f"Downside deviation (annualized, window={roll_window} bars)")
    st.plotly_chart(fig, use_container_width=True)

    # Rolling Sharpe
    fig = px.line(roll_sharpe, x=roll_sharpe.index, y=roll_sharpe.columns)
    fig = make_layout(fig, f"Rolling Sharpe (rf=0, window={roll_window} bars)")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Current summary (only when enough points)")
    if len(prices_wide) >= min_ratio_points:
        rows = []
        for sym in symbols:
            rr = rets[sym]
            rows.append(
                {
                    "symbol": sym,
                    "sharpe": sharpe_ratio(rr, periods_per_year),
                    "sortino": sortino_ratio(rr, periods_per_year),
                    "downside_dev": downside_deviation(rr, periods_per_year),
                    "vol_ann": float(rr.std(ddof=1) * np.sqrt(periods_per_year)),
                }
            )
        st.dataframe(pd.DataFrame(rows).set_index("symbol").round(4), use_container_width=True)
    else:
        st.info(f"Need {min_ratio_points}+ aligned bars to show stable ratios (have {len(prices_wide)}).")

with tab3:
    st.subheader("Beta of SOL vs BTC")

    if "SOL" not in symbols or "BTC" not in symbols:
        st.warning("Need SOL and BTC in the aligned symbol set to compute beta.")
    else:
        st.caption(f"Static beta: {beta_static:.3f} (computed from aligned {freq} returns)")

        fig = px.line(beta_series, x=beta_series.index, y=beta_series.values)
        fig = make_layout(fig, f"Rolling beta: SOL vs BTC (window={beta_window} bars)")
        fig.update_traces(name="beta", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Volatility regime detection (SOL)")

    if "SOL" not in symbols:
        st.warning("SOL not present in aligned symbol set.")
    else:
        sol_vol = sol_vol_for_regime
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sol_vol.index, y=sol_vol.values, mode="lines", name="SOL vol (ann.)"))

        # Shade regimes if available
        if not regime_df.empty and regime_df["regime"].notna().any():
            # Create background bands by regime chunks
            reg = regime_df["regime"].copy()
            # Fill forward to avoid gaps after window warmup
            reg = reg.ffill()

            # Build segments
            current = None
            start = None
            for t, v in reg.items():
                if pd.isna(v):
                    continue
                if current is None:
                    current, start = v, t
                    continue
                if v != current:
                    fig.add_vrect(
                        x0=start,
                        x1=t,
                        fillcolor={"Low": "rgba(0,200,255,0.12)", "Mid": "rgba(255,200,0,0.12)", "High": "rgba(255,0,100,0.12)"}[current],
                        line_width=0,
                        layer="below",
                    )
                    current, start = v, t
            # close last segment
            if current is not None and start is not None:
                fig.add_vrect(
                    x0=start,
                    x1=reg.index[-1],
                    fillcolor={"Low": "rgba(0,200,255,0.12)", "Mid": "rgba(255,200,0,0.12)", "High": "rgba(255,0,100,0.12)"}[current],
                    line_width=0,
                    layer="below",
                )

        fig = make_layout(fig, f"SOL volatility regimes (vol window={regime_window} bars, shaded by percentile)")
        st.plotly_chart(fig, use_container_width=True)

        # Percentile chart
        if not regime_df.empty:
            fig = px.line(regime_df["vol_percentile"], x=regime_df.index, y="vol_percentile")
            fig = make_layout(fig, "SOL volatility percentile (0..1)")
            st.plotly_chart(fig, use_container_width=True)

with tab5:
    st.subheader("Liquidity vs volatility scatter (SOL)")

    if "SOL" not in symbols:
        st.warning("SOL not present in aligned symbol set.")
    else:
        # Build scatter dataset: align liquidity with SOL rolling vol
        sol_vol = rets["SOL"].rolling(roll_window).std(ddof=1) * np.sqrt(periods_per_year)
        scatter_df = pd.DataFrame(
            {
                "liq_usd": liq,
                "sol_vol_ann": sol_vol,
                "sol_return": rets["SOL"],
            }
        ).dropna()

        # Add regime label if available
        if not regime_df.empty and "regime" in regime_df.columns:
            scatter_df = scatter_df.join(regime_df[["regime"]], how="left")
        else:
            scatter_df["regime"] = "n/a"

        fig = px.scatter(
            scatter_df,
            x="liq_usd",
            y="sol_vol_ann",
            color="regime",
            hover_data=["sol_return"],
            opacity=0.8,
        )
        fig.update_xaxes(title="Dex liquidity (USD)")
        fig.update_yaxes(title="SOL rolling volatility (annualized)")
        fig = make_layout(fig, "Dex liquidity vs SOL volatility (colored by regime)")
        st.plotly_chart(fig, use_container_width=True)

        st.caption("Tip: let the poller run longer so you see meaningful structure in scatter + regimes.")
