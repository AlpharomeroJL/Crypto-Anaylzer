# Versioning and release

**Purpose:** SemVer rules, config versioning, model artifact versioning, and reproducibility metadata stored in DB.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Versioning strategy

**Semantic versioning rules (engine)**  
- **MAJOR**: schema changes that require data rebuild or break DB compatibility (e.g., changing primary keys on bars tables).  
- **MINOR**: new pipeline stages or optional models (Kalman beta, new regime detector) that are additive and gated by config.  
- **PATCH**: bug fixes, including leakage fixes that do not change public interfaces (or do so backward-compatibly).

**Config versioning**  
- Add config_version to config.yaml and store it in experiments.config_hash + new experiments.config_version.  
- Any breaking behavior change requires bumping config_version, even on a MINOR engine bump.

**Model artifact versioning**  
- Every materialized model output (factor_run_id, regime_run_id, sweep_run_id) is a stable hash of:  
  - dataset_id  
  - model config JSON (sorted keys)  
  - git commit  
- This guarantees you can regenerate or detect drift.

**Repro metadata stored in DB (minimum)**  
- Already present: git_commit, spec_version, config_hash, env_fingerprint, dataset_id, params_json.  
- Add: engine_version, config_version, and (optionally) factor_run_id / regime_run_id foreign keys when those become first-class.
