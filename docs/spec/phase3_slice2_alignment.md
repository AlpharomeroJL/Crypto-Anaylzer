# Phase 3 Slice 2: Regime-conditioned validation and promotion hooks — STEP 0 alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [testing_acceptance.md](components/testing_acceptance.md), [risk_audit.md](components/risk_audit.md), [research_repo_mapping.md](components/research_repo_mapping.md), [phased_execution.md](components/phased_execution.md).

## A) Where regime-conditioned validation is defined

- **testing_acceptance.md:** Minimum evidence thresholds (Mean IC ≥ 0.02, IC t-stat ≥ 2.5, BH ≤ 0.05, Net Sharpe ≥ 1.0, bootstrap CI lower ≥ 0, deflated Sharpe z ≥ 1.0); walk-forward leakage (factor/regime fitted only on train).
- **risk_audit.md:** Regime modeling leakage — no smoothing in test; only filtering; require OOS persistence for regime-gated alpha.
- **research_repo_mapping.md:** "Regime-conditioned metrics" / "Regime-conditioned IC differences persist OOS" under Statistical regime modeling.

## B) Join policy (timestamp alignment + decision/return convention)

- **Convention:** Decisions at time t affect returns starting t+1. Regime state at t may be used for decision at t if regime at t is computed from information ≤ t (filter-only).
- **Join policy (exact):** Join frame (signals/returns/IC index) to regime_states on **ts_utc**. For each row with timestamp t we attach regime_label at t only. No use of regime at t+1 for row t (leakage-safe).
- **decision_lag_bars:** Document only; exact join means we attach regime at t to observation at t. If in future we supported "decision at t uses regime at t−lag", that would be a separate join (e.g. shift regime index by lag). Default 1: regime at t is the one available when deciding at t for execution at t+1.
- **Missing regime:** Timestamps with no regime state get regime_label = "unknown"; exclude from regime-conditioned summaries by default; report coverage (% available, % unknown, distribution).

## C) Artifacts to produce (filenames, columns, referenced in bundle)

| Artifact | Filename pattern | Columns / content | Referenced in bundle |
|----------|------------------|------------------|----------------------|
| Regime coverage | `regime_coverage_{run_id}.json` | pct_available, pct_unknown, n_ts, n_with_regime, n_unknown, regime_distribution (counts per label) | meta.regime_coverage + optional path |
| IC by regime | `ic_by_regime_{signal}_{run_id}.csv` | regime, horizon (if multi), mean_ic, std_ic, n_bars, t_stat | meta.regime_artifacts.ic_by_regime_path |
| IC decay by regime | `ic_decay_by_regime_{signal}_{run_id}.csv` | regime, horizon_bars, mean_ic, std_ic, n_obs | meta.regime_artifacts.ic_decay_by_regime_path |
| Portfolio by regime | `portfolio_by_regime_{signal}_{run_id}.csv` | regime, sharpe, cagr_proxy, max_dd, hit_rate, n | optional |

ValidationBundle meta extension (optional, no breaking change): regime_run_id, regime_join_policy ("exact"), regime_coverage (dict), regime_artifacts (dict of relative paths).
