"""
Normalized data layer: load from SQLite and return clean pandas DataFrames.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import (
    db_path,
    db_table,
    price_column,
    min_liquidity_usd as config_min_liq,
    min_vol_h24 as config_min_vol,
    is_btc_pair,
    factor_symbol as config_factor_symbol,
)

NORMAL_COLUMNS = [
    "ts_utc", "chain_id", "pair_address", "base_symbol", "quote_symbol",
    "price_usd", "liquidity_usd", "vol_h24",
]


def load_snapshots(
    db_path_override: Optional[str] = None,
    table_override: Optional[str] = None,
    price_col_override: Optional[str] = None,
    min_liquidity_usd: Optional[float] = None,
    min_vol_h24: Optional[float] = None,
    only_pairs: Optional[List[tuple]] = None,
    apply_filters: bool = True,
) -> pd.DataFrame:
    path = db_path_override or (db_path() if callable(db_path) else db_path)
    table = table_override or (db_table() if callable(db_table) else db_table)
    price_col = price_col_override or (price_column() if callable(price_column) else price_column)
    min_liq = min_liquidity_usd if min_liquidity_usd is not None else (config_min_liq() if callable(config_min_liq) else config_min_liq)
    min_vol = min_vol_h24 if min_vol_h24 is not None else (config_min_vol() if callable(config_min_vol) else config_min_vol)

    where = ""
    params: List[str] = []
    if only_pairs:
        clauses = []
        for cid, addr in only_pairs:
            clauses.append("(chain_id=? AND pair_address=?)")
            params.extend([cid, addr])
        where = "WHERE " + " OR ".join(clauses)

    select_price = f"{price_col} AS price_usd" if price_col != "price_usd" else "price_usd"
    query = f"""
        SELECT ts_utc, chain_id, pair_address, base_symbol, quote_symbol,
               {select_price}, liquidity_usd, vol_h24
        FROM {table} {where}
        ORDER BY ts_utc ASC
    """
    with sqlite3.connect(path) as con:
        df = pd.read_sql_query(query, con, params=params if params else None)

    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc", "chain_id", "pair_address", "price_usd"])
    df["price_usd"] = pd.to_numeric(df["price_usd"], errors="coerce")
    df = df.dropna(subset=["price_usd"])
    n_bad = (df["price_usd"] <= 0).sum()
    df = df[df["price_usd"] > 0]
    if n_bad > 0:
        import warnings
        warnings.warn(f"load_snapshots: dropped {int(n_bad)} rows with non-positive price_usd (table {table})", UserWarning, stacklevel=2)
    if apply_filters and (min_liq is not None or min_vol is not None):
        mask = pd.Series(True, index=df.index)
        if min_liq is not None and "liquidity_usd" in df.columns:
            liq = pd.to_numeric(df["liquidity_usd"], errors="coerce")
            mask = mask & (liq > min_liq)
        if min_vol is not None and "vol_h24" in df.columns:
            vol = pd.to_numeric(df["vol_h24"], errors="coerce")
            mask = mask & (vol > min_vol)
        df = df.loc[mask]
    df = df.reset_index(drop=True)
    try:
        from .integrity import assert_monotonic_time_index
        w = assert_monotonic_time_index(df, col="ts_utc")
        if w:
            import warnings
            warnings.warn(f"load_snapshots: {w}", UserWarning, stacklevel=2)
    except Exception:
        pass
    return df


def load_bars(
    freq: str,
    db_path_override: Optional[str] = None,
    min_bars: Optional[int] = None,
    only_pairs: Optional[List[tuple]] = None,
) -> pd.DataFrame:
    path = db_path_override or (db_path() if callable(db_path) else db_path)
    table = f"bars_{freq.replace(' ', '')}"
    where = ""
    params: List[str] = []
    if only_pairs:
        clauses = []
        for cid, addr in only_pairs:
            clauses.append("(chain_id=? AND pair_address=?)")
            params.extend([cid, addr])
        where = "WHERE " + " OR ".join(clauses)
    query = f"""
        SELECT ts_utc, chain_id, pair_address, base_symbol, quote_symbol,
               open, high, low, close, log_return, cum_return, roll_vol,
               liquidity_usd, vol_h24
        FROM {table} {where}
        ORDER BY ts_utc ASC
    """
    try:
        with sqlite3.connect(path) as con:
            df = pd.read_sql_query(query, con, params=params if params else None)
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            raise FileNotFoundError(
                f"Bars table '{table}' not found. Run: python materialize_bars.py --freq {freq}"
            ) from e
        raise
    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc", "chain_id", "pair_address", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    n_bad = (df["close"] <= 0).sum()
    df = df[df["close"] > 0]
    if n_bad > 0:
        import warnings
        warnings.warn(f"load_bars: dropped {int(n_bad)} rows with non-positive close (table {table})", UserWarning, stacklevel=2)
    if min_bars is not None:
        counts = df.groupby(["chain_id", "pair_address"]).size()
        valid = counts[counts >= min_bars].index
        df = df[df.set_index(["chain_id", "pair_address"]).index.isin(valid)].reset_index(drop=True)
    try:
        from .integrity import assert_monotonic_time_index
        w = assert_monotonic_time_index(df, col="ts_utc")
        if w:
            import warnings
            warnings.warn(f"load_bars: {w}", UserWarning, stacklevel=2)
    except Exception:
        pass
    return df


def _min_bars_filter_df(df: pd.DataFrame, min_bars: int, group_cols: List[str]) -> pd.DataFrame:
    if min_bars is None or min_bars <= 0:
        return df
    counts = df.groupby(group_cols).size()
    valid = counts[counts >= min_bars].index
    return df[df.set_index(group_cols).index.isin(valid)].reset_index(drop=True)


def load_snapshots_as_bars(
    freq: str,
    window: int,
    db_path_override: Optional[str] = None,
    table_override: Optional[str] = None,
    min_liquidity_usd: Optional[float] = None,
    min_vol_h24: Optional[float] = None,
    min_bars: Optional[int] = None,
) -> pd.DataFrame:
    df = load_snapshots(
        db_path_override=db_path_override,
        table_override=table_override,
        min_liquidity_usd=min_liquidity_usd,
        min_vol_h24=min_vol_h24,
        apply_filters=True,
    )
    if df.empty:
        return df
    df["pair_id"] = df["chain_id"].astype(str) + ":" + df["pair_address"].astype(str)
    out_rows = []
    for pair_id, g in df.groupby("pair_id"):
        g = g.sort_values("ts_utc").set_index("ts_utc")
        price = g["price_usd"].resample(freq).ohlc()
        price.columns = ["open", "high", "low", "close"]
        price = price.dropna(subset=["close"])
        if len(price) < max(2, window + 1):
            continue
        liq = g["liquidity_usd"].resample(freq).last()
        vol24 = g["vol_h24"].resample(freq).last()
        price["liquidity_usd"] = liq.reindex(price.index).ffill().bfill()
        price["vol_h24"] = vol24.reindex(price.index).ffill().bfill()
        price["chain_id"] = g["chain_id"].iloc[0]
        price["pair_address"] = g["pair_address"].iloc[0]
        price["base_symbol"] = g["base_symbol"].iloc[-1]
        price["quote_symbol"] = g["quote_symbol"].iloc[-1]
        log_ret = np.log(price["close"]).diff()
        price["log_return"] = log_ret
        price["cum_return"] = np.exp(log_ret.cumsum()) - 1.0
        price["roll_vol"] = log_ret.rolling(window).std()
        price["ts_utc"] = price.index
        out_rows.append(price.reset_index(drop=True))
    if not out_rows:
        return pd.DataFrame()
    out = pd.concat(out_rows, ignore_index=True)
    if min_bars is not None:
        out = _min_bars_filter_df(out, min_bars, ["chain_id", "pair_address"])
    return out


def load_spot_series(db_path_override: Optional[str] = None, symbol: str = "BTC") -> pd.Series:
    path = db_path_override or (db_path() if callable(db_path) else db_path())
    with sqlite3.connect(path) as con:
        df = pd.read_sql_query(
            "SELECT ts_utc, spot_price_usd FROM spot_price_snapshots WHERE symbol = ? ORDER BY ts_utc ASC",
            con,
            params=(symbol.upper(),),
        )
    if df.empty:
        return pd.Series(dtype=float)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc", "spot_price_usd"])
    df["spot_price_usd"] = pd.to_numeric(df["spot_price_usd"], errors="coerce")
    n_bad = (df["spot_price_usd"] <= 0).sum()
    df = df[df["spot_price_usd"] > 0]
    if n_bad > 0:
        import warnings
        warnings.warn(f"load_spot_series: dropped {int(n_bad)} rows with non-positive spot_price_usd (symbol={symbol})", UserWarning, stacklevel=2)
    return df.set_index("ts_utc")["spot_price_usd"].sort_index()


def load_spot_price_resampled(
    db_path_override: Optional[str] = None,
    symbol: str = "BTC",
    freq: str = "1h",
) -> pd.Series:
    spot = load_spot_series(db_path_override, symbol)
    if spot.empty or len(spot) < 2:
        return pd.Series(dtype=float)
    return spot.resample(freq).last().dropna()


def append_spot_returns_to_returns_df(
    returns_df: pd.DataFrame,
    meta: dict,
    db_path_override: Optional[str] = None,
    freq: str = "1h",
    spot_symbols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, dict]:
    if returns_df.empty:
        return returns_df, meta
    if spot_symbols is None:
        spot_symbols = ["ETH", "BTC"]
    out = returns_df.copy()
    meta = dict(meta)
    for sym in spot_symbols:
        spot = load_spot_series(db_path_override, sym)
        if spot.empty or len(spot) < 2:
            continue
        price = spot.resample(freq).last().dropna()
        log_ret = np.log(price).diff()
        aligned = log_ret.reindex(returns_df.index)
        col = f"{sym}_spot"
        out[col] = aligned
        meta[col] = col
    return out, meta


def get_factor_returns(
    returns_df: pd.DataFrame,
    meta: dict,
    db_path_override: Optional[str] = None,
    freq: str = "1h",
    factor_symbol: Optional[str] = None,
) -> Optional[pd.Series]:
    if "BTC_spot" in returns_df.columns:
        s = returns_df["BTC_spot"].copy()
        return s if not s.dropna().empty else None
    sym = factor_symbol or (config_factor_symbol() if callable(config_factor_symbol) else "BTC")
    for col in returns_df.columns:
        if is_btc_pair(meta.get(col, "")):
            return returns_df[col].copy()
    spot = load_spot_series(db_path_override, sym)
    if spot.empty or len(spot) < 2:
        return None
    price = spot.resample(freq).last().dropna()
    log_ret = np.log(price).diff()
    return log_ret.reindex(returns_df.index).dropna(how="all")
