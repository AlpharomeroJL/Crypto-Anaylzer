# Coinbase Advanced Trade — Phase 1 (majors venue layer)

Phase 1 uses **public market-data only** (REST plus optional websocket liveness path; no API keys, no trading). Data lands in SQLite tables `venue_products` and `venue_bars_1h`, separate from DEX `bars_*` and `sol_monitor_snapshots`.

## Prerequisites

- Config: `venue.coinbase_advanced.product_ids` in `config.yaml` (defaults include `BTC-USD`, `ETH-USD`, `SOL-USD`).
- Same DB as the rest of the project (`db.path`).

## One path: empty venue tables → majors report

1. **Apply schema** (creates `venue_*` tables):

   ```text
   python -m crypto_analyzer venue-sync products
   ```

   Or on Windows: `.\scripts\run.ps1 venue-sync products`

2. **Backfill 1h candles** (default window: last 30 days; override with `--start` / `--end` ISO UTC):

   ```text
   python -m crypto_analyzer venue-sync candles
   ```

   Example longer backfill:

   ```text
   python -m crypto_analyzer venue-sync candles --start 2024-01-01T00:00:00Z --end 2025-01-01T00:00:00Z
   ```

3. **Research report (majors universe)** — requires `--freq 1h`:

   ```text
   python -m crypto_analyzer reportv2 --universe majors --freq 1h
   ```

4. **Optional live freshness path (public websocket)**:

   ```text
   python -m crypto_analyzer venue-sync ws-live --channel market_trades --run-seconds 120 --status-interval-sec 15
   ```

   Notes:
   - This path writes hourly bars into `venue_bars_1h` with source `coinbase_advanced_ws_market_trades` or `coinbase_advanced_ws_ticker`.
   - Health logs print message age, feed lag, reconnect count, and flushed-bar count.
   - It remains strictly market-data ingestion; no authenticated channels or execution logic.

## Commands reference

| Command | Purpose |
|--------|---------|
| `venue-sync products` | Upsert product metadata into `venue_products` for configured IDs |
| `venue-sync candles` | Upsert OHLCV into `venue_bars_1h`, recompute `log_return` per product |
| `venue-sync all` | `products` then `candles` |
| `venue-sync ws-live` | Subscribe to Coinbase public websocket and materialize closed 1h bars into `venue_bars_1h` |
| `reportv2 --universe majors --freq 1h` | Report using **only** `venue_bars_1h` (no DEX cross-section) |

## Semantics

- **Bar timestamp** `ts_utc` is the **candle open** in ISO UTC (from Coinbase `start`).
- **reportv2 lineage**: `dataset_id` / `dataset_id_v2` for `--universe majors` hash **venue** tables only; default `--universe dex` hashes **DEX research tables** and **excludes** `venue_*` so a venue backfill does not shift DEX experiment IDs.
- **Idempotency**: reruns use `INSERT ... ON CONFLICT DO UPDATE` on `(ts_utc, venue, product_id)`.
- **Not supported in Phase 1**: mixed DEX + majors in one cross-section, `liquidity_shock_reversion` on majors (needs DEX liquidity), authenticated or private endpoints.

## Troubleshooting

- **`No assets` in majors report**: run `venue-sync candles` and confirm rows: `SELECT COUNT(*) FROM venue_bars_1h;`
- **`--strict` on products**: fails if a configured `product_id` is not returned by the API (typo or delisted pair).
