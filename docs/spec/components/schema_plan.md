# Schema evolution plan

**Purpose:** Proposed schema additions (tables/columns, PK/FK, indexes, example rows) and migration strategy.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Database schema changes

Current DB schema is created idempotently (core ingestion tables + provenance + universe + provider health). Bars tables are created on materialization with a fixed schema and primary key. Experiment registry already exists as SQLite tables (experiments, experiment_metrics, experiment_artifacts).

Phase 3 tables (regime_runs, regime_states, promotion_candidates, promotion_events, sweep_families, sweep_hypotheses) are created only by run_migrations_phase3; opt-in (e.g. CRYPTO_ANALYZER_ENABLE_REGIMES and explicit phase3 migration call). Core run_migrations does not apply phase3.

Below is a schema evolution plan that adds **(a)** versioned migrations, and **(b)** optional materialized research outputs needed for causal regime/cost/factor extensions.

---

## Proposed schema additions

### Table: schema_migrations (tracks applied migrations; enables deterministic upgrades)

**Columns**
- version INTEGER PRIMARY KEY
- name TEXT NOT NULL
- applied_at_utc TEXT NOT NULL
- git_commit TEXT

**Indexes:** implicit PK

**Example row**
- (7, "2026_02_add_factor_runs", "2026-02-19T18:30:00Z", "3cdd8d6c")

---

### Table: factor_model_runs (defines a reproducible factor materialization run)

**Columns**
- factor_run_id TEXT PRIMARY KEY (stable hash of config + dataset_id)
- created_at_utc TEXT NOT NULL
- dataset_id TEXT NOT NULL (align with experiments.dataset_id)
- freq TEXT NOT NULL
- window_bars INTEGER NOT NULL
- min_obs INTEGER NOT NULL
- factors_json TEXT NOT NULL (e.g., ["BTC_spot","ETH_spot"])
- estimator TEXT NOT NULL ("rolling_ols" | "kalman" later)
- params_json TEXT

**Indexes**
- CREATE INDEX idx_factor_runs_dataset_freq ON factor_model_runs(dataset_id, freq);

**Example row**
- ("fctr_9a21c0d1e4fa2b7a","2026-02-19T18:30:00Z","7e3c1f2a9b1d4e0c","1h",72,24,"[\"BTC_spot\",\"ETH_spot\"]","rolling_ols","{\"add_const\":true}")

---

### Table: factor_betas (materialized betas and fit diagnostics; avoids recompute + enables audit)

**Columns**
- factor_run_id TEXT NOT NULL (FK → factor_model_runs.factor_run_id)
- ts_utc TEXT NOT NULL
- asset_id TEXT NOT NULL (use existing pair_key style: chain:address)
- factor_name TEXT NOT NULL
- beta REAL
- alpha REAL
- r2 REAL
- PRIMARY KEY (factor_run_id, ts_utc, asset_id, factor_name)

**Indexes**
- CREATE INDEX idx_factor_betas_ts ON factor_betas(factor_run_id, ts_utc);
- CREATE INDEX idx_factor_betas_asset ON factor_betas(factor_run_id, asset_id);

**Example row**
- ("fctr_9a21c0d1e4fa2b7a","2026-02-10T13:00:00Z","solana:9wFF…","BTC_spot",1.12,0.0003,0.41)

---

### Table: residual_returns (materialized residual log returns per factor run)

**Columns**
- factor_run_id TEXT NOT NULL (FK)
- ts_utc TEXT NOT NULL
- asset_id TEXT NOT NULL
- resid_log_return REAL
- PRIMARY KEY (factor_run_id, ts_utc, asset_id)

**Indexes**
- CREATE INDEX idx_resid_ts ON residual_returns(factor_run_id, ts_utc);

**Example row**
- ("fctr_9a21c0d1e4fa2b7a","2026-02-10T13:00:00Z","solana:9wFF…",-0.0038)

---

### Table: regime_runs (versioned, causally-computed regimes)

**Columns**
- regime_run_id TEXT PRIMARY KEY
- created_at_utc TEXT NOT NULL
- dataset_id TEXT NOT NULL
- freq TEXT NOT NULL
- model TEXT NOT NULL ("heuristic_v1" | "garch" | "markov_switching")
- params_json TEXT

**Indexes**
- CREATE INDEX idx_regime_runs_dataset_freq ON regime_runs(dataset_id, freq);

**Example row**
- ("rgm_14c9…","2026-02-19T18:30:00Z","7e3c…","1h","markov_switching","{\"k\":2}")

---

### Table: regime_states (regime label/probability series)

**Columns**
- regime_run_id TEXT NOT NULL (FK)
- ts_utc TEXT NOT NULL
- regime_label TEXT NOT NULL
- regime_prob REAL (nullable if deterministic)
- PRIMARY KEY (regime_run_id, ts_utc)

**Indexes**
- CREATE INDEX idx_regime_states_ts ON regime_states(regime_run_id, ts_utc);

**Example row**
- ("rgm_14c9…","2026-02-10T13:00:00Z","risk_off",0.82)

---

### Minimal extensions to experiment registry (optional but recommended)

- Add engine_version TEXT and config_version TEXT to experiments for explicit reproducibility metadata beyond spec_version.

---

## Migration strategy

**Versioned migrations (how stored + applied)**  
- Introduce schema_migrations and a migration runner that applies migrations in ascending version.  
- Keep the existing **idempotent** style (CREATE TABLE IF NOT EXISTS, guarded ALTER TABLE ADD COLUMN) as the *implementation* of each migration, consistent with how core migrations work today.  
- Store each migration as a Python function in crypto_analyzer/db/migrations_v2.py, and have run_migrations() call them based on schema_migrations. Continue calling migrations on startup, but with version tracking.

**Backward compatibility expectations**  
- Existing DBs remain valid: all new tables are additive ("create if not exists").  
- For new columns in experiments, use guarded ALTER TABLE exactly as you already do for provenance fields.

**Rollback strategy**  
- SQLite rollback is **not supported** at the schema level; instead:  
- Before applying migrations, copy the SQLite file to db.sqlite.bak.<utc_timestamp>.  
- If migration fails, restore from backup and surface an error (non-zero exit code).  
- This is consistent with SQLite operational reality and maintains reproducibility.
