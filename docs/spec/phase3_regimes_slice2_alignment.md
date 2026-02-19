# Phase 3 Slice 2: Regime-conditioned validation + promotion hooks — alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [testing_acceptance.md](components/testing_acceptance.md), [risk_audit.md](components/risk_audit.md), [research_repo_mapping.md](components/research_repo_mapping.md), [phased_execution.md](components/phased_execution.md), [pipeline_contracts.md](components/pipeline_contracts.md).

## a) Join policy and decision_lag_bars

- **Join policy:** `exact` only. Join on **ts_utc**: for each row with timestamp t we attach regime_label at t. No use of regime at t+1 for row t (leakage-safe). Optional `asof` is not implemented in Slice 2.
- **decision_lag_bars:** Repo convention: decisions at t apply to returns from t+1. With exact join, regime at t is the label available when deciding at t (for execution at t+1). Default 1; stored in meta for reproducibility only; join does not shift regime index.
- **Missing regime:** Timestamps with no regime state get `regime_label = "unknown"`. Exclude "unknown" from regime-conditioned IC/decay summaries by default; report coverage (pct_available, pct_unknown, regime distribution).

## b) Artifact filenames and schemas (columns)

| Artifact | Filename | Columns / schema |
|----------|----------|-------------------|
| Regime coverage | `regime_coverage_{run_id}.json` | `pct_available`, `pct_unknown`, `n_ts`, `n_with_regime`, `n_unknown`, `regime_distribution` (dict label -> count) |
| IC summary by regime | `ic_summary_by_regime_{signal}_{run_id}.csv` | `regime`, `horizon`, `mean_ic`, `std_ic`, `n_bars`, `t_stat` |
| IC decay by regime | `ic_decay_by_regime_{signal}_{run_id}.csv` | `regime`, `horizon_bars`, `mean_ic`, `std_ic`, `n_obs` |
| Portfolio by regime (optional) | `portfolio_by_regime_{signal}_{run_id}.csv` | `regime`, `sharpe`, `cagr_proxy`, `max_dd`, `hit_rate`, `n` |

ValidationBundle meta extension: `regime_run_id`, `regime_join_policy` ("exact"), `decision_lag_bars` (1), `regime_coverage_summary` (dict). New optional path fields: `ic_summary_by_regime_path`, `ic_decay_by_regime_path`, `regime_coverage_path`.

## c) Thresholds and gating (from testing_acceptance.md)

**Minimum evidence thresholds (explicit):**
- Mean Spearman IC ≥ **0.02** over ≥ **200** timestamps with ≥ **10** assets per timestamp
- IC t-stat ≥ **2.5**
- BH-adjusted p-value ≤ **0.05**
- Net annualized Sharpe ≥ **1.0** after costs; bootstrap Sharpe CI lower ≥ **0.0**
- Deflated Sharpe z-score ≥ **1.0** (n_trials = family size)

**Promotion gating (Slice 2):**
- `ThresholdConfig`: ic_mean_min=0.02, tstat_min=2.5, p_value_max=0.05, deflated_sharpe_min=1.0, require_regime_robustness=False by default.
- When `require_regime_robustness=True`: optional `worst_regime_ic_mean_min`; reject if any regime’s mean IC below that (or if fewer than K regimes have enough samples; K default 2, documented).
- `evaluate_candidate(bundle, thresholds, regime_summary_df=None)` → `PromotionDecision` (status, reasons, metrics_snapshot). Deterministic; no UI wiring.
