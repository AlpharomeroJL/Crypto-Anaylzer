"""
Materialize regime run and states to SQLite: regime_runs, regime_states.

Gated by CRYPTO_ANALYZER_ENABLE_REGIMES=1. Caller must apply Phase 3 migrations
(run_migrations_phase3) before calling materialize_regime_run.
See docs/spec/components/schema_plan.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from ..stats.cache_flags import is_cache_disabled
from ..stats.regime_cache import (
    regime_run_exists,
    regime_run_matches_invocation,
    regime_states_rowcount_match,
)
from ..timeutils import now_utc_iso
from .regime_detector import RegimeStateSeries


@dataclass
class RegimeMaterializeConfig:
    """Config for one regime run; used for regime_run_id hash. No timestamps."""

    dataset_id: str
    freq: str
    model: str  # e.g. "threshold_vol_v1"
    feature_config: Optional[Dict[str, Any]] = None  # window sizes, etc.
    model_params: Optional[Dict[str, Any]] = None  # thresholds, hysteresis, etc.

    def to_canonical_dict(self) -> dict:
        """Stable fingerprint for hashing: dataset_id, freq, model, feature_config, model_params. No timestamps."""
        d: Dict[str, Any] = {
            "dataset_id": self.dataset_id,
            "freq": self.freq,
            "model": self.model,
        }
        if self.feature_config is not None:
            d["feature_config"] = dict(sorted((self.feature_config or {}).items()))
        if self.model_params is not None:
            d["model_params"] = dict(sorted((self.model_params or {}).items()))
        return d


def compute_regime_run_id(config: RegimeMaterializeConfig) -> str:
    """Stable regime_run_id from dataset_id + freq + feature_config + model_config. No timestamps (same style as Phase 2 factor_run_id)."""
    canonical = json.dumps(config.to_canonical_dict(), sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"rgm_{h[:16]}"


def materialize_regime_run(
    conn: sqlite3.Connection,
    states: RegimeStateSeries,
    config: RegimeMaterializeConfig,
    *,
    created_at_utc: Optional[str] = None,
    use_cache: bool = True,
    force: bool = False,
) -> str:
    """
    Write regime_runs row and regime_states rows. Idempotent: same regime_run_id
    replaces existing states (delete then insert). Deterministic: ts_utc sorted.
    PR3: If use_cache True and not force and cache not disabled, skip compute when
    regime_run exists and metadata + regime_states count match (return regime_run_id early).

    Call only when CRYPTO_ANALYZER_ENABLE_REGIMES=1. Phase 3 tables must exist
    (call run_migrations_phase3 first). Returns regime_run_id.
    """
    from ._flags import is_regimes_enabled

    if not is_regimes_enabled():
        raise RuntimeError(
            "Regime materialization is gated by CRYPTO_ANALYZER_ENABLE_REGIMES=1. "
            "Set the env var and apply Phase 3 migrations before calling materialize_regime_run."
        )

    regime_run_id = compute_regime_run_id(config)
    created_at_utc = created_at_utc or now_utc_iso()
    params_json = json.dumps(config.model_params) if config.model_params else None

    no_cache = is_cache_disabled(no_cache_flag=(not use_cache) or force)
    if not no_cache:
        row = regime_run_exists(conn, regime_run_id)
        if row is not None:
            if regime_run_matches_invocation(
                row,
                dataset_id=config.dataset_id,
                freq=config.freq,
                model=config.model,
                params_json=params_json,
            ):
                expected_count = len(states.ts_utc) if not states.ts_utc.empty else 0
                if regime_states_rowcount_match(conn, regime_run_id, expected_count):
                    return regime_run_id

    conn.execute(
        """
        INSERT OR REPLACE INTO regime_runs
        (regime_run_id, created_at_utc, dataset_id, freq, model, params_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (regime_run_id, created_at_utc, config.dataset_id, config.freq, config.model, params_json),
    )
    conn.commit()

    # Replace states for this run (idempotent)
    conn.execute("DELETE FROM regime_states WHERE regime_run_id = ?", (regime_run_id,))
    conn.commit()

    if states.ts_utc.empty:
        return regime_run_id

    # Deterministic order: sort by ts_utc
    df = pd.DataFrame(
        {
            "ts_utc": states.ts_utc,
            "regime_label": states.regime_label,
            "regime_prob": states.regime_prob,
        }
    )
    df = df.dropna(subset=["ts_utc"]).sort_values("ts_utc").reset_index(drop=True)

    for _, row in df.iterrows():
        ts = row["ts_utc"]
        if hasattr(ts, "isoformat"):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)
        prob = row["regime_prob"]
        prob_val = float(prob) if pd.notna(prob) else None
        conn.execute(
            """
            INSERT INTO regime_states (regime_run_id, ts_utc, regime_label, regime_prob)
            VALUES (?, ?, ?, ?)
            """,
            (regime_run_id, ts_str, str(row["regime_label"]), prob_val),
        )
    conn.commit()
    return regime_run_id
