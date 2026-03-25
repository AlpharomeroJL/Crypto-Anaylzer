"""
Research universe: define assets available for cross-sectional research.
Quality filters from config; degrades gracefully when too few assets.
Research-only; no execution.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import (
    STABLE_SYMBOLS,
    exclude_stable_pairs,
    venue_coinbase_advanced_product_ids,
    venue_coinbase_advanced_slug,
)
from .config import min_bars as config_min_bars
from .data import append_spot_returns_to_returns_df, load_bars, load_venue_bars_1h


def _is_stable_pair(base: str, quote: str) -> bool:
    """True if both base and quote are stablecoin symbols."""
    b = (base or "").upper().strip()
    q = (quote or "").upper().strip()
    return b in STABLE_SYMBOLS and q in STABLE_SYMBOLS


def _sanity_returns(ser: pd.Series) -> bool:
    """True if series has finite values and is not constant (std > 0 or len < 2)."""
    r = ser.dropna()
    if len(r) < 2:
        return False
    if not np.isfinite(r.values).all():
        return False
    if r.std(ddof=1) == 0 or (r.std(ddof=1) != r.std(ddof=1)):
        return False
    return True


def get_research_assets(
    db_path: str,
    freq: str,
    include_spot: bool = True,
    min_bars_override: Optional[int] = None,
    exclude_stable_override: Optional[bool] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build returns matrix and asset metadata for research.

    Returns:
        returns_df: index=ts_utc, columns=asset_id (DEX pair_id + optionally ETH_spot, BTC_spot).
        meta_df: columns asset_id, label, asset_type (dex|spot), chain_id, pair_address (NaN for spot).

    Quality filters: min_bars (config or override), exclude stable/stable pairs (config or override).
    Drops assets with non-finite or constant returns. If fewer than 1 asset remains, returns empty
    DataFrames. For cross-sectional work, callers should require >= 3 assets and show a message.
    """
    min_bars = (
        min_bars_override if min_bars_override is not None else (config_min_bars() if callable(config_min_bars) else 48)
    )
    exclude_stable = (
        exclude_stable_override
        if exclude_stable_override is not None
        else (exclude_stable_pairs() if callable(exclude_stable_pairs) else True)
    )

    try:
        bars = load_bars(freq, db_path_override=db_path, min_bars=min_bars)
    except FileNotFoundError:
        return pd.DataFrame(), pd.DataFrame()

    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()

    bars = bars.copy()
    bars["pair_id"] = bars["chain_id"].astype(str) + ":" + bars["pair_address"].astype(str)
    bars["label"] = bars["base_symbol"].fillna("").astype(str) + "/" + bars["quote_symbol"].fillna("").astype(str)

    if exclude_stable:
        bars = bars[~bars.apply(lambda r: _is_stable_pair(r.get("base_symbol", ""), r.get("quote_symbol", "")), axis=1)]
        if bars.empty:
            return pd.DataFrame(), pd.DataFrame()

    returns_df = bars.pivot_table(index="ts_utc", columns="pair_id", values="log_return").dropna(how="all")
    meta = (
        bars.groupby("pair_id")
        .agg(
            label=("label", "last"),
            chain_id=("chain_id", "first"),
            pair_address=("pair_address", "first"),
        )
        .to_dict(orient="index")
    )

    meta_rows = []
    for aid in returns_df.columns:
        m = meta.get(aid, {})
        meta_rows.append(
            {
                "asset_id": aid,
                "label": m.get("label", aid),
                "asset_type": "dex",
                "chain_id": m.get("chain_id", ""),
                "pair_address": m.get("pair_address", ""),
            }
        )

    if include_spot:
        label_dict = {r["asset_id"]: r["label"] for r in meta_rows}
        returns_df, _ = append_spot_returns_to_returns_df(returns_df, label_dict, db_path_override=db_path, freq=freq)
        for col in returns_df.columns:
            if col not in [r["asset_id"] for r in meta_rows]:
                meta_rows.append(
                    {
                        "asset_id": col,
                        "label": col,
                        "asset_type": "spot",
                        "chain_id": "",
                        "pair_address": "",
                    }
                )

    # Sanity: drop assets with non-finite or constant returns
    valid_cols = [c for c in returns_df.columns if _sanity_returns(returns_df[c])]
    returns_df = returns_df[valid_cols].copy()
    meta_df = pd.DataFrame(meta_rows)
    if not meta_df.empty:
        meta_df = (
            meta_df[meta_df["asset_id"].isin(valid_cols)].drop_duplicates(subset=["asset_id"]).reset_index(drop=True)
        )

    return returns_df, meta_df


def get_benchmark_majors_assets(
    db_path: str,
    *,
    min_bars_override: Optional[int] = None,
    venue: Optional[str] = None,
    product_ids: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Majors venue panel from venue_bars_1h (Coinbase Advanced Trade Phase 1).

    Columns are product_id (e.g. BTC-USD). Does not append Consumer spot snapshots.
    """
    min_bars = (
        min_bars_override if min_bars_override is not None else (config_min_bars() if callable(config_min_bars) else 48)
    )
    v = venue or venue_coinbase_advanced_slug()
    pids = product_ids if product_ids is not None else venue_coinbase_advanced_product_ids()

    bars = load_venue_bars_1h(
        db_path_override=db_path,
        venue=v,
        min_bars=min_bars,
        product_ids=pids if pids else None,
    )
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame()

    close_pt = bars.pivot_table(index="ts_utc", columns="product_id", values="close")
    lr_pt = bars.pivot_table(index="ts_utc", columns="product_id", values="log_return")
    returns_df = pd.DataFrame(index=close_pt.index)
    for c in close_pt.columns:
        s = lr_pt[c] if c in lr_pt.columns else None
        if s is None or s.notna().sum() == 0:
            returns_df[c] = np.log(close_pt[c]).diff()
        else:
            returns_df[c] = s

    returns_df = returns_df.dropna(how="all")

    meta_rows = []
    for pid in returns_df.columns:
        meta_rows.append(
            {
                "asset_id": pid,
                "label": pid,
                "asset_type": "venue_majors",
                "chain_id": "",
                "pair_address": "",
            }
        )

    valid_cols = [c for c in returns_df.columns if _sanity_returns(returns_df[c])]
    returns_df = returns_df[valid_cols].copy()
    meta_df = pd.DataFrame([r for r in meta_rows if r["asset_id"] in valid_cols])
    if not meta_df.empty:
        meta_df = meta_df.drop_duplicates(subset=["asset_id"]).reset_index(drop=True)

    returns_df = returns_df.sort_index()
    return returns_df, meta_df


def get_benchmark_majors_volume_panel(
    db_path: str,
    *,
    min_bars_override: Optional[int] = None,
    venue: Optional[str] = None,
    product_ids: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Venue-reported bar **volume** (base-asset units) from ``venue_bars_1h``, pivoted like returns.

    Same universe filter as ``get_benchmark_majors_assets`` (min_bars, venue, product_ids).
    Index ``ts_utc``, columns ``product_id``. No DEX fields.

    Used for majors-native participation / flow proxies without new tables or vendors.
    """
    min_bars = (
        min_bars_override if min_bars_override is not None else (config_min_bars() if callable(config_min_bars) else 48)
    )
    v = venue or venue_coinbase_advanced_slug()
    pids = product_ids if product_ids is not None else venue_coinbase_advanced_product_ids()

    bars = load_venue_bars_1h(
        db_path_override=db_path,
        venue=v,
        min_bars=min_bars,
        product_ids=pids if pids else None,
    )
    if bars.empty or "volume" not in bars.columns:
        return pd.DataFrame()

    bars = bars.copy()
    bars["volume"] = pd.to_numeric(bars["volume"], errors="coerce")
    vol = bars.pivot_table(index="ts_utc", columns="product_id", values="volume", aggfunc="last")
    vol.index = pd.to_datetime(vol.index, utc=True, errors="coerce")
    vol = vol.sort_index()
    vol = vol.dropna(axis=0, how="all")
    return vol
