# Architecture

## Diagram

```
  +------------------+     +------------------+
  | dex_poll_        |     | config.yaml /    |
  | to_sqlite.py     |---->| crypto_analyzer  |
  | (60s poll)       |     | .config          |
  +--------+---------+     +--------+----------+
           |                        |
           v                        v
  +------------------+     +------------------+
  | dex_data.sqlite  |<----| crypto_analyzer  |
  | snapshots,       |     | .data            |
  | bars_*, spot_*   |     | (normalized load)|
  +--------+---------+     +--------+----------+
           |                        |
           v                        v
  +------------------+     +------------------+
  | materialize_     |     | crypto_analyzer  |
  | bars.py          |---->| .features        |
  |                  |     | (returns, vol,   |
  +--------+---------+     |  beta, regime)  |
           |                +--------+--------+
           |                         |
           |     +-------------------+------------------+
           |     v                   v                  v
           |  +--------+  +----------------+  +------------------+
           |  | .factors|  | .regimes       |  | .signals (journal)|
           |  | (resid) |  | (market regime)|  | .walkforward     |
           |  +--------+  +----------------+  +------------------+
           v
  +------------+  +--------+  +----------+  +---------------+  +------------------+
  | dex_       |  | dex_   |  | backtest |  | backtest_     |  | report_daily     |
  | analyze.py |  | scan.py|  | .py      |  | walkforward.py|  | .py              |
  +------------+  +--------+  +----------+  +---------------+  +------------------+
                    |
                    v
  +------------------+
  | app.py           |
  | (Streamlit)      |
  +------------------+
```

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| **crypto_analyzer.config** | DB path, table, price column, filters, defaults; YAML + env overrides. |
| **crypto_analyzer.data** | Load snapshots, bars, spot series; append spot returns to returns_df; get factor returns. |
| **crypto_analyzer.features** | Returns, vol, drawdown, momentum, beta/corr, dispersion, vol/beta regime, lookback helpers. |
| **crypto_analyzer.factors** | Factor matrix (BTC/ETH spot), OLS betas, residual returns/vol/lookback. |
| **crypto_analyzer.regimes** | Classify market regime from dispersion_z, vol_regime, beta_state; explain_regime. |
| **crypto_analyzer.signals** | signals_log table; detect_signals (beta compression, dispersion extreme, residual momentum); log_signals. |
| **crypto_analyzer.ui** | safe_for_streamlit_df, format_percent/float/bps, apply_rounding. |
| **crypto_analyzer.walkforward** | walk_forward_splits, run_walkforward_backtest (train/test folds, no lookahead). |
| **Root scripts** | Thin wrappers: config.py, data.py, features.py re-export from package. dex_analyze, dex_scan, backtest, report_daily, app.py call package or stay as-is with root imports. |

## Data flow

1. **Poller** writes to `dex_data.sqlite` (snapshots + optional spot_price_snapshots).
2. **materialize_bars** builds `bars_{freq}` from snapshots.
3. **Analyze / Scan / Report** load bars (and spot), build returns_df, compute features/factors/regimes, optionally log signals.
4. **Backtest** runs on bars with fee/slippage; **backtest_walkforward** runs OOS folds.
5. **Streamlit** uses the same data/features for Overview, Scanner, Backtest, Market Structure, Signals.

## Research-only

No exchange keys, order placement, wallet signing, or position management. All outputs are for research and monitoring.
