"""
Streamlit UI helpers: safe dataframes for Arrow, formatting, rounding, width-compatible st_df/st_plot.
Research-only; no execution.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


def _streamlit_width_kwargs() -> dict:
    """Return width kwargs compatible with current Streamlit (avoids deprecation/TypeError)."""
    try:
        import streamlit as _st

        v = getattr(_st, "__version__", "0") or "0"
        parts = v.split(".")[:2]
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        if major > 1 or (major == 1 and minor >= 40):
            return {"width": "stretch"}
    except Exception:
        pass
    return {"use_container_width": True}


def streamlit_compatibility_caption() -> Optional[str]:
    """Return footer caption when using compatibility mode (use_container_width); None otherwise."""
    try:
        import streamlit as _st

        v = getattr(_st, "__version__", "0") or "0"
        parts = v.split(".")[:2]
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        if major > 1 or (major == 1 and minor >= 40):
            return None
        return "UI running in compatibility mode for Streamlit < 1.40; see crypto_analyzer.ui"
    except Exception:
        return None


def st_df(df: pd.DataFrame, **kwargs: Any) -> Any:
    """Display DataFrame with safe conversion and width-compatible kwargs. Use instead of st.dataframe."""
    safe = safe_for_streamlit_df(df)
    width_kw = _streamlit_width_kwargs()
    width_kw.update(kwargs)
    if "width" in width_kw:
        width_kw.pop("use_container_width", None)
    import streamlit as st

    return st.dataframe(safe, **width_kw)


def st_plot(fig: Any, **kwargs: Any) -> Any:
    """Display Plotly figure with width-compatible kwargs. Use instead of st.plotly_chart."""
    width_kw = _streamlit_width_kwargs()
    width_kw.update(kwargs)
    if "width" in width_kw:
        width_kw.pop("use_container_width", None)
    import streamlit as st

    return st.plotly_chart(fig, **width_kw)


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
