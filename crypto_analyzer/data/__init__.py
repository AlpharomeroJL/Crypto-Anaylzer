"""
Stable facade: data loaders from SQLite (load_bars, load_snapshots, get_factor_returns, etc.).
Imports config and read_api only; does not import cli or promotion. Do not add exports without updating __all__.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from crypto_analyzer.config import (
    ALLOWED_PRICE_COLUMNS,
    ALLOWED_SNAPSHOT_TABLES,
    allowed_bars_tables,
    db_path,
    db_table,
    is_btc_pair,
    price_column,
)
from crypto_analyzer.config import factor_symbol as config_factor_symbol
from crypto_analyzer.config import (
    min_liquidity_usd as config_min_liq,
)
from crypto_analyzer.config import (
    min_vol_h24 as config_min_vol,
)
from crypto_analyzer.read_api import _with_conn

NORMAL_COLUMNS = [
    "ts_utc",
    "chain_id",
    "pair_address",
    "base_symbol",
    "quote_symbol",
    "price_usd",
    "liquidity_usd",
    "vol_h24",
]


def _validate_snapshot_table_and_price_col(table: str, price_col: str) -> None:
    """Raise ValueError if table or price_col is not in the allowlist."""
    if table not in ALLOWED_SNAPSHOT_TABLES:
        raise ValueError(f"Invalid snapshot table {table!r}; allowed: {sorted(ALLOWED_SNAPSHOT_TABLES)}")
    if price_col not in ALLOWED_PRICE_COLUMNS:
        raise ValueError(f"Invalid price column {price_col!r}; allowed: {sorted(ALLOWED_PRICE_COLUMNS)}")


def load_snapshots(
    db_path_override: Optional[str] = None,
    table_override: Optional[str] = None,
    price_col_override: Optional[str] = None,
    min_liquidity_usd: Optional[float] = None,
    min_vol_h24: Optional[float] = None,
    only_pairs: Optional[List[tuple]] = None,
    apply_filters: bool = True,
) -> pd.DataFrame:
    path = db_path_override or db_path()
    table = table_override or db_table()
    price_col = price_col_override or price_column()
    _validate_snapshot_table_and_price_col(table, price_col)
    min_liq = min_liquidity_usd if min_liquidity_usd is not None else config_min_liq()
    min_vol = min_vol_h24 if min_vol_h24 is not None else config_min_vol()

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
    try:
        with _with_conn(path) as con:
            df = pd.read_sql_query(query, con, params=params if params else None)
    except Exception as e:
        if "no such table" not in str(e).lower():
            raise
        import warnings

        warnings.warn(
            f"load_snapshots: table {table!r} does not exist (DEX may be skipped). Return empty.",
            UserWarning,
            stacklevel=2,
        )
        return pd.DataFrame(
            columns=[
                "ts_utc",
                "chain_id",
                "pair_address",
                "base_symbol",
                "quote_symbol",
                "price_usd",
                "liquidity_usd",
                "vol_h24",
            ]
        )

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

        warnings.warn(
            f"load_snapshots: dropped {int(n_bad)} rows with non-positive price_usd (table {table})",
            UserWarning,
            stacklevel=2,
        )
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
        from crypto_analyzer.integrity import assert_monotonic_time_index

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
    path = db_path_override or db_path()
    table = f"bars_{freq.replace(' ', '')}"
    allowed = allowed_bars_tables()
    if table not in allowed:
        raise ValueError(f"Invalid bars table {table!r}; allowed: {sorted(allowed)}")
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
        with _with_conn(path) as con:
            df = pd.read_sql_query(query, con, params=params if params else None)
    except Exception as e:
        # pandas wraps sqlite3.OperationalError as pandas.errors.DatabaseError
        if "no such table" not in str(e).lower():
            raise
        import warnings

        warnings.warn(
            f"load_bars: table {table!r} does not exist (run materialize_bars for this freq). Return empty.",
            UserWarning,
            stacklevel=2,
        )
        return pd.DataFrame()
    if df.empty:
        return df
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc", "chain_id", "pair_address", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    n_bad = (df["close"] <= 0).sum()
    df = df[df["close"] > 0]
    if n_bad > 0:
        import warnings

        warnings.warn(
            f"load_bars: dropped {int(n_bad)} rows with non-positive close (table {table})", UserWarning, stacklevel=2
        )
    if min_bars is not None:
        counts = df.groupby(["chain_id", "pair_address"]).size()
        valid = counts[counts >= min_bars].index
        df = df[df.set_index(["chain_id", "pair_address"]).index.isin(valid)].reset_index(drop=True)
    try:
        from crypto_analyzer.integrity import assert_monotonic_time_index

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
    path = db_path_override or db_path()
    with _with_conn(path) as con:
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

        warnings.warn(
            f"load_spot_series: dropped {int(n_bad)} rows with non-positive spot_price_usd (symbol={symbol})",
            UserWarning,
            stacklevel=2,
        )
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
    sym = factor_symbol or config_factor_symbol()
    for col in returns_df.columns:
        if is_btc_pair(meta.get(col, "")):
            return returns_df[col].copy()
    spot = load_spot_series(db_path_override, sym)
    if spot.empty or len(spot) < 2:
        return None
    price = spot.resample(freq).last().dropna()
    log_ret = np.log(price).diff()
    return log_ret.reindex(returns_df.index).dropna(how="all")


def load_factor_run(
    db_path_override: str,
    factor_run_id: str,
) -> Optional[Tuple[Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]]:
    """
    Load a materialized factor run from factor_betas and residual_returns.
    Returns (betas_dict, r2_df, residual_df) in same shape as rolling_multifactor_ols:
    - betas_dict: {factor_name: DataFrame(index=ts_utc, columns=asset_id)}
    - r2_df: DataFrame(index=ts_utc, columns=asset_id), mean r2 across factors per (ts, asset)
    - residual_df: DataFrame(index=ts_utc, columns=asset_id)
    Returns None if factor_run_id has no rows (run missing or empty).
    """
    try:
        with _with_conn(db_path_override) as conn:
            cur = conn.execute(
                "SELECT ts_utc, asset_id, factor_name, beta, alpha, r2 FROM factor_betas WHERE factor_run_id = ?",
                (factor_run_id,),
            )
            beta_rows = cur.fetchall()
            if not beta_rows:
                return None
            cur = conn.execute(
                "SELECT ts_utc, asset_id, resid_log_return FROM residual_returns WHERE factor_run_id = ?",
                (factor_run_id,),
            )
            resid_rows = cur.fetchall()
            if not resid_rows:
                return None
    except sqlite3.OperationalError:
        return None

    # factor_betas: (ts_utc, asset_id, factor_name, beta, alpha, r2)
    betas_df = pd.DataFrame(
        beta_rows,
        columns=["ts_utc", "asset_id", "factor_name", "beta", "alpha", "r2"],
    )
    betas_df["ts_utc"] = pd.to_datetime(betas_df["ts_utc"])
    # Pivot per factor: index=ts_utc, columns=asset_id, values=beta
    betas_dict: Dict[str, pd.DataFrame] = {}
    for fname, grp in betas_df.groupby("factor_name"):
        pivot = grp.pivot(index="ts_utc", columns="asset_id", values="beta")
        betas_dict[fname] = pivot
    # r2: one per (ts, asset, factor); take mean across factors per (ts, asset)
    r2_pivot = betas_df.groupby(["ts_utc", "asset_id"])["r2"].mean().reset_index()
    r2_df = r2_pivot.pivot(index="ts_utc", columns="asset_id", values="r2")

    # residual_returns: (ts_utc, asset_id, resid_log_return)
    resid_df = pd.DataFrame(resid_rows, columns=["ts_utc", "asset_id", "resid_log_return"])
    resid_df["ts_utc"] = pd.to_datetime(resid_df["ts_utc"])
    residual_df = resid_df.pivot(index="ts_utc", columns="asset_id", values="resid_log_return")

    return betas_dict, r2_df, residual_df


# Do not add exports without updating __all__.
__all__ = [
    "NORMAL_COLUMNS",
    "append_spot_returns_to_returns_df",
    "get_factor_returns",
    "load_bars",
    "load_factor_run",
    "load_snapshots",
    "load_snapshots_as_bars",
    "load_spot_price_resampled",
    "load_spot_series",
]
