"""
Walk-forward runner with strict fold causality: fit on train only, apply to test, build attestation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Union

import pandas as pd

from crypto_analyzer.rng import SALT_FOLD_SPLITS, seed_root

from .attestation import build_fold_causality_attestation
from .folds import SplitPlan, slice_df_by_fold
from .guards import CausalityGuard
from .transforms import (
    ExogenousTransform,
    TrainableTransform,
    TrainState,
)


@dataclass
class RunnerConfig:
    """Config for run_walk_forward_with_causality."""

    ts_column: str = "ts_utc"
    run_key: str = ""
    dataset_id_v2: str = ""
    engine_version: str = ""
    config_version: str = ""
    seed_version: int = 1


def _is_trainable(t: Any) -> bool:
    return (
        hasattr(t, "fit")
        and hasattr(t, "transform")
        and callable(getattr(t, "fit"))
        and callable(getattr(t, "transform"))
    )


def run_walk_forward_with_causality(
    data: pd.DataFrame,
    split_plan: SplitPlan,
    transforms: List[tuple[str, Union[ExogenousTransform, TrainableTransform]]],
    scorer: Callable[[pd.DataFrame], Dict[str, Any]],
    cfg: RunnerConfig,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    For each fold: slice train_df, test_df; fit trainables on train only (with guard);
    apply exogenous + trained states to test; score test only. Return per-fold results
    and fold_causality attestation.
    """
    ts_col = cfg.ts_column
    per_fold_results: List[Dict[str, Any]] = []
    transforms_used: List[Dict[str, Any]] = []
    for name, t in transforms:
        if _is_trainable(t):
            transforms_used.append({"name": name, "kind": "trainable"})
        else:
            transforms_used.append({"name": name, "kind": "exogenous"})

    purge_applied = any(f.purge_gap_bars > 0 for f in split_plan.folds)
    embargo_applied = any(f.embargo_bars > 0 for f in split_plan.folds)
    no_future_violations = True

    for fold in split_plan.folds:
        train_df, test_df = slice_df_by_fold(data, fold, ts_col)
        if train_df.empty or test_df.empty:
            continue
        guard = CausalityGuard(fold, ts_column=ts_col)
        states: Dict[str, TrainState] = {}
        for name, t in transforms:
            if _is_trainable(t):
                guard.assert_train_bounds(train_df)
                try:
                    state = t.fit(train_df)
                    states[name] = state
                except AssertionError:
                    no_future_violations = False
                    raise
            else:
                pass
        test_transformed = test_df.copy()
        for name, t in transforms:
            if _is_trainable(t):
                state = states.get(name)
                if state is not None:
                    test_transformed = t.transform(test_transformed, state)
            else:
                test_transformed = t.transform(test_transformed)
        metrics = scorer(test_transformed)
        per_fold_results.append(
            {
                "fold_id": fold.fold_id,
                "train_start_ts": str(fold.train_start_ts),
                "train_end_ts": str(fold.train_end_ts),
                "test_start_ts": str(fold.test_start_ts),
                "test_end_ts": str(fold.test_end_ts),
                "metrics": metrics,
            }
        )

    seed_root_val = None
    seed_salt = None
    if cfg.run_key:
        seed_root_val = seed_root(cfg.run_key, salt=SALT_FOLD_SPLITS, version=cfg.seed_version)
        seed_salt = SALT_FOLD_SPLITS

    attestation = build_fold_causality_attestation(
        run_key=cfg.run_key,
        dataset_id_v2=cfg.dataset_id_v2,
        split_plan=split_plan,
        transforms_used=transforms_used,
        checks={
            "train_only_fit_enforced": True,
            "purge_applied": purge_applied or (split_plan.folds and split_plan.folds[0].purge_gap_bars >= 0),
            "embargo_applied": embargo_applied or (split_plan.folds and split_plan.folds[0].embargo_bars >= 0),
            "no_future_rows_in_fit": no_future_violations,
        },
        engine_version=cfg.engine_version,
        config_version=cfg.config_version,
        seed_root=seed_root_val,
        seed_salt=seed_salt,
        seed_version=cfg.seed_version,
    )
    return per_fold_results, attestation
