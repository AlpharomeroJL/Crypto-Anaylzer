# Performance and scale

**Purpose:** Complexity hotspots, expected runtime per stage, caching plan, SQLite limits and migration plan (Postgres/DuckDB/Parquet).  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Performance impact report

**Time complexity hotspots (by current code paths)**  
- Rolling multi-factor OLS loops **assets × time** and performs OLS per time step (windowed), i.e. roughly **O(A · T · K³)** in the worst case if you treat each OLS solve as cubic in factors/params (K is tiny here), but practically dominated by **A·T** iteration overhead in Python.  
- Cross-sectional per-timestamp regressions for neutralization/orthogonalization are **O(T · A · p²)** (p = number of exposures/signals), again dominated by Python loops.

**Expected runtime per stage (defaults with explicit assumptions)**  
Assume: freq=1h, T=4,000 bars (~166 days), A=200 assets, factors K=2.  
- Materialization: dominated by resampling + DB upserts; roughly O(T·A) resample operations.  
- Rolling OLS: today's pure-Python nested loops can become minutes at A=200, T=4k; you should cache outputs and/or optimize implementation.  
- Validation (IC): O(T·A) correlations with per-time slicing; moderate.  
- Optimization: per rebalance solve; manageable (n=assets at rebalance).

**Caching plan**
- Cache keys: sha256(dataset_id + freq + model_config_json)
- Cache targets:
  - factor model outputs (betas/residuals) in SQLite (tables above) keyed by factor_run_id
  - regime states in SQLite keyed by regime_run_id
  - validation bundles and sweep results as artifacts with SHA recorded in experiment registry
- Invalidation:
  - dataset_id change invalidates all derived caches by construction.

**Concrete cache modules**
- factor_cache (`crypto_analyzer/stats/factor_cache.py`), regime_cache (`crypto_analyzer/stats/regime_cache.py`), rc_cache (`crypto_analyzer/stats/rc_cache.py`); keys include dataset_id, config_hash, family_id; --no-cache and CRYPTO_ANALYZER_NO_CACHE disable.

**Determinism**
- CRYPTO_ANALYZER_DETERMINISTIC_TIME (timeutils) for reproducible materialize and reportv2 rerun.

**When SQLite breaks (and migration plan)**  
SQLite remains excellent for single-process research pipelines, but it becomes limiting when:  
- you want concurrent writers (multiple pollers, multiple materializers)  
- DB size grows to tens of GB with heavy indexing  
- you want high-throughput analytical scans over tall feature tables

**Migration path (least disruptive):**  
- Keep SQLite for **ingestion provenance + experiment registry**, and move heavy analytical tables to **DuckDB/Parquet** (local-first), or to **Postgres** if you need concurrency. This preserves your "single source of truth" semantics while acknowledging SQLite's concurrency ceiling.
