# Pipeline contracts

**Purpose:** Contract-first decomposition of pipeline stages: inputs, outputs, invariants, and error handling per stage.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Repo system decomposition — Pipeline contract

Below is a **contract-first** decomposition of your current stack based on repo docs and code.

### *Ingestion*

**Inputs**  
Provider-chain responses (SpotPriceChain, DexSnapshotChain) with resilience wrappers (retry/backoff, circuit breaker, last-known-good cache) and quality gates.

**Outputs (SQLite tables)**  
- spot_price_snapshots (spot price snapshots + provenance fields).  
- sol_monitor_snapshots (DEX pair snapshots + provenance fields).  
- provider_health (provider status, fail count, disabled_until, etc.).  
- Universe tracking tables (universe_allowlist, universe_persistence, universe_churn_log).

**Required invariants**  
- ts_utc is UTC, parseable, and monotonic per asset stream (or at minimum strictly orderable).  
- Provenance columns are always present (provider_name, fetched_at_utc, fetch_status, error_message).  
- Prices are positive; invalid prices are rejected/dropped by quality gates + loaders.

**Where errors are handled vs surfaced**  
- Handle provider/network failures inside provider chain (fallback, circuit breaker, LKG).  
- Surface integrity problems as warnings and/or strict failure in "doctor / reportv2" depending on flags.

### *Bar materialization*

**Inputs**  
- sol_monitor_snapshots via load_snapshots() (with filters) to produce resampled OHLCV-style bars.

**Outputs (SQLite tables)**  
- bars_{freq} with primary key (ts_utc, chain_id, pair_address) and computed features: log_return, cum_return, roll_vol, liquidity_usd, vol_h24.  
- Special case: bars_1D is materialized from bars_1h.

**Required invariants**  
- Deterministic, idempotent UPSERT semantics (re-running yields identical bars for same underlying snapshots).  
- No non-positive OHLC values; close cannot be null.

**Where errors are handled vs surfaced**  
- "Too few points," non-positive OHLC, NaNs → skip pair or return 0 rows.  
- Missing dependency (e.g., bars_1h absent when building bars_1D) surfaces as an explicit message.

### *Factor model and decomposition*

**Inputs**  
- Returns matrix including BTC/ETH spot return columns + asset return columns (via get_research_assets and get_factor_returns in report pipeline).  
- Rolling window parameters (window, min_obs) for rolling regressions.

**Outputs (current, in-memory)**  
- Rolling betas per factor, rolling R², and residual returns panel.

**Required invariants**  
- Time alignment: factor returns and asset returns must share the same index and be NaN-cleaned consistently.  
- For "no leak" evaluation: factor model fitting must be restricted to available history per fold (not full-sample). This is **not currently enforced as a contract**, even though rolling regression is available.

**Where errors are handled vs surfaced**  
- Linear algebra issues → NaNs / graceful degradation.

### *Signal generation*

**Inputs**  
- Asset return panels; factor returns; optional liquidity panel for exposures; lookback horizons per freq.

**Outputs (current, in-memory)**  
- Signal panels signal_df (index=ts_utc, columns=asset_id) for momentum and composites ("clean_momentum", "value_vs_beta").  
- Cross-sectional factor frames (cs_factors) and combined composite signals (cs_model).

**Required invariants**  
- Signal timestamps must represent information available at that timestamp (or earlier), and the pipeline must define the execution convention (trade at t+1). Your backtest implementations enforce this by using position.shift(1) before applying returns.

**Where errors are handled vs surfaced**  
- Missing factors → signal builders return None or empty frames (degrade gracefully).

### *Signal validation*

**Inputs**  
- Signal panel signal_df and return panel returns_df; horizon list.

**Outputs**  
- Forward returns matrix per horizon.  
- IC time-series (Spearman rank IC by default) and summary statistics (mean, std, t-stat, hit rate, CI).  
- IC decay table across horizons.  
- Optional orthogonalization and exposure neutralization outputs.

**Required invariants**  
- Forward returns must exclude contemporaneous return overlap (implemented via rolling sum + shift).  
- Must fail fast (or warn loudly) if signals/returns indices are misaligned or non-monotone; integrity helpers exist but do not yet hard-block most alignment failures.

**Where errors are handled vs surfaced**  
- Insufficient cross-section (fewer than 2 assets at a timestamp) yields NaN IC at that time.

### *Portfolio optimization*

**Inputs**  
- Expected returns proxy (signal vector) and covariance matrix; leverage/net/max weight constraints.

**Outputs**  
- Weight vector per rebalance time (or last time for "advanced" heuristic).

**Required invariants**  
- Covariance must be PSD (enforced via eigenvalue clipping).  
- Optimizer constraints must be satisfied or fallback is used (rank-based L/S).

**Where errors are handled vs surfaced**  
- Optimization errors → deterministic fallback weights (rank-based).

### *Backtest and walk-forward*

**Inputs**  
- bars_{freq} and strategy parameters.  
- Walk-forward split parameters (train_bars, test_bars, step_bars).

**Outputs**  
- Strategy equity curve and fold metrics; stitched out-of-sample equity.

**Required invariants**  
- No overlap between train and test indices.  
- Execution convention: trading decisions at t impact returns beginning at t+1 (implemented by using lagged positions).

**Where errors are handled vs surfaced**  
- If insufficient data for splits: return empty outputs.

### *Statistical correction*

**Inputs**  
- PnL series; estimated number of trials; walk-forward results; bootstrap parameters.

**Outputs**  
- Deflated Sharpe-style adjustment (with explicit warnings about rough assumptions).  
- PBO proxy based on walk-forward results schema.  
- Block bootstrap distributions and Sharpe CI.

**Required invariants**  
- The block bootstrap must not pretend i.i.d. when serial dependence exists; current implementation is a fixed-length block resampler (not stationary bootstrap).

**Where errors are handled vs surfaced**  
- Small-sample conditions → NaNs + informative messages.

### *Reporting*

**Inputs**  
- Tables in SQLite + derived in-memory analytics; CLI arguments.

**Outputs**  
- Report markdown + charts + JSON manifests + experiment registry rows (SQLite).

**Required invariants**  
- Every run must be traceable to git_commit, environment fingerprint, dataset fingerprint/id, and output hashes.
