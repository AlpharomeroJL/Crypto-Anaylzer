# System overview

High-level summary of the Crypto-Analyzer research platform: data lifecycle, pipeline, determinism, statistical correction, feature flags, and promotion workflow. See [master_architecture_spec.md](master_architecture_spec.md) and [components/pipeline_contracts.md](components/pipeline_contracts.md) for full contracts.

---

## Pipeline lifecycle (Mermaid)

```mermaid
flowchart LR
  subgraph In["Ingestion"]
    A[Providers + resilience]
  end
  subgraph Bars["Bars"]
    B[load_snapshots → bars_{freq}]
  end
  subgraph Factors["Factors"]
    C[Rolling OLS / Kalman]
  end
  subgraph Signals["Signals"]
    D[Signal panels]
  end
  subgraph Validation["Validation"]
    E[IC, decay, ValidationBundle]
  end
  subgraph Stats["RC / Bootstrap / Stats"]
    F[Reality Check, BH/BY, deflated Sharpe, PBO]
  end
  subgraph Optim["Optimizer"]
    G[Weights, costs]
  end
  subgraph WF["Walk-forward backtest"]
    H[Stitched OOS]
  end
  subgraph Promotion["Promotion"]
    I[Candidate → evaluate → Accepted]
  end
  subgraph Reporting["Reporting / UI"]
    J[Manifests, registry, Streamlit]
  end

  A --> B
  B --> C
  B --> R[Regime models]
  R --> E
  C --> D
  D --> E
  E --> F
  F --> G
  G --> H
  H --> I
  I --> J
```

Lifecycle: **Ingestion** → **Bars** (materialization) → **Factors** (+ optional Regime models) → **Signals** → **Validation** (IC, decay, ValidationBundle) → **RC / Bootstrap / Stats** (Reality Check, multiple-testing correction, deflated Sharpe, PBO) → **Optimizer** → **Walk-forward backtest** → **Promotion** (candidate creation, evaluation, audit) → **Reporting / UI** (manifests, experiment registry, Streamlit).

---

## Data lifecycle and SQLite as source of truth

- **Single source of truth:** SQLite. All ingested data, bars, experiment registry, and (when opted in) factor runs, regime runs, and promotion state live in SQLite.
- **Ingestion:** Provider responses (spot, DEX) with resilience → `spot_price_snapshots`, `sol_monitor_snapshots`, `provider_health`, universe tables. See `crypto_analyzer/db/migrations.py`.
- **Bars:** Snapshots → resampled OHLCV in `bars_{freq}` (deterministic, idempotent UPSERT). `bars_1D` from `bars_1h`. See `cli/materialize.py`, `crypto_analyzer/data.py`.
- **Factors (optional materialization):** In-memory path (reportv2 default) or materialized `factor_model_runs`, `factor_betas`, `residual_returns` via `factor_materialize.py` and migrations_v2.
- **Regimes (opt-in):** `regime_runs`, `regime_states` and promotion/sweep tables only when Phase 3 migrations are run (run_migrations_phase3, env flag). See [schema_plan.md](components/schema_plan.md).
- **Reporting:** Reads from SQLite + in-memory analytics; writes report markdown, manifests, run_registry.jsonl, and experiment/promotion rows.

---

## Determinism model

| Mechanism | Role |
|-----------|------|
| **dataset_id** | Stable hash from table summaries (row counts, min/max ts). `crypto_analyzer/dataset.py`. Any dataset change invalidates derived caches. |
| **factor_run_id** | Hash of dataset_id + factor config (freq, window, estimator, etc.). Identifies a single factor materialization run. |
| **regime_run_id** | Identifies a single regime materialization run (when regimes enabled). |
| **run_id** | Stable hash of payload (e.g. manifest content). `crypto_analyzer/governance.py` stable_run_id. Used in manifests and artifact paths. |
| **Artifact SHA256** | File hashes for validation bundles and outputs. `crypto_analyzer/artifacts.compute_file_sha256`. Deterministic rerun test compares bundle and manifest bytes. |
| **Deterministic time** | `CRYPTO_ANALYZER_DETERMINISTIC_TIME` (timeutils) fixes timestamps so materialize and reportv2 produce identical outputs on rerun. Required for deterministic rerun test. |
| **Bootstrap / RC seed** | Fixed seed in config → reproducible null distributions and CIs. Seed stored in artifacts. |

---

## Statistical correction stack

- **Deflated Sharpe:** Adjusts for multiple trials; when `--n-trials auto`, effective trials (Neff) from strategy return correlation. `crypto_analyzer/multiple_testing.py`. Artifacts: `n_trials_user`, `n_trials_eff_eigen`, `n_trials_used`, `n_trials_eff_inputs_total`, `n_trials_eff_inputs_used`.
- **PBO proxy + CSCV PBO:** Walk-forward PBO proxy and canonical CSCV PBO (split sampling when combinations exceed max_splits); skip when T &lt; S×4 or J &lt; 2 with reason in artifacts. `crypto_analyzer/multiple_testing.py`.
- **Bootstrap:** Block (fixed-length) and stationary options; seed and method recorded in artifacts. `crypto_analyzer/statistics.py`. Block bootstrap does not assume iid when dependence exists.
- **Reality Check (RC):** Bootstrap-based null for “data snooping”; family_id; reportv2 --reality-check opt-in. `crypto_analyzer/stats/reality_check.py`. RC null cache keyed by family_id + config + dataset + git.
- **Romano–Wolf:** MaxT stepdown on RC null matrix; opt-in via CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1. Outputs `rw_adjusted_p_values` when enabled. `crypto_analyzer/stats/reality_check.py`.
- **Multiple-testing adjustment:** BH/BY FDR; adjusted p-values stored in experiment registry. `crypto_analyzer/multiple_testing_adjuster.py`.
- **HAC mean inference:** Newey–West LRV for mean return/IC; t and p when n ≥ 30; else `hac_skipped_reason` and null t/p. `crypto_analyzer/statistics.py`.
- **Structural break diagnostics:** CUSUM mean-shift (HAC) and sup-Chow single-break scan; `break_diagnostics.json`; skip reasons and `estimated_break_date`. `crypto_analyzer/structural_breaks.py`.
- **Capacity curve:** Participation-based impact (or power-law fallback); required columns `notional_multiplier`, `sharpe_annual`; additive audit columns; `non_monotone_capacity_curve_observed` flag. `crypto_analyzer/execution_cost.py`. Execution evidence JSON matches cost_config to model used.

---

## Feature flags and opt-in behavior

| Flag / option | Effect |
|---------------|--------|
| **CRYPTO_ANALYZER_ENABLE_REGIMES** | Enables regime code path; run_migrations_phase3 and regime materialize / reportv2 --regimes require it. Default: off. |
| **run_migrations_phase3** | Creates regime_runs, regime_states, promotion_candidates, promotion_events, sweep_families, sweep_hypotheses. Not run by default run_migrations(); explicit opt-in. |
| **reportv2 --regimes** | Emits regime-conditioned IC summary and artifacts only when regimes enabled and REGIME_RUN_ID provided. |
| **reportv2 --reality-check** | Runs Reality Check over signal×horizon family; writes RC artifacts and registry metrics. Opt-in. |
| **reportv2 --execution-evidence** | Writes capacity curve and execution_evidence.json for promotion gates. |
| **--no-cache / CRYPTO_ANALYZER_NO_CACHE** | Disables factor, regime, and RC caches. |
| **CRYPTO_ANALYZER_DETERMINISTIC_TIME** | Makes materialize and reportv2 timestamps deterministic for rerun tests. |
| **CRYPTO_ANALYZER_ENABLE_ROMANOWOLF** | Enables Romano–Wolf stepdown; outputs `rw_adjusted_p_values` in RC summary when enabled. |

---

## Promotion workflow summary

- **States:** Exploratory → Candidate → Accepted. Stored in `promotion_candidates` and `promotion_events` (Phase 3 tables).
- **Candidate creation:** CLI `promotion create` (or Streamlit) with run_id, signal_name, horizon, bundle path, optional execution evidence path. Creates a row in promotion_candidates.
- **Evaluation:** `evaluate_candidate` (gating) checks thresholds (IC, t-stat, BH-adjusted p-value, Sharpe, deflated Sharpe, optional regime robustness, Reality Check, execution evidence). Pass/fail and warnings recorded.
- **Audit log:** promotion_events record status changes (e.g. created, evaluated, accepted) with timestamps, thresholds_used, and optional warnings. Evidence JSON stores paths (e.g. validation_bundle_path, execution_evidence_path) for traceability.
- **Gates:** Require RC for accept when candidate belongs to a sweep family (unless override). Require execution evidence for accept when target is candidate/accepted (unless allow_missing_execution_evidence). See `crypto_analyzer/promotion/gating.py` and [phased_execution.md](components/phased_execution.md).
