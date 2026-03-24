# Coinbase Majors Methodology Correction (Phase 1.4)

This case study documents a research-correctness upgrade on the majors/CEX track.

Phase 1.4 is not an alpha claim. It is a methodology-correction pass focused on:
- causal portfolio application (lagged execution),
- more robust cross-sectional neutralization,
- cleaner majors-native factor preference,
- rerunning the same strict validation stack.

## 1) What was run

- Strict majors rerun (same strict stack as Phase 1.3):
  - `python -m crypto_analyzer reportv2 --universe majors --freq 1h --signals clean_momentum,value_vs_beta --portfolio advanced --walk-forward-strict --reality-check --execution-evidence --out-dir reports/reportv2_majors_phase1_4_signal_quality_strict`
- Primary output root:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict`
- Primary report:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/research_v2_20260324_0949.md`

## 2) What changed from Phase 1.3

Relative to `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict`:

- **Lagged portfolio application correction**
  - Portfolio returns/turnover are now computed from lagged weights (`weights_df.shift(1)`), reducing same-bar evaluation risk.
- **Neutralization robustness improvement**
  - Cross-sectional neutralization now uses only finite signal/exposure rows (no exposure NaN->0 imputation during OLS residualization).
- **Majors-native factor preference improvement**
  - Factor-return routing now prioritizes majors-native `BTC-USD` before `BTC_spot` fallback when available.
- **Strict rerun completed end-to-end**
  - Fresh manifest/attestation/validation/reality-check/execution-evidence artifacts produced under a new run identity.

## 3) Why this matters

- It improves causal correctness in the research PnL path.
- It makes signal residualization behavior more statistically defensible on a small majors panel.
- It keeps factor semantics aligned with majors data where possible.
- It strengthens trust in negative/weak outcomes by improving method quality rather than relaxing validation.

## 4) What this artifact proves

- A strict Phase 1.4 rerun completed with traceable lineage:
  - `run_id`: `af51f0b73963cb13`
  - `run_instance_id`: `43e78b82501ae21a`
  - `run_key`: `344d6d39d4a1d0cb`
  - `dataset_id_v2`: `6324b3b258ec05d0`
- Strict majors dataset scope remains explicit:
  - `dataset_hash_scope`: `["venue_bars_1h", "venue_products"]`
- Fold-causality attestation exists and reports enforcement checks true:
  - `train_only_fit_enforced`, `no_future_rows_in_fit`, `purge_applied`, `embargo_applied`
- Two majors-compatible signal paths remained active with separate validation bundles:
  - `clean_momentum`
  - `value_vs_beta`

## 5) What it still does not prove

- It does **not** prove durable alpha.
- It does **not** prove production trading readiness.
- It does **not** prove live execution quality or realized PnL.
- It does **not** imply transferability to DEX conclusions.

## 6) Key evidence artifacts and lineage

- Report:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/research_v2_20260324_0949.md`
- Manifest:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/manifests/af51f0b73963cb13.json`
- Fold-causality attestation:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/fold_causality_attestation.json`
- Validation bundles:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/validation_bundle_clean_momentum_43e78b82501ae21a.json`
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/validation_bundle_value_vs_beta_43e78b82501ae21a.json`
- Reality Check:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/reality_check_summary_rcfam_e4445426efc86abf.json`
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/reality_check_null_max_rcfam_e4445426efc86abf.csv`
- Execution evidence:
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/execution_evidence_clean_momentum_43e78b82501ae21a.json`
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/capacity_curve_clean_momentum_43e78b82501ae21a.csv`
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/execution_evidence_value_vs_beta_43e78b82501ae21a.json`
  - `reports/reportv2_majors_phase1_4_signal_quality_strict/csv/capacity_curve_value_vs_beta_43e78b82501ae21a.csv`
- Code-level methodology corrections:
  - `crypto_analyzer/cli/reportv2.py`
  - `crypto_analyzer/signals_xs.py`
  - `crypto_analyzer/data/__init__.py`
- Phase 1.3 comparator:
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/research_v2_20260324_0830.md`
  - `reports/reportv2_majors_phase1_3_ws_sigbreadth_strict/stats_overview.json`

## 7) Main caveats

- Results remained weak/mixed in Phase 1.4:
  - both signal portfolios still show negative Sharpe in this run,
  - HAC mean return remains non-significant,
  - Reality Check remains non-significant.
- Orthogonalization before/after correlation remained very similar in this panel.
- This is a methodology-correction milestone, not a performance milestone.

## 8) Recommended next step

- Keep the corrected methodology fixed and run a pre-registered out-of-window repeat on majors-only data.
- Evaluate whether robustness improvements persist without changing validation strictness.
- Publish only credibility-focused language until statistical/return evidence materially improves.
