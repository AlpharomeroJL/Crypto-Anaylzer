"""
Shared backtest logic: trend/vol_breakout strategies, equity metrics.
Used by CLI (cli/backtest.py), walk-forward (walkforward.py), and dashboard (cli/app.py).
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd

from crypto_analyzer.execution_cost import (
    ExecutionCostConfig,
    ExecutionCostModel,
    slippage_bps_from_liquidity,
)
from crypto_analyzer.features import bars_per_year, ema, log_returns, rolling_volatility

# Default fees and slippage (documented in README); unified with ExecutionCostModel
DEFAULT_FEE_BPS = 30
DEFAULT_SLIPPAGE_BPS = 10


def run_trend_strategy(
    bars: pd.DataFrame,
    freq: str,
    ema_fast: int = 20,
    ema_slow: int = 50,
    vol_window: int = 24,
    vol_max: Optional[float] = None,
    position_pct: float = 0.25,
    fee_bps: float = DEFAULT_FEE_BPS,
    slippage_bps_fixed: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Trend: long when EMA20 > EMA50 and vol below vol_max (optional). Fixed fraction position. slippage_bps_fixed=None uses liquidity-based proxy."""
    bars = bars.sort_values(["chain_id", "pair_address", "ts_utc"])
    all_equity = []
    all_trades = []

    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").reset_index(drop=True)
        if len(g) < ema_slow + 5:
            continue
        close = g["close"]
        e20 = ema(close, ema_fast)
        e50 = ema(close, ema_slow)
        vol = rolling_volatility(log_returns(close), vol_window)
        long_signal = e20 > e50
        if vol_max is not None:
            long_signal = long_signal & (vol < vol_max)
        # Position: 1 when long, 0 when flat
        position = long_signal.astype(float) * position_pct
        ret = log_returns(close)
        prev_pos = position.shift(1).fillna(0)
        gross_ret = prev_pos * ret
        turnover = (position - prev_pos).abs()
        cfg = ExecutionCostConfig(fee_bps=fee_bps, slippage_bps=slippage_bps_fixed or DEFAULT_SLIPPAGE_BPS)
        if slippage_bps_fixed is not None:
            slip_series = None
        else:
            liq = g["liquidity_usd"] if "liquidity_usd" in g.columns else pd.Series(index=g.index, dtype=float)
            slip_series = liq.map(lambda x: slippage_bps_from_liquidity(x, cfg))
        model = ExecutionCostModel(cfg)
        strategy_ret, _ = model.apply_costs(gross_ret, turnover, slippage_bps_series=slip_series)
        equity = (1 + strategy_ret.fillna(0)).cumprod()
        equity.index = g["ts_utc"].values
        all_equity.append(equity)
        # Trades: entry/exit when position changes
        pos_diff = position.diff().fillna(0)
        entries = g.loc[pos_diff > 0, ["ts_utc", "chain_id", "pair_address", "close"]].copy()
        entries["side"] = "long"
        entries["position_pct"] = position_pct
        exits = g.loc[pos_diff < 0, ["ts_utc", "chain_id", "pair_address", "close"]].copy()
        exits["side"] = "exit"
        for _, row in entries.iterrows():
            all_trades.append(
                {
                    "ts_utc": row["ts_utc"],
                    "chain_id": cid,
                    "pair_address": addr,
                    "side": "long",
                    "price": row["close"],
                    "position_pct": position_pct,
                }
            )
        for _, row in exits.iterrows():
            all_trades.append(
                {
                    "ts_utc": row["ts_utc"],
                    "chain_id": cid,
                    "pair_address": addr,
                    "side": "exit",
                    "price": row["close"],
                    "position_pct": 0,
                }
            )

    if not all_equity:
        return pd.DataFrame(), pd.Series(dtype=float)
    if len(all_equity) == 1:
        equity_curve = all_equity[0]
    else:
        eq_df = pd.concat(all_equity, axis=1)
        idx = eq_df.index.union(eq_df.index).drop_duplicates().sort_values()
        eq_df = eq_df.reindex(idx).ffill().bfill()
        equity_curve = eq_df.mean(axis=1)
    trades_df = pd.DataFrame(all_trades) if all_trades else pd.DataFrame()
    return trades_df, equity_curve


def run_vol_breakout_strategy(
    bars: pd.DataFrame,
    freq: str,
    z_entry: float = 2.0,
    trailing_stop_pct: float = 0.05,
    vol_window: int = 24,
    position_pct: float = 0.25,
    fee_bps: float = DEFAULT_FEE_BPS,
    slippage_bps_fixed: Optional[float] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Vol breakout: enter when return z-score > z_entry; exit on trailing stop (from high)."""
    bars = bars.sort_values(["chain_id", "pair_address", "ts_utc"])
    all_equity = []
    all_trades = []

    for (cid, addr), g in bars.groupby(["chain_id", "pair_address"]):
        g = g.sort_values("ts_utc").reset_index(drop=True)
        if len(g) < vol_window + 10:
            continue
        close = g["close"]
        lr = log_returns(close)
        # Keep lr aligned with g (same index/length); rolling produces NaN for first vol_window-1
        mean_r = lr.rolling(vol_window).mean()
        std_r = lr.rolling(vol_window).std(ddof=1)
        z = (lr - mean_r) / std_r.replace(0, np.nan)
        position = pd.Series(0.0, index=g.index)
        high_water = close.copy()
        for pos in range(1, len(g)):
            if pos < vol_window or std_r.iloc[pos] == 0 or pd.isna(std_r.iloc[pos]) or pd.isna(z.iloc[pos]):
                position.iloc[pos] = position.iloc[pos - 1]
                continue
            if position.iloc[pos - 1] == 0 and z.iloc[pos] >= z_entry:
                position.iloc[pos] = position_pct
                high_water.iloc[pos] = close.iloc[pos]
            elif position.iloc[pos - 1] > 0:
                high_water.iloc[pos] = max(high_water.iloc[pos - 1], close.iloc[pos])
                if close.iloc[pos] < high_water.iloc[pos] * (1 - trailing_stop_pct):
                    position.iloc[pos] = 0
                else:
                    position.iloc[pos] = position.iloc[pos - 1]
            else:
                position.iloc[pos] = 0
        prev_pos = position.shift(1).fillna(0)
        gross_ret = prev_pos * lr
        turnover = (position - prev_pos).abs()
        cfg = ExecutionCostConfig(fee_bps=fee_bps, slippage_bps=slippage_bps_fixed or DEFAULT_SLIPPAGE_BPS)
        if slippage_bps_fixed is not None:
            slip_series = None
        else:
            liq = g["liquidity_usd"] if "liquidity_usd" in g.columns else pd.Series(index=g.index, dtype=float)
            slip_series = liq.map(lambda x: slippage_bps_from_liquidity(x, cfg))
        model = ExecutionCostModel(cfg)
        strategy_ret, _ = model.apply_costs(gross_ret, turnover, slippage_bps_series=slip_series)
        equity = (1 + strategy_ret.fillna(0)).cumprod()
        equity.index = g["ts_utc"].values
        all_equity.append(equity)
        pos_diff = position.diff().fillna(0)
        for i in g.index[pos_diff > 0]:
            all_trades.append(
                {
                    "ts_utc": g.loc[i, "ts_utc"],
                    "chain_id": cid,
                    "pair_address": addr,
                    "side": "long",
                    "price": g.loc[i, "close"],
                    "position_pct": position_pct,
                }
            )
        for i in g.index[pos_diff < 0]:
            all_trades.append(
                {
                    "ts_utc": g.loc[i, "ts_utc"],
                    "chain_id": cid,
                    "pair_address": addr,
                    "side": "exit",
                    "price": g.loc[i, "close"],
                    "position_pct": 0,
                }
            )

    if not all_equity:
        return pd.DataFrame(), pd.Series(dtype=float)
    if len(all_equity) == 1:
        equity_curve = all_equity[0]
    else:
        eq_df = pd.concat(all_equity, axis=1)
        idx = eq_df.index.union(eq_df.index).drop_duplicates().sort_values()
        eq_df = eq_df.reindex(idx).ffill().bfill()
        equity_curve = eq_df.mean(axis=1)
    trades_df = pd.DataFrame(all_trades) if all_trades else pd.DataFrame()
    return trades_df, equity_curve


def metrics(equity: pd.Series, freq: str) -> dict:
    """CAGR-ish, vol, Sharpe, Sortino, max DD, win rate, avg win/loss (from period returns)."""
    if equity.empty or len(equity) < 2:
        return {}
    ret = equity.pct_change().dropna()
    if ret.empty:
        return {}
    bars_yr = bars_per_year(freq)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    try:
        delta = equity.index[-1] - equity.index[0]
        n_years = delta.total_seconds() / (365.25 * 24 * 3600)
    except Exception:
        n_years = len(equity) / bars_yr
    if n_years <= 0:
        n_years = len(equity) / bars_yr
    cagr = (1 + total_return) ** (1 / n_years) - 1.0 if n_years > 0 else total_return
    vol = ret.std(ddof=1) * np.sqrt(bars_yr) if ret.std(ddof=1) else np.nan
    sharpe = (ret.mean() / ret.std(ddof=1)) * np.sqrt(bars_yr) if ret.std(ddof=1) and ret.std(ddof=1) != 0 else np.nan
    downside = ret[ret < 0]
    sortino = (
        (ret.mean() / downside.std(ddof=1)) * np.sqrt(bars_yr)
        if len(downside) > 1 and downside.std(ddof=1) != 0
        else np.nan
    )
    cum = (1 + ret).cumprod()
    dd = cum.cummax() - cum
    max_dd = float(dd.max()) if len(dd) else np.nan
    wins, losses = ret[ret > 0], ret[ret < 0]
    win_rate = len(wins) / len(ret) if len(ret) else np.nan
    avg_win = float(wins.mean()) if len(wins) else np.nan
    avg_loss = float(losses.mean()) if len(losses) else np.nan
    n_trades = 0  # caller can add from trades_df
    return {
        "total_return": total_return,
        "cagr": cagr,
        "vol_annual": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "n_bars": len(equity),
        "n_trades": n_trades,
    }
