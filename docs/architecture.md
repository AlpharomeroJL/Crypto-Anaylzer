# Architecture

This expands the README’s high-level diagram with module responsibilities.

## Diagram

Data flow: poll → SQLite → materialize bars → research / backtests / reports / UI.

```
  +------------------------+     +------------------+
  | dex_poll_to_sqlite.py  |---->| config.yaml /    |
  | (poll, interval 60s)   |     | config.py        |
  +------------+-----------+     +------------------+
               |                           |
               v                           v
  +------------------------+     +------------------+
  | dex_data.sqlite        |<----| crypto_analyzer  |
  | snapshots, bars_*      |     | .data (load)     |
  +------------+-----------+     +------------------+
               |                           |
               v                           v
  +------------------------+     +------------------+
  | materialize_bars.py    |     | .features        |
  | bars_5min, 1h, 1D      |     | (returns, vol,   |
  +------------+-----------+     |  regime, etc.)   |
               |                  +--------+--------+
               |                           |
               +-----------+---------------+
                           v
  +--------+  +--------+  +----------+  +----------------+  +----------+
  | dex_   |  | dex_   |  | backtest |  | report_*.py    |  | app.py   |
  | analyze|  | scan   |  | *_wf     |  | (daily, R, Rv2) |  | Streamlit|
  +--------+  +--------+  +----------+  +----------------+  +----------+
```

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| **crypto_analyzer.config** | DB path, table, price column, filters, defaults; YAML + env overrides. |
| **crypto_analyzer.data** | Load snapshots, bars, spot series; append spot returns; get factor returns. |
| **crypto_analyzer.features** | Returns, vol, drawdown, momentum, beta/corr, dispersion, vol/beta regime, lookback helpers. |
| **crypto_analyzer.factors** | Multi-factor OLS (BTC/ETH spot), rolling regression (`rolling_multifactor_ols`), residual returns/vol/lookback. Falls back to BTC-only when ETH is unavailable. |
| **crypto_analyzer.experiments** | SQLite experiment registry: persists run metadata, metrics, and artifact hashes for cross-run comparison. |
| **crypto_analyzer.regimes** | Classify regime from dispersion_z, vol_regime, beta_state; explain_regime. |
| **crypto_analyzer.signals** | signals_log table; detect_signals (beta compression, dispersion extreme, residual momentum); log_signals. |
| **crypto_analyzer.ui** | safe_for_streamlit_df, format_percent/float/bps, apply_rounding. |
| **crypto_analyzer.walkforward** | walk_forward_splits, run_walkforward_backtest (train/test folds, no lookahead). |
| **Root scripts** | dex_analyze, dex_scan, backtest, materialize_bars, report_*, app.py call package or use root imports. |

## Data flow

1. **Poller** writes to `dex_data.sqlite` (snapshots; universe mode: allowlist, churn_log, persistence).
2. **materialize_bars** builds `bars_{freq}` from snapshots.
3. **Analyze / Scan / Report** load bars (and spot), build returns_df, compute features/factors/regimes, optionally log signals.
4. **Backtest** runs on bars with fee/slippage; **backtest_walkforward** runs OOS folds.
5. **Streamlit** uses the same data/features for Overview, Scanner, Backtest, Market Structure, Signals, Research, Governance.

## Research-only

No exchange keys, order placement, wallet signing, or position management. All outputs are for research and monitoring.
