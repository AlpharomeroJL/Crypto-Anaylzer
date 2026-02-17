"""
Streamlit UI helpers: safe dataframes for Arrow, formatting, rounding.
Research-only; no execution.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def safe_for_streamlit_df(df: pd.DataFrame) -> pd.DataFrame:
    """Cast object/category columns to str so pyarrow does not coerce to double (e.g. regime/beta_state)."""
    if df.empty:
        return df.copy()
    out = df.copy()
    for c in out.columns:
        d = out[c].dtype
        if d == "object" or str(d) == "category":
            out[c] = out[c].astype(str)
    return out


def format_percent(x: Any, decimals: int = 2) -> str:
    """Format as percentage; handles NaN."""
    if pd.isna(x):
        return "—"
    return f"{float(x) * 100:.{decimals}f}%"


def format_float(x: Any, decimals: int = 4) -> str:
    """Format float; handles NaN."""
    if pd.isna(x):
        return "—"
    return f"{float(x):.{decimals}f}"


def format_bps(x: Any, decimals: int = 1) -> str:
    """Format basis points."""
    if pd.isna(x):
        return "—"
    return f"{float(x):.{decimals}f} bps"


def apply_rounding(df: pd.DataFrame, col_rules: Optional[Dict[str, int]] = None) -> pd.DataFrame:
    """
    Round numeric columns. col_rules: {col_name: decimals}. If None, round all numeric to 4.
    """
    if df.empty:
        return df
    out = df.copy()
    if col_rules is None:
        col_rules = {}
    for c in out.columns:
        if out[c].dtype.kind in ("f", "i"):
            decimals = col_rules.get(c, 4)
            out[c] = out[c].round(decimals)
    return out


_safe_df = safe_for_streamlit_df
