"""
Reality Check (RC) p-value for max statistic over a family; Romano–Wolf stepdown stub.
Dependence-aware: joint null via block/stationary bootstrap. Phase 3 Slice 4.
See docs/spec/phase3_reality_check_slice4_alignment.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, Literal, Optional

import numpy as np
import pandas as pd

from crypto_analyzer.statistics import _stationary_bootstrap_indices


@dataclass
class RealityCheckConfig:
    """Config for Reality Check; defaults suitable for CI (small n_sim)."""

    metric: Literal["mean_ic", "deflated_sharpe"] = "mean_ic"
    horizon: Optional[int] = None
    n_sim: int = 200
    method: Literal["stationary", "block_fixed"] = "stationary"
    avg_block_length: int = 12
    block_size: int = 12
    seed: int = 42


def compute_sweep_statistic(
    results_df: pd.DataFrame,
    metric: Literal["mean_ic", "deflated_sharpe"] = "mean_ic",
    horizon: Optional[int] = None,
) -> pd.Series:
    """
    Build observed statistic Series indexed by hypothesis_id from a results DataFrame.
    results_df must have columns to identify hypothesis (e.g. signal, horizon) and the metric column.
    hypothesis_id = signal + '|' + str(horizon) (or similar). Deterministic sorted order.
    """
    if results_df.empty:
        return pd.Series(dtype=float)
    if "signal" in results_df.columns and "horizon" in results_df.columns:
        results_df = results_df.copy()
        results_df["hypothesis_id"] = results_df["signal"].astype(str) + "|" + results_df["horizon"].astype(str)
    elif "hypothesis_id" not in results_df.columns:
        results_df = results_df.copy()
        results_df["hypothesis_id"] = results_df.index.astype(str)
    col = "mean_ic" if metric == "mean_ic" else "deflated_sharpe"
    if col not in results_df.columns:
        return pd.Series(dtype=float)
    out = results_df.groupby("hypothesis_id", sort=True)[col].mean()
    return out.sort_index()


def reality_check_pvalue(
    stat_by_hypothesis: pd.Series,
    null_stats_matrix: np.ndarray,
) -> float:
    """
    RC p-value: (1 + #{b : T_b >= T_obs}) / (B + 1).
    T_obs = max(stat_by_hypothesis). T_b = max over h of null_stats_matrix[b, h].
    null_stats_matrix shape (n_sim, n_hypotheses); columns must align with stat_by_hypothesis.index order.
    """
    if stat_by_hypothesis.empty or null_stats_matrix.size == 0:
        return 1.0
    T_obs = float(stat_by_hypothesis.max())
    null_max = np.nanmax(null_stats_matrix, axis=1)
    count_ge = int(np.sum(null_max >= T_obs))
    B = null_stats_matrix.shape[0]
    return (1.0 + count_ge) / (B + 1.0)


def run_reality_check(
    observed_stats: pd.Series,
    null_generator: Callable[[int], np.ndarray],
    cfg: RealityCheckConfig,
) -> Dict:
    """
    Run RC: build null_stats_matrix by calling null_generator(b) for b in 0..n_sim-1,
    then compute rc_p_value. Returns dict with rc_p_value, observed_max, null_max_distribution.
    Romano–Wolf stepdown: stub (returns empty or NotImplemented when CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1).
    """
    if observed_stats.empty:
        return {
            "rc_p_value": 1.0,
            "observed_max": np.nan,
            "null_max_distribution": np.array([]),
            "n_sim": 0,
            "hypothesis_ids": [],
        }
    hypothesis_ids = sorted(observed_stats.index.tolist())
    n_sim = cfg.n_sim
    null_rows = []
    for b in range(n_sim):
        row = null_generator(b)
        if row is not None and len(row) == len(hypothesis_ids):
            null_rows.append(row)
    null_stats_matrix = np.array(null_rows, dtype=float) if null_rows else np.zeros((0, len(hypothesis_ids)))
    if null_stats_matrix.shape[0] == 0:
        rc_p_value = 1.0
    else:
        rc_p_value = reality_check_pvalue(observed_stats, null_stats_matrix)
    observed_max = float(observed_stats.max())
    null_max_dist = np.nanmax(null_stats_matrix, axis=1) if null_stats_matrix.size else np.array([])

    out = {
        "rc_p_value": float(rc_p_value),
        "observed_max": observed_max,
        "null_max_distribution": null_max_dist,
        "n_sim": null_stats_matrix.shape[0],
        "hypothesis_ids": hypothesis_ids,
        "rc_metric": cfg.metric,
        "rc_horizon": cfg.horizon,
        "rc_seed": cfg.seed,
        "rc_method": cfg.method,
        "rc_avg_block_length": cfg.avg_block_length,
    }
    if os.environ.get("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "").strip() == "1":
        raise NotImplementedError("Romano–Wolf stepdown not implemented; set CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=0 or unset")
    out["rw_adjusted_p_values"] = pd.Series(dtype=float)
    return out


def _block_fixed_bootstrap_indices(length: int, block_size: int, seed: Optional[int]) -> np.ndarray:
    """Fixed-size block bootstrap indices; same length as input."""
    if length < 1 or block_size < 1:
        return np.array([], dtype=int)
    if seed is not None:
        np.random.seed(seed)
    max_start = max(0, length - block_size)
    indices = []
    while len(indices) < length:
        start = int(np.random.randint(0, max_start + 1)) if max_start >= 0 else 0
        end = min(start + block_size, length)
        indices.extend(range(start, end))
    return np.array(indices[:length], dtype=int)


def make_null_generator_stationary(
    series_by_hypothesis: Dict[str, pd.Series],
    cfg: RealityCheckConfig,
) -> Callable[[int], np.ndarray]:
    """
    Build a null generator that uses stationary (or block_fixed) bootstrap.
    series_by_hypothesis: hypothesis_id -> time series (e.g. IC_t). Same index length for all.
    Returns callable f(b) -> 1d array of null statistics in sorted hypothesis_id order.
    """
    hyps = sorted(series_by_hypothesis.keys())
    if not hyps:
        def _null(b: int) -> np.ndarray:
            return np.array([])
        return _null
    common_idx = series_by_hypothesis[hyps[0]].index
    for h in hyps[1:]:
        common_idx = common_idx.intersection(series_by_hypothesis[h].index)
    length = len(common_idx)
    if length < 2:
        def _null(b: int) -> np.ndarray:
            return np.full(len(hyps), np.nan)
        return _null
    arrs = {
        h: np.asarray(series_by_hypothesis[h].reindex(common_idx).values, dtype=float)
        for h in hyps
    }

    def _null(b: int) -> np.ndarray:
        seed_b = cfg.seed + b
        if cfg.method == "stationary":
            idx = _stationary_bootstrap_indices(length, float(cfg.avg_block_length), seed_b)
        else:
            idx = _block_fixed_bootstrap_indices(length, cfg.block_size, seed_b)
        if len(idx) < 2:
            return np.full(len(hyps), np.nan)
        stats = []
        for h in hyps:
            vals = arrs[h][idx]
            stats.append(float(np.nanmean(vals)))
        return np.array(stats)
    return _null
