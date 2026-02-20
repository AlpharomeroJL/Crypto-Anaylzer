"""
Research pipeline: load data → signals → IC/decay/coverage → promotion → artifact bundle.
Deterministic outputs tagged with run_id, hypothesis_id, family_id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from crypto_analyzer.alpha_research import (
    compute_forward_returns,
    ic_decay,
    ic_summary,
    information_coefficient,
    signal_momentum_24h,
)
from crypto_analyzer.artifacts import (
    compute_file_sha256,
    ensure_dir,
    write_df_csv_stable,
    write_json_sorted,
)
from crypto_analyzer.governance import stable_run_id
from crypto_analyzer.promotion.gating import (
    PromotionDecision,
    ThresholdConfig,
    evaluate_candidate,
)
from crypto_analyzer.stats.reality_check import (
    RealityCheckConfig,
    make_null_generator_stationary,
    run_reality_check,
)
from crypto_analyzer.validation_bundle import ValidationBundle


@dataclass
class ResearchPipelineResult:
    """Minimal dataclass for pipeline outputs: metrics, decision, ids, artifact paths."""

    run_id: str
    hypothesis_id: str
    family_id: str
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)
    decision: PromotionDecision = field(default_factory=lambda: PromotionDecision(status="exploratory", reasons=[]))
    artifact_paths: Dict[str, str] = field(default_factory=dict)
    bundle_dir: str = ""


def _synthetic_returns(n_bars: int = 100, n_assets: int = 3, seed: int = 42) -> pd.DataFrame:
    """Small synthetic log-returns for demo; deterministic given seed."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_bars, freq="h")
    cols = [f"A{i}" for i in range(n_assets)]
    data = rng.standard_normal((n_bars, n_assets)).astype(np.float64) * 0.01
    return pd.DataFrame(data, index=idx, columns=cols)


def _stable_run_id_from_pipeline(
    hypothesis_id: str,
    family_id: str,
    config_digest: Dict[str, Any],
) -> str:
    """Stable run_id from hypothesis_id, family_id, and config digest (sorted keys, no timestamps)."""
    payload = {
        "hypothesis_id": hypothesis_id,
        "family_id": family_id,
        "config": json.dumps(config_digest, sort_keys=True, default=str),
    }
    return stable_run_id(payload)


def _config_digest(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract deterministic fields for run_id hashing (no paths, no mutable refs)."""
    out: Dict[str, Any] = {}
    for k in sorted(config.keys()):
        v = config[k]
        if k in ("out_dir", "output_dir"):
            continue
        if isinstance(v, (dict, list)):
            out[k] = json.loads(json.dumps(v, sort_keys=True, default=str))
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out


def run_research_pipeline(
    config: Dict[str, Any],
    hypothesis_id: str,
    family_id: str,
    *,
    run_id: Optional[str] = None,
    enable_reality_check: bool = False,
) -> ResearchPipelineResult:
    """
    End-to-end demo pipeline: load data → construct signals → IC/decay/coverage
    → apply promotion thresholds → optional reality-check → write artifact bundle.

    Determinism: stable sorting, sort_keys JSON, stable run_id when not provided.
    Bundle directory contains manifest.json, metrics files, and hashes.json.

    config: dict with at least out_dir, dataset_id, signal_name, freq, horizons; optional seed, thresholds.
    """
    out_dir = Path(config.get("out_dir", "artifacts/research"))
    dataset_id = str(config.get("dataset_id", "demo"))
    signal_name = str(config.get("signal_name", "momentum_24h"))
    freq = str(config.get("freq", "1h"))
    horizons: List[int] = sorted(config.get("horizons", [1, 4]))
    seed = int(config.get("seed", 42))
    thresholds_dict = config.get("thresholds")
    if isinstance(thresholds_dict, ThresholdConfig):
        thresholds = thresholds_dict
    else:
        thresholds = ThresholdConfig(**(thresholds_dict or {}))

    # Stable run_id
    if run_id is None:
        run_id = _stable_run_id_from_pipeline(hypothesis_id, family_id, _config_digest(config))

    # 1) Load data (synthetic for demo)
    n_bars = int(config.get("n_bars", 100))
    n_assets = int(config.get("n_assets", 3))
    returns_df = _synthetic_returns(n_bars=n_bars, n_assets=n_assets, seed=seed)

    # 2) Construct signal
    signal_df = signal_momentum_24h(returns_df, freq)
    if signal_df.empty or signal_df.isna().all().all():
        return ResearchPipelineResult(
            run_id=run_id,
            hypothesis_id=hypothesis_id,
            family_id=family_id,
            metrics_snapshot={},
            decision=PromotionDecision(status="rejected", reasons=["signal empty or all NaN"]),
            bundle_dir="",
        )

    # 3) IC / decay (stable horizon order)
    ic_series_by_horizon: Dict[int, pd.Series] = {}
    ic_summary_by_horizon: Dict[int, Dict[str, float]] = {}
    for h in horizons:
        if h < 1:
            continue
        fwd = compute_forward_returns(returns_df, h)
        ic_ts = information_coefficient(signal_df, fwd, method="spearman")
        ic_series_by_horizon[h] = ic_ts.sort_index()
        ic_summary_by_horizon[h] = ic_summary(ic_ts)

    decay_df = ic_decay(signal_df, returns_df, horizons, method="spearman")
    ic_decay_table: List[Dict[str, Any]] = (
        decay_df.sort_values("horizon_bars").to_dict(orient="records") if not decay_df.empty else []
    )
    for row in ic_decay_table:
        for k, v in list(row.items()):
            if isinstance(v, (np.floating, np.integer)):
                row[k] = float(v) if np.issubdtype(type(v), np.floating) else int(v)

    # 4) Regime coverage: optional; demo uses no regimes -> coverage placeholder
    regime_coverage_summary: Dict[str, Any] = {
        "pct_available": 0.0,
        "pct_unknown": 1.0,
        "n_ts": len(returns_df),
        "n_with_regime": 0,
        "n_unknown": len(returns_df),
        "regime_distribution": {},
    }

    # 5) Optional reality check
    rc_summary: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "family_id": family_id,
        "regime_coverage_summary": regime_coverage_summary,
    }
    if enable_reality_check and ic_series_by_horizon:
        primary_h = horizons[0]
        ic_series = ic_series_by_horizon[primary_h]
        observed_stats = pd.Series({hypothesis_id: float(ic_series.mean())}).sort_index()
        series_by_hyp = {hypothesis_id: ic_series.reindex(returns_df.index).dropna()}
        rc_cfg = RealityCheckConfig(
            metric="mean_ic",
            horizon=primary_h,
            n_sim=int(config.get("rc_n_sim", 50)),
            seed=seed + 1,
        )
        null_gen = make_null_generator_stationary(series_by_hyp, rc_cfg)
        rc_summary = run_reality_check(observed_stats, null_gen, rc_cfg)
        meta["rc_p_value"] = rc_summary.get("rc_p_value")
        meta["rc_observed_max"] = rc_summary.get("observed_max")

    # 6) Build ValidationBundle
    bundle = ValidationBundle(
        run_id=run_id,
        dataset_id=dataset_id,
        signal_name=signal_name,
        freq=freq,
        horizons=horizons,
        ic_summary_by_horizon=ic_summary_by_horizon,
        ic_decay_table=ic_decay_table,
        meta=meta,
    )

    # 7) Promotion decision
    regime_summary_df: Optional[pd.DataFrame] = None
    decision = evaluate_candidate(bundle, thresholds, regime_summary_df=regime_summary_df, rc_summary=rc_summary)

    # 8) Write artifact bundle (deterministic)
    bundle_dir = out_dir / run_id
    ensure_dir(bundle_dir)
    artifact_paths: Dict[str, str] = {}

    # manifest
    manifest = {
        "run_id": run_id,
        "hypothesis_id": hypothesis_id,
        "family_id": family_id,
        "dataset_id": dataset_id,
        "signal_name": signal_name,
        "freq": freq,
        "horizons": horizons,
        "decision_status": decision.status,
        "decision_reasons": decision.reasons,
        "metrics_snapshot": decision.metrics_snapshot,
        "artifact_paths": {},
    }
    manifest_path = bundle_dir / "manifest.json"
    write_json_sorted(manifest, manifest_path)
    artifact_paths["manifest"] = str(manifest_path)

    # metrics (IC summary)
    metrics_path = bundle_dir / "metrics_ic.json"
    write_json_sorted(
        {str(k): v for k, v in sorted(ic_summary_by_horizon.items())},
        metrics_path,
    )
    artifact_paths["metrics_ic"] = str(metrics_path)

    # decay CSV
    decay_path: Optional[Path] = None
    if not decay_df.empty:
        decay_path = bundle_dir / "ic_decay.csv"
        write_df_csv_stable(decay_df.sort_values("horizon_bars").sort_index(axis=1), decay_path)
        artifact_paths["ic_decay"] = str(decay_path)

    # RC summary (if run)
    rc_path: Optional[Path] = None
    if rc_summary is not None:
        rc_out = {k: v for k, v in rc_summary.items() if k != "null_max_distribution"}
        if "null_max_distribution" in rc_summary:
            arr = rc_summary["null_max_distribution"]
            rc_out["null_max_distribution_len"] = len(arr) if hasattr(arr, "__len__") else 0
        rc_path = bundle_dir / "rc_summary.json"
        write_json_sorted(rc_out, rc_path)
        artifact_paths["rc_summary"] = str(rc_path)

    # hashes (relative paths, sorted) — all written artifacts except hashes.json
    paths_to_hash: List[Path] = [manifest_path, metrics_path]
    if decay_path is not None:
        paths_to_hash.append(decay_path)
    if rc_path is not None:
        paths_to_hash.append(rc_path)
    hashes_content: Dict[str, str] = {}
    for p in paths_to_hash:
        rel = p.name
        hashes_content[rel] = compute_file_sha256(p)
    hashes_path = bundle_dir / "hashes.json"
    write_json_sorted(hashes_content, hashes_path)
    artifact_paths["hashes"] = str(hashes_path)

    return ResearchPipelineResult(
        run_id=run_id,
        hypothesis_id=hypothesis_id,
        family_id=family_id,
        metrics_snapshot=decision.metrics_snapshot,
        decision=decision,
        artifact_paths=artifact_paths,
        bundle_dir=str(bundle_dir),
    )
