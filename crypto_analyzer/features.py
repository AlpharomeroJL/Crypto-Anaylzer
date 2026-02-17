"""
Feature engineering from bar data: returns, volatility, drawdown, momentum, trend.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd


def _normalize_freq(freq: str) -> str:
    f = (freq or "").strip().replace(" ", "").lower()
    if f in ("1d", "1day", "d"):
        return "1D"
    if f in ("1h", "1hr", "h"):
        return "1h"
    if "min" in f:
        m = int("".join(c for c in f if c.isdigit()) or "5")
        return "15min" if m == 15 else "5min" if m <= 5 else f"{m}min"
    return freq.strip() if freq else "5min"


PERIODS_PER_YEAR = {"5min": 12 * 24 * 365, "15min": 4 * 24 * 365, "1h": 24 * 365, "1D": 365}


def periods_per_year(freq: str) -> float:
    n = _normalize_freq(freq)
    if n in PERIODS_PER_YEAR:
        return float(PERIODS_PER_YEAR[n])
    minutes_per_year = 365.25 * 24 * 60
    period_minutes = pd.Timedelta(freq).total_seconds() / 60
    return minutes_per_year / period_minutes


def bars_per_day(freq: str) -> float:
    n = _normalize_freq(freq)
    if n == "1D":
        return 1.0
    if n == "1h":
        return 24.0
    if n == "15min":
        return 96.0
    if n == "5min":
        return 288.0
    return 24 * 60 / (pd.Timedelta(freq).total_seconds() / 60)


def bars_per_year(freq: str) -> float:
    return periods_per_year(freq)


def annualize_sharpe(sharpe_per_bar: float, freq: str) -> float:
    if sharpe_per_bar is None or np.isnan(sharpe_per_bar):
        return np.nan
    return float(sharpe_per_bar * np.sqrt(periods_per_year(freq)))


def compute_drawdown_from_log_returns(log_return_series: pd.Series) -> Tuple[pd.Series, float]:
    r = log_return_series.dropna()
    if r.empty:
        return pd.Series(dtype=float), np.nan
    equity = np.exp(r.cumsum())
    return compute_drawdown_from_equity(equity)


def compute_drawdown_from_equity(equity_series: pd.Series) -> Tuple[pd.Series, float]:
    eq = equity_series.dropna()
    if eq.empty:
        return pd.Series(dtype=float), np.nan
    peak = eq.cummax()
    dd = eq / peak - 1.0
    max_dd = float(dd.min()) if len(dd) else np.nan
    return dd, max_dd


def compute_lookback_return(log_returns: pd.Series, lookback_bars: int) -> float:
    r = log_returns.dropna().tail(lookback_bars)
    if len(r) < lookback_bars or lookback_bars <= 0:
        return np.nan
    return float(np.exp(r.sum()) - 1.0)


def bars_for_lookback_hours(freq: str, hours: float) -> int:
    n = _normalize_freq(freq)
    if n == "1D":
        return max(1, int(hours / 24))
    if n == "1h":
        return max(1, int(hours))
    if n == "15min":
        return max(1, int(hours * 4))
    if n == "5min":
        return max(1, int(hours * 12))
    period_min = pd.Timedelta(freq).total_seconds() / 60
    return max(1, int(hours * 60 / period_min))


def period_return_bars(freq: str) -> dict:
    fm = pd.Timedelta(freq).total_seconds() / 60
    if fm >= 24 * 60:
        one_h = one_d = 1
        three_d = 3
    else:
        one_h = max(1, int(60 / fm))
        one_d = max(1, int(24 * 60 / fm))
        three_d = max(1, 3 * one_d)
    return {"1h": one_h, "24h": one_d, "1d": one_d, "3d": three_d}


def arithmetic_returns(close: pd.Series) -> pd.Series:
    return close.pct_change()


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close).diff()


def compute_ratio_series(numerator_price: pd.Series, denominator_price: pd.Series) -> pd.Series:
    idx = numerator_price.dropna().index.intersection(denominator_price.dropna().index)
    num = numerator_price.reindex(idx).dropna()
    den = denominator_price.reindex(idx).dropna()
    idx = num.index.intersection(den.index)
    num, den = num.loc[idx], den.loc[idx]
    return (num / den).replace([np.inf, -np.inf], np.nan).dropna()


def compute_lookback_return_from_price(price_or_ratio_series: pd.Series, lookback_bars: int) -> float:
    lr = log_returns(price_or_ratio_series).dropna().tail(lookback_bars)
    if len(lr) < lookback_bars or lookback_bars <= 0:
        return np.nan
    return float(np.exp(lr.sum()) - 1.0)


def cumulative_returns_log(log_ret: pd.Series) -> pd.Series:
    return np.exp(log_ret.cumsum()) - 1.0


def rolling_volatility(log_ret: pd.Series, window: int, ddof: int = 1) -> pd.Series:
    return log_ret.rolling(window, min_periods=1).std(ddof=ddof)


def annualized_volatility(log_ret: pd.Series, freq: str, window: Optional[int] = None) -> pd.Series:
    bars_yr = bars_per_year(freq)
    if window is not None:
        roll_std = log_ret.rolling(window, min_periods=1).std(ddof=1)
        return roll_std * np.sqrt(bars_yr)
    std = log_ret.std(ddof=1)
    return pd.Series(np.sqrt(bars_yr) * std, index=log_ret.index)


def drawdown(cum_return: pd.Series) -> pd.Series:
    return cum_return.cummax() - cum_return


def max_drawdown(cum_return: pd.Series) -> float:
    dd = drawdown(cum_return)
    return float(dd.max()) if len(dd) else np.nan


def momentum_returns(close: pd.Series, freq: str) -> pd.DataFrame:
    periods = period_return_bars(freq)
    log_ret = log_returns(close)
    out = pd.DataFrame(index=close.index)
    out["ret_1h"] = np.exp(log_ret.rolling(periods["1h"]).sum()) - 1.0
    out["ret_24h"] = np.exp(log_ret.rolling(periods["24h"]).sum()) - 1.0
    out["ret_1d"] = np.exp(log_ret.rolling(periods["1d"]).sum()) - 1.0
    out["ret_3d"] = np.exp(log_ret.rolling(periods["3d"]).sum()) - 1.0
    return out


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def trend_features(close: pd.Series, ema20_span: int = 20, ema50_span: int = 50) -> pd.DataFrame:
    out = pd.DataFrame(index=close.index)
    out["ema20"] = ema(close, ema20_span)
    out["ema50"] = ema(close, ema50_span)
    return out


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def liquidity_change_pct(liquidity_usd: pd.Series, window: int = 24) -> pd.Series:
    return liquidity_usd.pct_change(periods=window)


def compute_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    if returns_df.empty or returns_df.shape[1] < 2:
        return pd.DataFrame()
    return returns_df.corr()


def compute_rolling_correlation(returns_df: pd.DataFrame, window: int) -> pd.DataFrame:
    if returns_df.empty or len(returns_df) < window:
        return pd.DataFrame()
    if returns_df.shape[1] == 2:
        return returns_df.iloc[:, 0].rolling(window).corr(returns_df.iloc[:, 1]).to_frame("corr")
    out = pd.DataFrame(index=returns_df.index)
    ref = returns_df.iloc[:, 0]
    for c in returns_df.columns[1:]:
        out[c] = ref.rolling(window).corr(returns_df[c])
    return out


def compute_beta_vs_factor(asset_returns: pd.Series, factor_returns: pd.Series) -> float:
    joined = pd.concat([asset_returns.dropna(), factor_returns.dropna()], axis=1).dropna()
    if len(joined) < 2:
        return np.nan
    cov = joined.iloc[:, 0].cov(joined.iloc[:, 1])
    var_f = joined.iloc[:, 1].var(ddof=1)
    if var_f == 0 or np.isnan(var_f):
        return np.nan
    return float(cov / var_f)


def _align_returns(asset_ret: pd.Series, factor_ret: pd.Series) -> Tuple[pd.Series, pd.Series]:
    common = asset_ret.dropna().index.union(factor_ret.dropna().index)
    common = common[common.isin(asset_ret.index) & common.isin(factor_ret.index)]
    a = asset_ret.reindex(common).dropna()
    f = factor_ret.reindex(common).dropna()
    idx = a.index.intersection(f.index)
    return a.loc[idx], f.loc[idx]


def compute_excess_log_returns(
    asset_log_ret: pd.Series,
    factor_log_ret: pd.Series,
    beta_value: float,
) -> pd.Series:
    a, f = _align_returns(asset_log_ret, factor_log_ret)
    if len(a) < 2:
        return pd.Series(dtype=float)
    return a - beta_value * f


def compute_excess_cum_return(excess_log_ret: pd.Series) -> pd.Series:
    r = excess_log_ret.dropna()
    if r.empty:
        return pd.Series(dtype=float)
    return np.exp(r.cumsum()) - 1.0


def compute_excess_lookback_return(excess_log_ret: pd.Series, lookback_bars: int) -> float:
    r = excess_log_ret.dropna().tail(lookback_bars)
    if len(r) < lookback_bars or lookback_bars <= 0:
        return np.nan
    return float(np.exp(r.sum()) - 1.0)


def compute_rolling_corr(asset_ret: pd.Series, factor_ret: pd.Series, window: int) -> pd.Series:
    a, f = _align_returns(asset_ret, factor_ret)
    if len(a) < window:
        return pd.Series(dtype=float)
    return a.rolling(window).corr(f)


def compute_rolling_beta(asset_ret: pd.Series, factor_ret: pd.Series, window: int) -> pd.Series:
    a, f = _align_returns(asset_ret, factor_ret)
    if len(a) < window:
        return pd.Series(dtype=float)
    cov = a.rolling(window).cov(f)
    var_f = f.rolling(window).var(ddof=1)
    out = cov / var_f
    return out.where(var_f > 0, np.nan)


def rolling_windows_for_freq(freq: str) -> Tuple[int, int]:
    n = _normalize_freq(freq)
    if n == "1h":
        return 24, 72
    if n == "5min":
        return 288, 864
    if n == "15min":
        return 96, 288
    if n == "1D":
        return 7, 21
    return 24, 72


def compute_beta_compression(beta_short: float, beta_long: float) -> float:
    if (beta_short is None or np.isnan(beta_short)) or (beta_long is None or np.isnan(beta_long)):
        return np.nan
    return float(beta_long - beta_short)


def classify_beta_state(beta_btc_24: float, beta_btc_72: float, threshold: float = 0.15) -> str:
    if beta_btc_24 is None or np.isnan(beta_btc_24) or beta_btc_72 is None or np.isnan(beta_btc_72):
        return "unknown"
    if beta_btc_24 < beta_btc_72 - threshold:
        return "compressed"
    if beta_btc_24 > beta_btc_72 + threshold:
        return "expanded"
    return "stable"


def compute_dispersion_index(returns_df: pd.DataFrame) -> pd.Series:
    if returns_df.empty or returns_df.shape[1] < 2:
        return pd.Series(dtype=float)
    return returns_df.std(axis=1, ddof=1)


def compute_dispersion_zscore(disp_series: pd.Series, window: int) -> pd.Series:
    if disp_series.empty or len(disp_series) < window:
        return pd.Series(dtype=float)
    roll_mean = disp_series.rolling(window).mean()
    roll_std = disp_series.rolling(window).std(ddof=1)
    z = (disp_series - roll_mean) / roll_std
    return z.where(roll_std > 0, np.nan)


def dispersion_window_for_freq(freq: str) -> int:
    n = _normalize_freq(freq)
    if n == "1h":
        return 72
    if n == "5min":
        return 864
    if n == "15min":
        return 288
    if n == "1D":
        return 21
    return 72


def classify_vol_regime(
    short_vol: float,
    medium_vol: float,
    rising_threshold: float = 1.25,
    falling_threshold: float = 0.75,
) -> str:
    if medium_vol is None or np.isnan(medium_vol) or medium_vol <= 0:
        return "unknown"
    if short_vol is None or np.isnan(short_vol):
        return "unknown"
    ratio = short_vol / medium_vol
    if ratio >= rising_threshold:
        return "rising"
    if ratio <= falling_threshold:
        return "falling"
    return "stable"


def compute_bar_metrics(
    price: pd.Series,
    freq: str,
    window: int,
    liquidity_usd: Optional[pd.Series] = None,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    log_ret = log_returns(price)
    cum_ret = cumulative_returns_log(log_ret)
    roll_vol = rolling_volatility(log_ret, window)
    ann_vol = annualized_volatility(log_ret, freq, window=window)
    return log_ret, cum_ret, roll_vol, ann_vol


def add_features_to_bars(
    df: pd.DataFrame,
    freq: str,
    window: int,
    pair_id_col: str = "pair_id",
    close_col: str = "close",
) -> pd.DataFrame:
    out_dfs = []
    for pid, g in df.groupby(pair_id_col):
        g = g.sort_values("ts_utc").copy()
        close = g[close_col]
        log_ret, cum_ret, roll_vol, ann_vol = compute_bar_metrics(close, freq, window)
        g["log_return"] = log_ret.values
        g["cum_return"] = cum_ret.values
        g["roll_vol"] = roll_vol.values
        g["annual_vol"] = ann_vol.values
        g["drawdown"] = drawdown(cum_ret).values
        g["max_drawdown"] = max_drawdown(cum_ret)
        mom = momentum_returns(close, freq)
        for c in mom.columns:
            g[c] = mom[c].values
        trend = trend_features(close)
        for c in trend.columns:
            g[c] = trend[c].values
        g["rsi14"] = rsi(close, 14).values
        if "liquidity_usd" in g.columns:
            g["liquidity_change_pct"] = liquidity_change_pct(g["liquidity_usd"], window).values
        out_dfs.append(g)
    return pd.concat(out_dfs, ignore_index=True)
