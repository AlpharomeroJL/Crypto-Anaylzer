# Phase 1 Verification Checklist

Use this checklist to verify Phase 1 (dataset v2, run identity, governance, RW, backfill) before calling Phase 1 complete.

---

## 1. Dataset Hash v2 Is Truly Logical

| Check | How to verify | Test / code |
|-------|----------------|-------------|
| **One row value change → dataset_id_v2 changes** | Change one cell in a hashed table; recompute v2; hash must differ. | `tests/test_dataset_v2.py::test_one_row_value_change_changes_dataset_id_v2` |
| **VACUUM without data change → dataset_id_v2 unchanged** | Run VACUUM; recompute v2; hash must be identical. | `tests/test_dataset_v2.py::test_vacuum_without_data_change_preserves_dataset_id_v2` |
| **Excluded tables do not affect hash** | Insert data into `experiments` (or other excluded table); v2 unchanged. | `tests/test_dataset_v2.py::test_excluded_tables_do_not_affect_hash` |
| **FAST_DEV writes dataset_hash_mode="FAST_DEV"** | Compute v2 with mode=FAST_DEV; metadata has `dataset_hash_mode="FAST_DEV"`. | `tests/test_dataset_v2.py::test_fast_dev_writes_dataset_hash_mode` |
| **FAST_DEV blocks promotion** | Eligibility with dataset_hash_mode=FAST_DEV → blockers. | `tests/test_promotion_gating.py::test_evaluate_eligibility_blocks_when_dataset_hash_mode_not_strict` |

If any of these fail, you still have “correctness theater.”

---

## 2. run_key Is Actually Deterministic

| Check | How to verify | Test / code |
|-------|----------------|-------------|
| **Same config + same dataset, different timestamps → run_key identical** | Payloads that differ only in `ts_utc` / `created_utc` → same run_key. | `tests/test_run_identity.py::test_run_key_excludes_timestamps`, `test_run_key_identical_for_same_semantic_payload` |
| **run_instance_id differs** | Same semantic payload, different instance id passed to `build_run_identity` → same run_key, different run_instance_id. | `tests/test_run_identity.py::test_run_instance_id_can_differ` |
| **Change factor / engine_version / dataset_id_v2 → run_key changes** | Alter any of these in the payload; run_key must change. | `tests/test_run_identity.py::test_run_key_changes_with_*` |

**Manual (optional):** Run reportv2 twice with different timestamps, same config + dataset; compare manifests: `run_instance_id` should differ, `run_key` must be identical. Then change a factor or version and confirm `run_key` changes.

---

## 3. Governance Is Structurally Non-Bypassable

| Check | How to verify | Test / code |
|-------|----------------|-------------|
| **Raw UPDATE status='candidate' without eligibility_report_id fails** | Execute `UPDATE promotion_candidates SET status='candidate' WHERE candidate_id=...`; must raise (trigger). | `tests/test_migrations_phase3.py::test_trigger_blocks_direct_update_to_candidate_without_eligibility_report` |
| **update_status('candidate'/'accepted') raises in Python** | Call `update_status(conn, id, "accepted", ...)`; must raise ValueError. | `tests/test_promotion_store.py::test_update_status_raises_for_candidate_accepted` |
| **Streamlit: candidate/accepted go through eligibility** | In app, “Update status” to candidate/accepted uses `evaluate_and_record(..., target_status=new_status)` with bundle path from evidence; no direct `update_status` for those. | `cli/app.py`: candidate/accepted branch calls `evaluate_and_record(..., target_status=new_status)` only. |
| **CLI: candidate/accepted go through eligibility** | Promotion CLI uses `evaluate_and_record`; no code path sets candidate/accepted via `update_status`. | `cli/promotion.py`: uses `evaluate_and_record`. |

If any code path can set candidate/accepted without eligibility evidence, Phase 1 is not done.

---

## 4. RW Path Actually Works

| Check | How to verify | Test / code |
|-------|----------------|-------------|
| **Set CRYPTO_ANALYZER_ENABLE_ROMANOWOLF=1 → run_reality_check does not raise** | Env=1, call `run_reality_check` with small observed + null generator; no exception. | `tests/test_reality_check_rw.py::test_run_reality_check_with_rw_env_does_not_raise` |
| **rw_adjusted_p_values: count, [0,1], non-empty, aligned to hypothesis index** | With RW enabled, result has `rw_adjusted_p_values` same length as hypotheses, values in [0,1], index aligned. | `tests/test_reality_check_rw.py::test_rw_adjusted_p_values_match_hypothesis_count_and_in_range` |
| **Gatekeeper: RW enabled + missing outputs → blocks** | Bundle with `rw_enabled=True` and no `rw_adjusted_p_values` → eligibility blockers. | `tests/test_promotion_gating.py::test_evaluate_eligibility_blocks_when_rw_enabled_but_rw_adjusted_p_values_missing` |
| **Gatekeeper: RW enabled + valid p-values → allowed** | Bundle with `rw_enabled=True` and valid `rw_adjusted_p_values` in [0,1] → eligibility passes. | `tests/test_promotion_gating.py::test_evaluate_eligibility_passes_with_rw_enabled_and_valid_p_values` |

**Manual (optional):** Enable RW, run pipeline, then try promoting: missing RW outputs should be blocked; valid RW + other checks pass should allow promotion.

---

## 5. Backfill Works

| Check | How to verify | Test / code |
|-------|----------------|-------------|
| **backfill_dataset_id_v2 populates dataset_id_v2** | Run backfill on DB with in-scope table; `dataset_metadata` has `dataset_id_v2`. | `tests/test_backfill_dataset_v2.py::test_backfill_populates_dataset_metadata_and_experiments` |
| **dataset_hash_algo and mode recorded** | After backfill, `dataset_metadata` has `dataset_hash_algo` and `dataset_hash_mode` (STRICT). | Same test. |
| **Old experiments rows get dataset_id_v2** | DB with existing experiments rows (dataset_id_v2 NULL); after backfill, those rows updated with v2/algo/mode. | Same test. |

**Manual (optional):** Run `backfill_dataset_id_v2` on an existing DB; confirm `dataset_metadata` and `experiments.dataset_id_v2` populated; old runs become promotion-eligible when STRICT.

---

## Commands to Run

```powershell
.venv\Scripts\activate
python -m pytest tests/test_dataset_v2.py tests/test_run_identity.py tests/test_reality_check_rw.py tests/test_backfill_dataset_v2.py tests/test_promotion_gating.py tests/test_migrations_phase3.py tests/test_promotion_store.py -v --tb=short
```

Expect all listed tests to pass. Then run the full promotion + phase3 suite to confirm nothing else regressed.
