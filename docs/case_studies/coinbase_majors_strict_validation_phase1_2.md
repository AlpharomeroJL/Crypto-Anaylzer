# Coinbase Majors Strict Validation (Phase 1.2)

This case study documents a stricter validation-evidence pass on the same Coinbase majors benchmark surface used in Phase 1.1.

It is an evidence-rigor upgrade, not a performance claim.

## 1) What was run

- Command profile:
  - `reportv2 --universe majors --freq 1h --signals clean_momentum,value_vs_beta --portfolio advanced --walk-forward-strict --reality-check --execution-evidence`
- Output root:
  - `reports/reportv2_majors_phase1_2_strict`
- Primary report:
  - `reports/reportv2_majors_phase1_2_strict/research_v2_20260324_0750.md`
- Manifest:
  - `reports/reportv2_majors_phase1_2_strict/manifests/e83d932ca18d5d95.json`

## 2) What changed from Phase 1.1

Phase 1.2 adds stricter evidence artifacts on top of the same majors dataset scope:

- **Strict walk-forward enabled** (`walk_forward_used=true`)
- **Fold-causality attestation produced** (`fold_causality_attestation.json`)
- **Reality Check outputs produced** (summary + null-max distribution)
- **Execution-evidence outputs produced** (execution evidence JSON + capacity curve CSV)

Phase 1.1 did not include these strict artifacts in its output set.

## 3) Why this matters

- It strengthens auditability and reproducibility for majors research claims.
- It improves anti-overfitting and process-governance evidence without changing the architecture boundary.
- It keeps majors and DEX workflows explicitly separate (no pooled semantics).

## 4) What this artifact proves

- A strict majors validation run completed end-to-end on the existing 9-asset universe.
- The run is lineage-anchored to stable identifiers and hashed outputs.
- Fold-causality checks were explicitly attested (train-only fit enforcement, no-future-rows-in-fit, purge/embargo flags all true).
- Reality-check and execution-evidence files are present and reproducible as artifacts.

## 5) What it still does not prove

- It does **not** prove durable alpha.
- It does **not** prove production trading readiness.
- It does **not** prove live execution quality or realized PnL.
- It does **not** merge DEX and majors conclusions.

## 6) Key evidence artifacts and lineage

- Report:
  - `reports/reportv2_majors_phase1_2_strict/research_v2_20260324_0750.md`
- Manifest:
  - `reports/reportv2_majors_phase1_2_strict/manifests/e83d932ca18d5d95.json`
- Fold-causality attestation:
  - `reports/reportv2_majors_phase1_2_strict/fold_causality_attestation.json`
- Validation bundles:
  - `reports/reportv2_majors_phase1_2_strict/csv/validation_bundle_clean_momentum_2e55a7da8b0f98a6.json`
  - `reports/reportv2_majors_phase1_2_strict/csv/validation_bundle_value_vs_beta_2e55a7da8b0f98a6.json`
- Reality Check:
  - `reports/reportv2_majors_phase1_2_strict/csv/reality_check_summary_rcfam_923736c3ee7a35f9.json`
  - `reports/reportv2_majors_phase1_2_strict/csv/reality_check_null_max_rcfam_923736c3ee7a35f9.csv`
- Execution evidence:
  - `reports/reportv2_majors_phase1_2_strict/csv/execution_evidence_clean_momentum_2e55a7da8b0f98a6.json`
  - `reports/reportv2_majors_phase1_2_strict/csv/capacity_curve_clean_momentum_2e55a7da8b0f98a6.csv`

Core identifiers from the Phase 1.2 manifest:

- `run_id`: `e83d932ca18d5d95`
- `run_instance_id`: `2e55a7da8b0f98a6`
- `run_key`: `281180d0d3f3f6e2`
- `dataset_id_v1`: `b57bf0dda072809c`
- `dataset_id_v2`: `ec1d43e36254e830`
- `dataset_hash_scope`: `["venue_bars_1h", "venue_products"]`
- `engine_version`: `93cd3df`

## 7) Main caveats

- Signal breadth is still limited to two majors-native paths (`clean_momentum`, `value_vs_beta`).
- The statistical outcome is not a positive-edge claim (negative Sharpe, non-significant HAC mean-return, RC p-value not significant).
- Break diagnostics flag instability; this is additional caution, not confirmation.
- The milestone is stricter evidence quality, not better returns.

## 8) Recommended next step

Publish this as a Phase 1.2 evidence-upgrade companion to Phase 1.1, then run a longer fixed-window repeat with unchanged strict settings to test evidence stability over time.

Keep majors and DEX tracks separated in all public reporting.
