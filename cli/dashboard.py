#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

try:
    from st_keyup import st_keyup
except ImportError:

    def st_keyup(default: str, *, key: str = "", label_visibility: str = "collapsed"):
        return default  # keyboard shortcuts disabled when st-keyup not installed


# Same path the poller uses when NSSM AppDirectory is the project folder
DB_PATH_DEFAULT = str(Path(__file__).resolve().parent.parent / "dex_data.sqlite")
SOL_MONITOR_TABLE = "sol_monitor_snapshots"
SPOT_TABLE = "spot_price_snapshots"

# All displayed timestamps in Central Time (CST/CDT)
DISPLAY_TZ = "America/Chicago"


# -----------------------------
# Quant helpers
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
    r = r.dropna()
    if r.empty:
        return float("nan")
    downside = r.clip(upper=0)
    dd = np.sqrt((downside**2).mean())
    return float(dd * np.sqrt(periods_per_year))


def rolling_beta(asset_r: pd.Series, bench_r: pd.Series, window: int) -> pd.Series:
    df = pd.concat([asset_r, bench_r], axis=1).dropna()
    if df.empty:
        return pd.Series(dtype=float)
    a = df.iloc[:, 0]
    b = df.iloc[:, 1]
    cov = a.rolling(window).cov(b)
    var = b.rolling(window).var(ddof=1)
    return cov / var


def annualization_factor(freq: str) -> float:
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
    return 365 * 24 * 60


def to_dt_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def to_display_tz(dt_index_or_ts):
    """Convert UTC datetime index or timestamp to display timezone (CST)."""
    if hasattr(dt_index_or_ts, "tz_convert"):
        if dt_index_or_ts.tz is None:
            return dt_index_or_ts.tz_localize("UTC", ambiguous="infer").tz_convert(DISPLAY_TZ)
        return dt_index_or_ts.tz_convert(DISPLAY_TZ)
    ts = pd.Timestamp(dt_index_or_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(DISPLAY_TZ)


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

    out: Dict[str, pd.Series] = {}
    for sym in sorted(spot_df["symbol"].unique().tolist()):
        sub = spot_df[spot_df["symbol"] == sym].set_index("ts_utc").sort_index()
        s = sub["spot_price_usd"].resample(freq).last().dropna()
        if len(s) >= 2:
            out[sym] = s

    if not out:
        return pd.DataFrame()

    return pd.DataFrame(out).dropna(how="any")  # inner-join alignment


def resample_liquidity(sol_df: pd.DataFrame, freq: str) -> pd.Series:
    sol_df = sol_df.copy()
    sol_df["ts_utc"] = to_dt_utc(sol_df["ts_utc"])
    sol_df = sol_df.dropna(subset=["ts_utc"]).set_index("ts_utc").sort_index()
    return pd.to_numeric(sol_df["liquidity_usd"], errors="coerce").resample(freq).last()


def add_regime_from_percentile(vol: pd.Series) -> pd.DataFrame:
    v = vol.dropna()
    if v.empty:
        return pd.DataFrame(index=vol.index)
    pct = v.rank(pct=True)
    pct_full = pd.Series(index=vol.index, dtype=float)
    pct_full.loc[pct.index] = pct.values

    regime = pd.Series(index=vol.index, dtype=object)
    regime[pct_full < 0.33] = "Low"
    regime[(pct_full >= 0.33) & (pct_full <= 0.66)] = "Mid"
    regime[pct_full > 0.66] = "High"
    return pd.DataFrame({"vol_percentile": pct_full, "regime": regime})


# -----------------------------
# Bloomberg-style UI
# -----------------------------
st.set_page_config(page_title="Crypto Analyzer", layout="wide")

# Session defaults
if "page" not in st.session_state:
    st.session_state.page = "PRICES"
if "mode" not in st.session_state:
    st.session_state.mode = "Bloomberg Dark"
if "accent" not in st.session_state:
    st.session_state.accent = "Lime"
# Sync theme from Settings popover (keyed selectboxes) so theme updates on same run
if "settings_theme" in st.session_state:
    st.session_state.mode = st.session_state.settings_theme
if "settings_accent" in st.session_state:
    st.session_state.accent = st.session_state.settings_accent

PAGES = ["PRICES", "RISK", "BETA", "REGIMES", "DEX ↔ VOL"]
ACCENTS = ["Lime", "Cyan", "Magenta", "Amber", "Blue"]


# Sidebar controls
with st.sidebar:
    st.markdown("## Terminal")

    db_path = st.text_input("SQLite DB path", DB_PATH_DEFAULT)
    # Show which file we're actually reading and when it was last written (so reset is visible)
    if db_path and os.path.isfile(db_path):
        mtime = os.path.getmtime(db_path)
        mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        st.caption(f"DB last written: **{mtime_str}**")
    else:
        st.caption("DB file not found. Run poller or check path.")

    st.caption(
        "To refresh after new data or a reset: reload the page (F5). Historical data is never cleared from the dashboard."
    )

    st.markdown("## Real-time")
    auto_refresh = st.toggle("Auto-refresh", value=True)
    refresh_s = st.slider("Refresh interval (seconds)", 2, 60, 5, 1)

    st.markdown("## Analysis")
    freq = st.selectbox("Resample bars", ["10s", "30s", "1min", "5min", "15min", "1H", "1D"], index=2)
    roll_window = st.slider("Rolling window (bars)", 5, 300, 30, 1)
    min_ratio_points = st.slider("Min bars for ratios", 10, 2000, 300, 10)

    st.markdown("## Beta / Regimes")
    beta_window = st.slider("Rolling beta window (bars)", 10, 500, 60, 5)
    regime_window = st.slider("Regime vol window (bars)", 10, 500, 60, 5)

# Auto refresh
if auto_refresh:
    st_autorefresh(interval=refresh_s * 1000, key="autorefresh")

# Keyboard shortcuts listener (returns last key pressed as a string)
key = st_keyup("", key="keypress", label_visibility="collapsed")


# Shortcut handling
def cycle_accent(delta: int) -> None:
    i = ACCENTS.index(st.session_state.accent)
    st.session_state.accent = ACCENTS[(i + delta) % len(ACCENTS)]


if key:
    k = key.lower().strip()
    if k == "1":
        st.session_state.page = "PRICES"
    elif k == "2":
        st.session_state.page = "RISK"
    elif k == "3":
        st.session_state.page = "BETA"
    elif k == "4":
        st.session_state.page = "REGIMES"
    elif k == "5":
        st.session_state.page = "DEX ↔ VOL"
    elif k == "t":
        st.session_state.mode = "Bloomberg Light" if st.session_state.mode == "Bloomberg Dark" else "Bloomberg Dark"
        st.rerun()
    elif k == "a":
        cycle_accent(+1)
        st.rerun()
    elif k == "z":
        cycle_accent(-1)
        st.rerun()


# Theme constants
DARK_BG = "#0b0f14"
DARK_PANEL = "#111823"
DARK_TEXT = "#e6edf3"
DARK_MUTED = "#9aa4b2"
GRID_DARK = "rgba(255,255,255,0.08)"

LIGHT_BG = "#f6f7fb"
LIGHT_PANEL = "#ffffff"
LIGHT_TEXT = "#0b0f14"
LIGHT_MUTED = "#51606e"
GRID_LIGHT = "rgba(0,0,0,0.08)"

ACCENT_HEX = {
    "Lime": "#b6ff00",
    "Cyan": "#00e5ff",
    "Magenta": "#ff2d55",
    "Amber": "#ffb020",
    "Blue": "#4da3ff",
}[st.session_state.accent]

is_dark = st.session_state.mode == "Bloomberg Dark"
BG = DARK_BG if is_dark else LIGHT_BG
PANEL = DARK_PANEL if is_dark else LIGHT_PANEL
TXT = DARK_TEXT if is_dark else LIGHT_TEXT
MUTED = DARK_MUTED if is_dark else LIGHT_MUTED
GRID = GRID_DARK if is_dark else GRID_LIGHT

# CSS + ticker tape animation + overlay fixes
st.markdown(
    f"""
<style>
.stApp {{ background: {BG}; color: {TXT}; }}
section[data-testid="stSidebar"] {{
  background: {PANEL};
  border-right: 1px solid rgba(128,128,128,0.18);
}}
.block-container {{
  padding-top: 1.0rem;
  padding-bottom: 1.0rem;
  position: relative;
  z-index: 1;
}}
/* Header row (title + Settings) as one panel */
.block-container [data-testid="stHorizontalBlock"]:first-of-type {{
  background: {PANEL};
  border: 1px solid rgba(128,128,128,0.18);
  border-radius: 14px;
  padding: 10px 14px;
  margin-bottom: 0.5rem;
  align-items: center;
}}

/* Prevent Streamlit header/toolbar from overlapping main content */
[data-testid="stHeader"] {{
  background: {BG};
  z-index: 999;
}}
[data-testid="stToolbar"] {{
  z-index: 1000;
}}
[data-testid="stAppViewContainer"] {{
  position: relative;
  z-index: 0;
}}

html, body, [class*="css"] {{
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}}

.panel {{
  background: {PANEL};
  border: 1px solid rgba(128,128,128,0.18);
  border-radius: 14px;
  padding: 10px 14px;
  position: relative;
  z-index: 2;
}}

.kpi {{
  background: {PANEL};
  border: 1px solid rgba(128,128,128,0.18);
  border-radius: 12px;
  padding: 10px 12px;
  position: relative;
  z-index: 2;
}}
.kpi .label {{ color: {MUTED}; font-size: 12px; }}
.kpi .value {{ color: {TXT}; font-size: 20px; margin-top: 6px; }}
.kpi .accent {{ color: {ACCENT_HEX}; font-size: 12px; margin-top: 8px; }}

/* Ticker tape — contain so it doesn't overlap nav */
.ticker-wrap {{
  background: {PANEL};
  border: 1px solid rgba(128,128,128,0.18);
  border-radius: 14px;
  overflow: hidden;
  padding: 8px 0;
  position: relative;
  z-index: 2;
  isolation: isolate;
}}
.ticker {{
  display: inline-block;
  white-space: nowrap;
  animation: ticker 22s linear infinite;
}}
.ticker:hover {{ animation-play-state: paused; }}
.ticker-item {{
  display: inline-block;
  padding: 0 26px;
  color: {TXT};
  font-size: 13px;
}}
.ticker-item .sym {{ color: {ACCENT_HEX}; font-weight: 700; }}
.ticker-item .muted {{ color: {MUTED}; }}
@keyframes ticker {{
  0% {{ transform: translate3d(100%,0,0); }}
  100% {{ transform: translate3d(-100%,0,0); }}
}}

/* Plotly chart container — contain so one chart doesn't overlap the next; margin so title doesn't overlap content above */
.js-plotly-plot .plotly .modebar {{
  z-index: 10;
}}
div[data-testid="stVerticalBlock"] > div:has(.js-plotly-plot) {{
  overflow: hidden;
  min-height: 480px;
  margin-top: 1.5rem;
  position: relative;
  z-index: 1;
  isolation: isolate;
  transform: translateZ(0);
  backface-visibility: hidden;
}}
/* Reduce title ghosting: force Plotly title into its own layer */
.js-plotly-plot .plotly .gtitle {{
  transform: translateZ(0);
  backface-visibility: hidden;
}}

a, a:visited {{ color: {ACCENT_HEX}; }}
</style>
""",
    unsafe_allow_html=True,
)

# Header: title left, Settings popover right
header_col1, header_col2 = st.columns([4, 1])
with header_col1:
    st.markdown(
        f"""
<div style="font-size:22px; font-weight:800; letter-spacing:0.6px;">CRYPTO ANALYZER</div>
<div style="color:{MUTED}; font-size:12px; margin-top:4px;">
  Keys: <span style="color:{ACCENT_HEX};">1–5</span> tabs • <span style="color:{ACCENT_HEX};">T</span> theme • <span style="color:{ACCENT_HEX};">A/Z</span> accent cycle
</div>
""",
        unsafe_allow_html=True,
    )
with header_col2:
    with st.popover("Settings", use_container_width=True):
        st.markdown("**Look & Feel**")
        st.selectbox(
            "Theme",
            ["Bloomberg Dark", "Bloomberg Light"],
            index=0 if st.session_state.mode == "Bloomberg Dark" else 1,
            key="settings_theme",
        )
        st.selectbox(
            "Accent",
            ACCENTS,
            index=ACCENTS.index(st.session_state.accent),
            key="settings_accent",
        )

# Page selector (Bloomberg-ish nav)
st.session_state.page = st.radio(
    "NAV",
    PAGES,
    index=PAGES.index(st.session_state.page),
    horizontal=True,
    label_visibility="collapsed",
)

st.write("")


def chart_df_cst(df_or_series):
    """Return a copy with index in display TZ (CST) for chart x-axis."""
    out = df_or_series.copy()
    out.index = to_display_tz(out.index)
    return out


def fig_style(fig: go.Figure, title: str, height: int = 430) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=14),
            x=0.02,
            xanchor="left",
        ),
        height=height,
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color=TXT, family="ui-monospace, Menlo, Consolas, monospace", size=12),
        margin=dict(l=18, r=18, t=72, b=18),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=0.98,
            xanchor="left",
            x=0,
            font=dict(color=MUTED, size=11),
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=PANEL, font_color=TXT, bordercolor="rgba(128,128,128,0.35)"),
    )
    fig.update_xaxes(
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor="rgba(128,128,128,0.25)", tickfont=dict(color=MUTED)
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID, zeroline=False, linecolor="rgba(128,128,128,0.25)", tickfont=dict(color=MUTED)
    )
    return fig


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
    spot_df = load_spot_prices(conn) if SPOT_TABLE in tables else None
finally:
    try:
        conn.close()
    except Exception:
        pass

if spot_df is None or spot_df.empty:
    sol_df2 = sol_df.copy()
    sol_df2["ts_utc"] = to_dt_utc(sol_df2["ts_utc"])
    sol_df2 = sol_df2.dropna(subset=["ts_utc"]).set_index("ts_utc").sort_index()
    prices_wide = (
        pd.DataFrame({"SOL": pd.to_numeric(sol_df2["spot_price_usd"], errors="coerce")}).resample(freq).last().dropna()
    )
else:
    prices_wide = resample_prices_wide(spot_df, freq)

liq = resample_liquidity(sol_df, freq)
periods_per_year = annualization_factor(freq)

if prices_wide.empty or len(prices_wide) < 3:
    st.error("Not enough aligned price data yet. Let the poller run longer.")
    st.stop()

# Show latest data time in CST so you can confirm poller is feeding the dashboard
latest_ts = prices_wide.index[-1]
latest_cst = to_display_tz(latest_ts)
if hasattr(latest_cst, "strftime"):
    latest_str = latest_cst.strftime("%Y-%m-%d %H:%M %Z")
else:
    latest_str = str(latest_cst)
st.caption(
    f"Data through: **{latest_str}** — turn on Auto-refresh to see new rows. After a data reset, refresh this page (F5) to load the DB."
)

symbols = list(prices_wide.columns)

rets = prices_wide.pct_change()
cum = (1.0 + rets.fillna(0)).cumprod() - 1.0
roll_vol = rets.rolling(roll_window).std(ddof=1) * np.sqrt(periods_per_year)

downside = rets.clip(upper=0)
roll_down_dev = downside.rolling(roll_window).apply(lambda x: np.sqrt((x * x).mean()), raw=True) * np.sqrt(
    periods_per_year
)
roll_sharpe = (rets.rolling(roll_window).mean() / rets.rolling(roll_window).std(ddof=1)) * np.sqrt(periods_per_year)

beta_series = pd.Series(dtype=float)
beta_static = float("nan")
if "SOL" in symbols and "BTC" in symbols:
    beta_series = rolling_beta(rets["SOL"], rets["BTC"], beta_window)
    df_beta = pd.concat([rets["SOL"], rets["BTC"]], axis=1).dropna()
    if len(df_beta) >= 10:
        cov = df_beta.iloc[:, 0].cov(df_beta.iloc[:, 1])
        var = df_beta.iloc[:, 1].var(ddof=1)
        beta_static = float(cov / var) if var and not np.isnan(var) else float("nan")

sol_vol_for_regime = (
    rets["SOL"].rolling(regime_window).std(ddof=1) * np.sqrt(periods_per_year) if "SOL" in symbols else None
)
regime_df = add_regime_from_percentile(sol_vol_for_regime) if sol_vol_for_regime is not None else pd.DataFrame()


# -----------------------------
# Ticker tape content
# -----------------------------
def fmt_money(x: float) -> str:
    if np.isnan(x):
        return "n/a"
    if x >= 1000:
        return f"{x:,.2f}"
    return f"{x:.4f}"


ticker_items = []
for sym in symbols:
    s = prices_wide[sym].dropna()
    if len(s) >= 2:
        last = float(s.iloc[-1])
        prev = float(s.iloc[-2])
        chg = (last / prev - 1.0) * 100.0 if prev else np.nan
        sign = "+" if chg >= 0 else ""
        ticker_items.append(
            f"<span class='sym'>{sym}</span> {fmt_money(last)} <span class='muted'>({sign}{chg:.2f}%)</span>"
        )
    elif len(s) == 1:
        last = float(s.iloc[-1])
        ticker_items.append(f"<span class='sym'>{sym}</span> {fmt_money(last)} <span class='muted'>(n/a)</span>")

liq_last = liq.dropna().iloc[-1] if liq.dropna().shape[0] else np.nan
ticker_items.append(
    f"<span class='sym'>DEX_LIQ</span> {liq_last:,.0f}"
    if not np.isnan(liq_last)
    else "<span class='sym'>DEX_LIQ</span> n/a"
)

ticker_html = " • ".join([f"<span class='ticker-item'>{it}</span>" for it in ticker_items])

st.markdown(
    f"""
<div class="ticker-wrap">
  <div class="ticker">{ticker_html} {ticker_html}</div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")

# -----------------------------
# KPI row
# -----------------------------
k1, k2, k3, k4, k5 = st.columns(5)
latest_liq = liq.dropna().iloc[-1] if liq.dropna().shape[0] else np.nan
bars = len(prices_wide)


def kpi(col, label, value, accent_text=""):
    col.markdown(
        f"""
<div class="kpi">
  <div class="label">{label}</div>
  <div class="value">{value}</div>
  <div class="accent">{accent_text}</div>
</div>
""",
        unsafe_allow_html=True,
    )


kpi(k1, "BARS", f"{bars}", f"resample={freq}")
kpi(k2, "WINDOW", f"{roll_window}", "rolling (bars)")
kpi(k3, "SYMBOLS", f"{len(symbols)}", ", ".join(symbols))
kpi(k4, "β SOL/BTC", ("n/a" if np.isnan(beta_static) else f"{beta_static:.2f}"), f"beta window={beta_window}")
kpi(k5, "DEX LIQ (USD)", ("n/a" if np.isnan(latest_liq) else f"{latest_liq:,.0f}"), f"refresh={refresh_s}s")

st.write("")


# -----------------------------
# Pages (no st.tabs; keyboard friendly)
# -----------------------------
page = st.session_state.page

if page == "PRICES":
    st.write("")
    norm = (prices_wide / prices_wide.iloc[0]) * 100.0
    fig = px.line(chart_df_cst(norm), x=chart_df_cst(norm).index, y=norm.columns)
    fig = fig_style(fig, "Normalized price (start = 100)")
    st.plotly_chart(fig, use_container_width=True)

    st.write("")
    cum_cst = chart_df_cst(cum)
    fig = px.line(cum_cst, x=cum_cst.index, y=cum.columns)
    fig = fig_style(fig, "Cumulative return")
    st.plotly_chart(fig, use_container_width=True)

    pick = st.selectbox("Histogram asset", symbols, index=0, key="hist_pick")
    st.write("")
    r = rets[pick].dropna()
    fig = px.histogram(r, nbins=70, marginal="rug")
    fig = fig_style(fig, f"{pick} return histogram ({freq} bars)", height=380)
    st.plotly_chart(fig, use_container_width=True)

elif page == "RISK":
    st.write("")
    rv_cst = chart_df_cst(roll_vol)
    fig = px.line(rv_cst, x=rv_cst.index, y=roll_vol.columns)
    fig = fig_style(fig, f"Rolling volatility (annualized) — window={roll_window} bars")
    st.plotly_chart(fig, use_container_width=True)

    st.write("")
    rd_cst = chart_df_cst(roll_down_dev)
    fig = px.line(rd_cst, x=rd_cst.index, y=roll_down_dev.columns)
    fig = fig_style(fig, f"Downside deviation (annualized) — window={roll_window} bars")
    st.plotly_chart(fig, use_container_width=True)

    st.write("")
    rs_cst = chart_df_cst(roll_sharpe)
    fig = px.line(rs_cst, x=rs_cst.index, y=roll_sharpe.columns)
    fig = fig_style(fig, f"Rolling Sharpe (rf=0) — window={roll_window} bars")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Ratio snapshot (gated)")
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
        out = pd.DataFrame(rows).set_index("symbol").round(4)
        st.dataframe(out, use_container_width=True)
    else:
        st.info(f"Need {min_ratio_points}+ aligned bars to show ratios (have {len(prices_wide)}).")

elif page == "BETA":
    if "SOL" not in symbols or "BTC" not in symbols:
        st.warning("Need SOL and BTC present to compute beta.")
    else:
        st.caption(f"Static beta: {beta_static:.3f} (aligned {freq} returns)")
        beta_cst = chart_df_cst(beta_series)
        fig = px.line(beta_cst, x=beta_cst.index, y=beta_series.values)
        fig = fig_style(fig, f"Rolling beta: SOL vs BTC — window={beta_window} bars")
        fig.data[0].update(name="beta", showlegend=False, line=dict(width=2.6, color=ACCENT_HEX))
        st.plotly_chart(fig, use_container_width=True)

elif page == "REGIMES":
    if "SOL" not in symbols:
        st.warning("SOL not present.")
    else:
        sol_vol = sol_vol_for_regime
        sol_vol_cst = chart_df_cst(sol_vol)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=sol_vol_cst.index,
                y=sol_vol.values,
                mode="lines",
                name="SOL vol (ann.)",
                line=dict(width=2.6, color=ACCENT_HEX),
            )
        )

        if not regime_df.empty and regime_df["regime"].notna().any():
            reg = regime_df["regime"].ffill()
            reg_cst = reg.copy()
            reg_cst.index = to_display_tz(reg.index)
            current = None
            start = None
            band = {
                "Low": "rgba(0,229,255,0.10)",
                "Mid": "rgba(255,176,32,0.10)",
                "High": "rgba(255,45,85,0.10)",
            }
            for t, v in reg_cst.items():
                if pd.isna(v):
                    continue
                if current is None:
                    current, start = v, t
                    continue
                if v != current:
                    fig.add_vrect(
                        x0=start,
                        x1=t,
                        fillcolor=band.get(current, "rgba(255,255,255,0.06)"),
                        line_width=0,
                        layer="below",
                    )
                    current, start = v, t
            if current is not None and start is not None:
                fig.add_vrect(
                    x0=start,
                    x1=reg_cst.index[-1],
                    fillcolor=band.get(current, "rgba(255,255,255,0.06)"),
                    line_width=0,
                    layer="below",
                )

        fig = fig_style(fig, f"SOL volatility regimes — vol window={regime_window} bars")
        st.plotly_chart(fig, use_container_width=True)

        st.write("")
        if not regime_df.empty:
            rp_cst = chart_df_cst(regime_df["vol_percentile"].to_frame())
            fig = px.line(rp_cst, x=rp_cst.index, y="vol_percentile")
            fig = fig_style(fig, "SOL volatility percentile (0..1)", height=360)
            st.plotly_chart(fig, use_container_width=True)

elif page == "DEX ↔ VOL":
    st.write("")
    if "SOL" not in symbols:
        st.warning("SOL not present.")
    else:
        sol_vol = rets["SOL"].rolling(roll_window).std(ddof=1) * np.sqrt(periods_per_year)

        scatter_df = pd.DataFrame({"liq_usd": liq, "sol_vol_ann": sol_vol, "sol_return": rets["SOL"]}).dropna()
        if not regime_df.empty and "regime" in regime_df.columns:
            scatter_df = scatter_df.join(regime_df[["regime"]], how="left")
        else:
            scatter_df["regime"] = "n/a"

        fig = px.scatter(
            scatter_df, x="liq_usd", y="sol_vol_ann", color="regime", hover_data=["sol_return"], opacity=0.85
        )
        fig.update_traces(marker=dict(size=9, line=dict(width=0.6, color="rgba(0,0,0,0.25)")))
        fig.update_xaxes(title="Dex liquidity (USD)")
        fig.update_yaxes(title="SOL rolling volatility (annualized)")
        fig = fig_style(fig, "Dex liquidity vs SOL volatility (colored by regime)")
        st.plotly_chart(fig, use_container_width=True)

st.caption("Shortcuts: 1–5 tabs • T theme • A/Z accent • ticker pauses on hover.")
