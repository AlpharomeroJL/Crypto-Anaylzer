"""
Null suite: random signal, permuted signal, block-shuffled time. Produces null IC and
Sharpe distributions and p-value estimates. Research-only; for CI run on small fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from .alpha_research import information_coefficient
from .artifacts import write_json_sorted
from .features import bars_per_year


def null_1_random_ranks(signal_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Null 1: at each timestamp, random cross-sectional ranks (same shape as signal)."""
    rng = np.random.default_rng(seed)
    out = signal_df.copy()
    for t in out.index:
        n = out.loc[t].notna().sum()
        if n < 2:
            continue
        perm = rng.permutation(n)
        ranks = np.zeros(len(out.columns))
        ranks[:] = np.nan
        valid = out.columns[out.loc[t].notna()]
        ranks[out.columns.get_indexer(valid)] = perm
        out.loc[t] = ranks
    return out


def null_2_permute_signal(signal_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Null 2: at each timestamp, permute signal values across assets (break signal-return link)."""
    rng = np.random.default_rng(seed)
    out = signal_df.copy()
    for t in out.index:
        row = out.loc[t].dropna()
        if len(row) < 2:
            continue
        idx = row.index
        out.loc[t, idx] = rng.permutation(row.values)
    return out


def null_3_block_shuffle(signal_df: pd.DataFrame, block_size: int, seed: int) -> pd.DataFrame:
    """Null 3: permute contiguous time blocks (preserve within-block dependence)."""
    rng = np.random.default_rng(seed)
    idx = signal_df.index.tolist()
    n = len(idx)
    if n < block_size or block_size < 1:
        return signal_df.copy()
    n_blocks = (n + block_size - 1) // block_size
    block_starts = [i * block_size for i in range(n_blocks)]
    perm_blocks = rng.permutation(n_blocks)
    new_order = []
    for b in perm_blocks:
        start = block_starts[b]
        end = min(start + block_size, n)
        new_order.extend(range(start, end))
    new_order = new_order[:n]
    reindexed = signal_df.iloc[new_order].copy()
    reindexed.index = signal_df.index
    return reindexed


def run_null_suite(
    signal_df: pd.DataFrame,
    returns_df: pd.DataFrame,
    n_sim: int = 100,
    block_size: int = 10,
    seed: int = 42,
    freq: str = "1h",
) -> "NullSuiteResult":
    """
    Run null 1, 2, 3 each n_sim times; compute mean_ic and annualized Sharpe per run.
    Returns NullSuiteResult with null_ic_means, null_sharpe, observed_ic, observed_sharpe, p_values.
    """
    fwd = returns_df.shift(-1).dropna(how="all")
    common = signal_df.index.intersection(fwd.index)
    if len(common) < 10:
        return NullSuiteResult(
            null_ic_means={"null1": [], "null2": [], "null3": []},
            null_sharpe={"null1": [], "null2": [], "null3": []},
            observed_mean_ic=np.nan,
            observed_sharpe=np.nan,
            p_value_ic={"null1": np.nan, "null2": np.nan, "null3": np.nan},
            p_value_sharpe={"null1": np.nan, "null2": np.nan, "null3": np.nan},
        )
    signal_aligned = signal_df.reindex(common).dropna(how="all")
    fwd_aligned = fwd.reindex(common).dropna(how="all")
    obs_ic = information_coefficient(signal_aligned, fwd_aligned, method="spearman")
    observed_mean_ic = float(obs_ic.mean()) if obs_ic.notna().any() else np.nan

    # Simple long-short: rank signal, top - bottom; gross Sharpe from that portfolio
    def _sharpe_from_signal(sig: pd.DataFrame, fwd_ret: pd.DataFrame) -> float:
        common_t = sig.index.intersection(fwd_ret.index)
        if len(common_t) < 5:
            return np.nan
        ic_ts = information_coefficient(sig.reindex(common_t), fwd_ret.reindex(common_t), method="spearman")
        if ic_ts.empty or ic_ts.notna().sum() < 5:
            return np.nan
        bars_yr = bars_per_year(freq)
        return (
            float(ic_ts.mean() / ic_ts.std(ddof=1) * np.sqrt(bars_yr))
            if ic_ts.std(ddof=1) and ic_ts.std(ddof=1) != 0
            else np.nan
        )

    observed_sharpe = _sharpe_from_signal(signal_aligned, fwd_aligned)
    rng = np.random.default_rng(seed)
    null_ic = {"null1": [], "null2": [], "null3": []}
    null_sharpe = {"null1": [], "null2": [], "null3": []}
    for i in range(n_sim):
        s1 = rng.integers(0, 2**31)
        n1 = null_1_random_ranks(signal_aligned, s1)
        ic1 = information_coefficient(n1, fwd_aligned, method="spearman")
        null_ic["null1"].append(float(ic1.mean()) if ic1.notna().any() else np.nan)
        null_sharpe["null1"].append(_sharpe_from_signal(n1, fwd_aligned))
        n2 = null_2_permute_signal(signal_aligned, s1 + 1)
        ic2 = information_coefficient(n2, fwd_aligned, method="spearman")
        null_ic["null2"].append(float(ic2.mean()) if ic2.notna().any() else np.nan)
        null_sharpe["null2"].append(_sharpe_from_signal(n2, fwd_aligned))
        n3 = null_3_block_shuffle(signal_aligned, block_size, s1 + 2)
        ic3 = information_coefficient(n3, fwd_aligned, method="spearman")
        null_ic["null3"].append(float(ic3.mean()) if ic3.notna().any() else np.nan)
        null_sharpe["null3"].append(_sharpe_from_signal(n3, fwd_aligned))

    def p_val(null_vals: List[float], obs: float) -> float:
        arr = np.array([x for x in null_vals if np.isfinite(x)])
        if len(arr) == 0 or not np.isfinite(obs):
            return np.nan
        return float(np.mean(arr >= obs))

    p_ic = {k: p_val(null_ic[k], observed_mean_ic) for k in null_ic}
    p_sharpe = {k: p_val(null_sharpe[k], observed_sharpe) for k in null_sharpe}
    return NullSuiteResult(
        null_ic_means=null_ic,
        null_sharpe=null_sharpe,
        observed_mean_ic=observed_mean_ic,
        observed_sharpe=observed_sharpe,
        p_value_ic=p_ic,
        p_value_sharpe=p_sharpe,
    )


@dataclass
class NullSuiteResult:
    null_ic_means: dict
    null_sharpe: dict
    observed_mean_ic: float
    observed_sharpe: float
    p_value_ic: dict
    p_value_sharpe: dict


def write_null_suite_artifacts(result: NullSuiteResult, out_dir: str | Path) -> List[str]:
    """Write null_ic_dist.csv, null_sharpe_dist.csv, null_pvalues.json to out_dir. Returns paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    rows_ic = []
    for null_type, vals in result.null_ic_means.items():
        for i, v in enumerate(vals):
            rows_ic.append({"null_type": null_type, "run_id": i, "mean_ic": v})
    if rows_ic:
        df_ic = pd.DataFrame(rows_ic)
        p_ic = out_dir / "null_ic_dist.csv"
        # Stable column order and no index for deterministic hashes
        df_ic.reindex(columns=sorted(df_ic.columns)).to_csv(p_ic, index=False, encoding="utf-8")
        paths.append(str(p_ic))
    rows_sharpe = []
    for null_type, vals in result.null_sharpe.items():
        for i, v in enumerate(vals):
            rows_sharpe.append({"null_type": null_type, "run_id": i, "sharpe_annual": v})
    if rows_sharpe:
        df_sharpe = pd.DataFrame(rows_sharpe)
        p_sharpe = out_dir / "null_sharpe_dist.csv"
        df_sharpe.reindex(columns=sorted(df_sharpe.columns)).to_csv(p_sharpe, index=False, encoding="utf-8")
        paths.append(str(p_sharpe))

    pvals = {
        "observed_mean_ic": result.observed_mean_ic,
        "observed_sharpe": result.observed_sharpe,
        "p_value_ic": result.p_value_ic,
        "p_value_sharpe": result.p_value_sharpe,
    }
    p_pvals = out_dir / "null_pvalues.json"
    write_json_sorted(pvals, p_pvals)
    paths.append(str(p_pvals))
    return paths
