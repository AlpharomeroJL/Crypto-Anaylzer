"""
FDR-based multiple testing adjustment (BH, BY). Used for family-wise p-value correction
and discovery flags. Research-only.
"""

from __future__ import annotations

from typing import Literal, Tuple

import numpy as np
import pandas as pd


def adjust(
    p_values: pd.Series,
    method: Literal["bh", "by"] = "bh",
    q: float = 0.05,
) -> Tuple[pd.Series, pd.Series]:
    """
    Adjust p-values for multiple testing and return discovery flags.

    method: "bh" = Benjamini-Hochberg (independence or PRDS), "by" = Benjamini-Yekutieli (arbitrary dependence).
    q: target FDR level (e.g. 0.05).
    Returns (adjusted_p_values, discoveries) with same index as p_values.
    discoveries is boolean: True where adjusted_p_value <= q.
    """
    if p_values.empty:
        return pd.Series(dtype=float), pd.Series(dtype=bool)
    p = p_values.dropna()
    if p.empty:
        out_adj = pd.Series(np.nan, index=p_values.index, dtype=float)
        out_disc = pd.Series(False, index=p_values.index, dtype=bool)
        return out_adj, out_disc
    n = len(p)
    order = p.argsort()
    p_sorted = p.iloc[order]
    ranks = np.arange(1, n + 1, dtype=float)
    if method == "bh":
        # BH: adj[i] = min(1, p[i] * n / rank)
        adj_sorted = np.minimum(1.0, p_sorted.values * n / ranks)
    elif method == "by":
        # BY: c_n = sum(1/j for j=1..n); adj[i] = min(1, p[i] * n * c_n / rank)
        c_n = np.sum(1.0 / np.arange(1, n + 1))
        adj_sorted = np.minimum(1.0, p_sorted.values * n * c_n / ranks)
    else:
        raise ValueError(f"method must be 'bh' or 'by', got {method!r}")
    # Monotonicity: adjusted should be non-decreasing in original order
    for i in range(1, n):
        adj_sorted[i] = max(adj_sorted[i], adj_sorted[i - 1])
    adjusted = pd.Series(np.nan, index=p_values.index, dtype=float)
    adjusted.loc[p.index] = adj_sorted[np.argsort(order)]
    discoveries = (adjusted <= q) & adjusted.notna()
    return adjusted, discoveries
