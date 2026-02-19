# Phase 3 Regimes Slice — STEP 0 Spec Alignment

**Canonical spec:** [master_architecture_spec.md](master_architecture_spec.md), [schema_plan.md](components/schema_plan.md), [interfaces.md](components/interfaces.md), [testing_acceptance.md](components/testing_acceptance.md), [risk_audit.md](components/risk_audit.md), [phased_execution.md](components/phased_execution.md).

## A) Regime tables (schema_plan.md)

**regime_runs**
- regime_run_id TEXT PRIMARY KEY
- created_at_utc TEXT NOT NULL
- dataset_id TEXT NOT NULL
- freq TEXT NOT NULL
- model TEXT NOT NULL ("heuristic_v1" | "garch" | "markov_switching")
- params_json TEXT
- INDEX idx_regime_runs_dataset_freq ON regime_runs(dataset_id, freq)

**regime_states**
- regime_run_id TEXT NOT NULL (FK)
- ts_utc TEXT NOT NULL
- regime_label TEXT NOT NULL
- regime_prob REAL (nullable)
- PRIMARY KEY (regime_run_id, ts_utc)
- INDEX idx_regime_states_ts ON regime_states(regime_run_id, ts_utc)

## B) RegimeDetector interface (interfaces.md)

- **Inputs:** market_series / train_data DataFrame (features); fit_window (train-only); inference_mode "filter" (no smoothing in test).
- **Outputs:** regime_states: ts_utc, label, prob (Series or DataFrame).
- **Signatures:** fit(train_data, config) -> RegimeModel; predict(test_data, model, mode="filter") -> RegimeStateSeries.
- **Error handling:** Raise if mode="smooth" in test or train/test overlap.
- **Determinism:** Fixed seeds, stable ordering, strict fit/predict separation.

## C) Required tests (testing_acceptance.md + risk_audit.md)

- **RegimeDetector causality:** Fit on train, predict on test; no use of test timestamps in fitted params; probabilities sum to 1.0 ± 1e-6 per timestamp.
- **Filter-only:** mode="smooth" must raise in validation/backtest context (or be explicitly rejected).
- **No leakage:** Synthetic feature where future values are informative; regime at t must not use t+1.
- **Walk-forward:** Factor/regime models fitted only on train; signals for test without future within test.

## D) Pipeline integration (dependency graph)

Bars -> RegimeFeatures (regime_features.py) -> RegimeDetector (fit on train, predict filter on test) -> RegimeStates -> Materialize (regime_runs / regime_states) -> Validation/Reporting (optional regime-conditioned IC/summaries).
