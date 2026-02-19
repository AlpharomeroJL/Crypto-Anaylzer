# Design Document

## Overview

This document describes the architecture, data flow, provider contracts, and failure handling strategies used by the Crypto Quantitative Research Platform.

## System Architecture

The platform is organized into four independent stages, each with a clear contract:

```
  INGESTION  →  MATERIALIZATION  →  MODELING  →  PRESENTATION
  (providers)    (bar builder)      (research)    (dashboard/API)
```

Each stage reads from and writes to the **same SQLite database**, which serves as the single source of truth. Stages can run independently: if the poller stops, materialization and modeling still work on existing data.

## Provider Architecture

### Problem

The original poller hardcoded Coinbase and Kraken calls with inline retry loops. Adding a new exchange required editing the poll loop, duplicating retry logic, and risking regressions.

### Solution: Provider Chain Pattern

Data ingestion uses a **provider chain** — an ordered list of providers tried in priority order. Each provider implements a typed protocol:

```python
class SpotPriceProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    def get_spot(self, symbol: str) -> SpotQuote: ...

class DexSnapshotProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    def get_snapshot(self, chain_id: str, pair_address: str) -> DexSnapshot: ...
    def search_pairs(self, query: str, chain_id: str) -> list[dict]: ...
```

### Resilience Wrappers

Every provider call passes through three layers:

1. **Retry with exponential backoff** — Configurable max retries, base delay, backoff factor. Handles transient 429s and timeouts.

2. **Circuit breaker** — Per-provider state machine (CLOSED → OPEN → HALF_OPEN → CLOSED). Opens after N consecutive failures, skipping the provider for a cooldown period. Auto-recovers with a probe request.

3. **Last-known-good cache** — When all providers fail, the system returns the last valid result (marked as DEGRADED) rather than crashing or writing garbage.

### Data Quality Gates

Before any record reaches the database:
- Price must be positive and non-null
- Status must not be DOWN (DEGRADED is allowed but flagged)
- Provider name and fetch timestamp are always set

### Provider Registry

Providers register by name in a central registry. The chain order is config-driven:

```yaml
# config.yaml
providers:
  spot_priority: ["coinbase", "kraken"]
  dex_priority: ["dexscreener"]
```

Adding a provider: implement the protocol, register in `defaults.py`, add to config.

## Database Schema

### Provenance Fields

Every ingested record includes:
- `provider_name` — Which provider served this data point
- `fetched_at_utc` — When the upstream API was called
- `fetch_status` — OK, DEGRADED, or DOWN
- `error_message` — Error details when status is not OK

### Health Tracking

The `provider_health` table tracks per-provider state:

| Column | Type | Description |
|--------|------|-------------|
| provider_name | TEXT PK | Provider identifier |
| status | TEXT | OK / DEGRADED / DOWN |
| last_ok_at | TEXT | Last successful fetch timestamp |
| fail_count | INTEGER | Consecutive failure count |
| disabled_until | TEXT | Circuit breaker cooldown expiry |
| last_error | TEXT | Most recent error message |
| updated_at | TEXT | Last state change |

### Migrations

All schema changes use `CREATE TABLE IF NOT EXISTS` and guarded `ALTER TABLE ADD COLUMN`. Migrations run on every startup and are idempotent.

## Data Flow

### Ingestion

```
Every 60s:
  For each spot asset (SOL, ETH, BTC):
    SpotPriceChain.get_spot(symbol)
      → Try coinbase.get_spot()
        → On failure: try kraken.get_spot()
          → On failure: return last-known-good (DEGRADED)
      → DbWriter.write_spot_price()  (with provenance)

  For each DEX pair:
    DexSnapshotChain.get_snapshot(chain_id, pair_address)
      → Try dexscreener.get_snapshot()
        → On failure: return last-known-good (DEGRADED)
      → DbWriter.write_dex_snapshot()  (with provenance)

  ProviderHealthStore.upsert_all()  (persist health state)
```

### Materialization

```
For each frequency (5min, 15min, 1h, 1D):
  Load raw snapshots from sol_monitor_snapshots
  Group by (chain_id, pair_address)
  Resample to OHLCV bars
  Compute: log_return, cum_return, roll_vol
  UPSERT into bars_{freq}  (idempotent)
```

### Research

```
Load bars → Build returns matrix → Factor decomposition (OLS)
→ Signal construction (momentum, size, liquidity)
→ Signal validation (IC, decay, orthogonalization)
→ Portfolio optimization (QP with constraints)
→ Walk-forward backtest (strict train/test)
→ Overfitting controls (DSR, PBO, bootstrap)
→ Regime conditioning (dispersion, beta state, vol regime)
→ Experiment registry (metrics, hypothesis, artifacts)
→ Governance manifest (git commit, env, data hashes)
```

## Failure Modes and Recovery

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Coinbase API down | Kraken fallback; if both fail, last-known-good | Auto-recovers when API returns |
| Dexscreener rate limit (429) | Retry with backoff (up to 3 attempts) | Automatic after rate limit window |
| Provider returns invalid data | Quality gate rejects; logs warning | Next cycle tries again |
| All providers down for >5min | LKG cache expires; records gap | Manual investigation needed |
| Circuit breaker trips | Provider skipped for 60s cooldown | Half-open probe after cooldown |
| SQLite write failure | Transaction rolled back; logged | Check disk space / permissions |
| Config YAML missing | Falls back to hardcoded defaults | Create config.yaml or set env vars |

## Design Decisions

### Why Protocol instead of ABC?

Protocols enable structural subtyping — a class doesn't need to explicitly inherit from the interface. This makes it easier to create test doubles and keeps the dependency graph shallow.

### Why frozen dataclasses for SpotQuote/DexSnapshot?

Immutability guarantees that data flowing through the chain can't be accidentally mutated by a retry wrapper or quality gate. The `frozen=True` flag raises `FrozenInstanceError` on assignment.

### Why per-provider circuit breakers?

Without circuit breakers, a failing provider would be retried on every poll cycle, wasting time and potentially triggering rate limits. The circuit breaker pattern lets healthy providers serve traffic while the failing one recovers.

### Why last-known-good instead of just failing?

For a research platform running 24/7, a brief API outage shouldn't create gaps in the data. Stale data (marked DEGRADED) is more useful than no data, and the provenance fields make it easy to filter or flag in analysis.
