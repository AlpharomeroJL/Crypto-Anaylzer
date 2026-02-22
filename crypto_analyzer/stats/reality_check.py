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

try:
    from crypto_analyzer.rng import SALT_RC_NULL
    from crypto_analyzer.rng import rng_for as _rng_for_central
except ImportError:
    _rng_for_central = None  # type: ignore[misc, assignment]
    SALT_RC_NULL = "rc_null"  # fallback only if rng not importable


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
    # Deterministic run_key-derived RNG (runtime-only; not serialized)
    run_key: Optional[str] = None
    seed_root: Optional[int] = None
    rng: Optional[np.random.Generator] = None


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


def _romano_wolf_stepdown(
    observed_stats: pd.Series,
    null_stats_matrix: np.ndarray,
) -> pd.Series:
    """
    Romano–Wolf stepdown adjusted p-values. observed_stats and null_stats_matrix columns
    must align (same hypothesis order). Returns Series index=hypothesis_id, values=adjusted p in [0,1].
    Stepdown order: by decreasing observed statistic. Adjusted p-values non-decreasing in that order.
    Caller must ensure observed_stats contains no NaN/inf (fail-closed: do not call if not finite).
    """
    if observed_stats.empty or null_stats_matrix.size == 0:
        return pd.Series(dtype=float)
    vals = np.asarray(observed_stats.values, dtype=float)
    if not np.all(np.isfinite(vals)):
        return pd.Series(dtype=float)
    # Order by decreasing observed stat (most significant first)
    order = np.argsort(-vals)
    hyp_index = observed_stats.index
    m = len(hyp_index)
    B = null_stats_matrix.shape[0]
    p_adj = np.ones(m)
    for j in range(m):
        # Remaining set: order[j], order[j+1], ..., order[m-1]
        remaining = order[j:]
        null_max_j = np.nanmax(null_stats_matrix[:, remaining], axis=1)
        T_j = observed_stats.iloc[order[j]]
        count_ge = int(np.sum(null_max_j >= T_j))
        p_adj[j] = (1.0 + count_ge) / (B + 1.0)
    # Enforce monotonicity (non-decreasing in stepdown order)
    for j in range(1, m):
        p_adj[j] = max(p_adj[j], p_adj[j - 1])
    # Map back to hypothesis_id order (same as observed_stats.index)
    result_vals = np.ones(m)
    for j in range(m):
        result_vals[order[j]] = p_adj[j]
    return pd.Series(result_vals, index=hyp_index)


def run_reality_check(
    observed_stats: pd.Series,
    null_generator: Callable[[int], np.ndarray],
    cfg: RealityCheckConfig,
    cached_null_max: Optional[np.ndarray] = None,
) -> Dict:
    """
    Run RC: build null_stats_matrix by calling null_generator(b) for b in 0..n_sim-1,
    then compute rc_p_value. Returns dict with rc_p_value, observed_max, null_max_distribution.
    Hypothesis order: canonical order is sorted(observed_stats.index). observed_stats is reindexed
    to this order for RC/RW; null_generator(b) must return a 1d array in the same order (column j
    = hypothesis_ids[j]). If cached_null_max is provided (1d array of length n_sim), skip
    null_generator and use it for RC only. When CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1: also compute
    Romano–Wolf stepdown (requires full null matrix; if only cached_null_max, RW skipped).
    Emits requested_n_sim and actual_n_sim; if actual < requested, n_sim_shortfall_warning is set.
    """
    if observed_stats.empty:
        return {
            "rc_p_value": 1.0,
            "observed_max": np.nan,
            "null_max_distribution": np.array([]),
            "requested_n_sim": 0,
            "actual_n_sim": 0,
            "n_sim": 0,
            "hypothesis_ids": [],
            "rw_adjusted_p_values": pd.Series(dtype=float),
        }
    # Canonical hypothesis order: sorted. All RC/RW use this order; null_generator rows must match.
    hypothesis_ids = sorted(observed_stats.index.tolist())
    obs_reindexed = observed_stats.reindex(hypothesis_ids)
    n_sim = cfg.n_sim
    requested_n_sim = n_sim
    rw_enabled = os.environ.get("CRYPTO_ANALYZER_ENABLE_ROMANOWOLF", "").strip() == "1"
    null_stats_matrix: Optional[np.ndarray] = None
    n_sim_shortfall_warning: Optional[str] = None

    if cached_null_max is not None and cached_null_max.size == n_sim and not rw_enabled:
        null_max_dist = np.asarray(cached_null_max, dtype=float).ravel()
        T_obs = float(obs_reindexed.max())
        count_ge = int(np.sum(null_max_dist >= T_obs))
        rc_p_value = (1.0 + count_ge) / (n_sim + 1.0)
        actual_n_sim = len(null_max_dist)
    else:
        null_rows = []
        dropped = 0
        for b in range(n_sim):
            row = null_generator(b)
            if row is not None and len(row) == len(hypothesis_ids):
                null_rows.append(row)
            else:
                dropped += 1
        null_stats_matrix = np.array(null_rows, dtype=float) if null_rows else np.zeros((0, len(hypothesis_ids)))
        actual_n_sim = null_stats_matrix.shape[0]
        if actual_n_sim < requested_n_sim:
            n_sim_shortfall_warning = f"actual_n_sim={actual_n_sim} < requested_n_sim={requested_n_sim}" + (
                f" ({dropped} null rows dropped due to length mismatch)" if dropped else ""
            )
        if null_stats_matrix.shape[0] == 0:
            rc_p_value = 1.0
        else:
            rc_p_value = reality_check_pvalue(obs_reindexed, null_stats_matrix)
        null_max_dist = np.nanmax(null_stats_matrix, axis=1) if null_stats_matrix.size else np.array([])
    observed_max = float(obs_reindexed.max())

    from crypto_analyzer.contracts.schema_versions import RC_SUMMARY_SCHEMA_VERSION
    from crypto_analyzer.rng import SALT_RC_NULL, SEED_ROOT_VERSION
    from crypto_analyzer.rng import seed_root as _seed_root

    # Seed derivation provenance: required for governance/audit; seed_version prevents "same run_key, different nulls" without explanation
    seed_root_val: Optional[int] = cfg.seed_root
    component_salt: Optional[str] = None
    seed_derivation: str = "explicit"
    seed_version: int = SEED_ROOT_VERSION
    if cfg.run_key:
        component_salt = SALT_RC_NULL
        seed_root_val = _seed_root(cfg.run_key, salt=component_salt, version=seed_version)
        seed_derivation = "run_key"
    null_construction_spec = {
        "method": cfg.method,
        "avg_block_length": cfg.avg_block_length,
        "block_size": cfg.block_size,
        "seed_derivation": seed_derivation,
        "seed_version": seed_version,
    }

    out: Dict = {
        "rc_summary_schema_version": RC_SUMMARY_SCHEMA_VERSION,
        "rc_p_value": float(rc_p_value),
        "observed_max": observed_max,
        "null_max_distribution": null_max_dist,
        "requested_n_sim": requested_n_sim,
        "actual_n_sim": actual_n_sim,
        "n_sim": actual_n_sim,
        "hypothesis_ids": hypothesis_ids,
        "rc_metric": cfg.metric,
        "rc_horizon": cfg.horizon,
        "rc_seed": cfg.seed,
        "rc_method": cfg.method,
        "rc_avg_block_length": cfg.avg_block_length,
        "seed_root": seed_root_val,
        "seed_version": seed_version,
        "component_salt": component_salt,
        "null_construction_spec": null_construction_spec,
    }
    if n_sim_shortfall_warning:
        out["n_sim_shortfall_warning"] = n_sim_shortfall_warning

    # RW: require full null matrix and finite observed stats (fail-closed)
    rw_skipped_reason: Optional[str] = None
    if rw_enabled and null_stats_matrix is not None and null_stats_matrix.shape[0] >= 1:
        if not np.all(np.isfinite(np.asarray(obs_reindexed.values, dtype=float))):
            rw_skipped_reason = "observed stats contain NaN/inf; RW requires finite values"
            out["rw_adjusted_p_values"] = pd.Series(dtype=float)
            out["rw_enabled"] = True
            out["rw_skipped_reason"] = rw_skipped_reason
        else:
            rw_adj = _romano_wolf_stepdown(obs_reindexed, null_stats_matrix)
            out["rw_adjusted_p_values"] = rw_adj
            out["rw_enabled"] = True
            out["rw_method"] = "romano_wolf_stepdown"
            out["rw_null_params"] = {
                "rc_method": cfg.method,
                "rc_seed": cfg.seed,
                "rc_avg_block_length": cfg.avg_block_length,
                "requested_n_sim": requested_n_sim,
                "actual_n_sim": actual_n_sim,
                "seed_root": seed_root_val,
                "seed_version": seed_version,
                "component_salt": component_salt,
                "null_construction_spec": null_construction_spec,
            }
    else:
        out["rw_adjusted_p_values"] = pd.Series(dtype=float)
        out["rw_enabled"] = rw_enabled
        if rw_enabled and (null_stats_matrix is None or null_stats_matrix.shape[0] == 0):
            out["rw_skipped_reason"] = "no null simulations produced; RW requires full null matrix"
    return out


def _block_fixed_bootstrap_indices(
    length: int,
    block_size: int,
    seed: Optional[int],
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Fixed-size block bootstrap indices; same length as input. No global RNG mutation."""
    if length < 1 or block_size < 1:
        return np.array([], dtype=int)
    if rng is None and seed is not None:
        rng = np.random.default_rng(seed)
    if rng is None:
        rng = np.random.default_rng()
    max_start = max(0, length - block_size)
    indices = []
    while len(indices) < length:
        start = int(rng.integers(0, max_start + 1)) if max_start >= 0 else 0
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
    arrs = {h: np.asarray(series_by_hypothesis[h].reindex(common_idx).values, dtype=float) for h in hyps}

    # Deterministic RNG: run_key -> rng_base (canonical SALT_RC_NULL; fold_id=horizon for substreams)
    rng_base: Optional[np.random.Generator] = None
    if cfg.rng is not None:
        rng_base = cfg.rng
    elif cfg.run_key and _rng_for_central is not None:
        rng_base = _rng_for_central(cfg.run_key, SALT_RC_NULL, fold_id=cfg.horizon)

    def _null(b: int) -> np.ndarray:
        if rng_base is not None:
            per_b_seed = int(rng_base.integers(0, 2**63 - 1))
            rng_b = np.random.default_rng(per_b_seed)
            if cfg.method == "stationary":
                idx = _stationary_bootstrap_indices(length, float(cfg.avg_block_length), seed=None, rng=rng_b)
            else:
                idx = _block_fixed_bootstrap_indices(length, cfg.block_size, seed=None, rng=rng_b)
        else:
            seed_b = cfg.seed + b
            if cfg.method == "stationary":
                idx = _stationary_bootstrap_indices(length, float(cfg.avg_block_length), seed_b, rng=None)
            else:
                idx = _block_fixed_bootstrap_indices(length, cfg.block_size, seed_b, rng=None)
        if len(idx) < 2:
            return np.full(len(hyps), np.nan)
        stats = []
        for h in hyps:
            vals = arrs[h][idx]
            stats.append(float(np.nanmean(vals)))
        return np.array(stats)

    return _null
