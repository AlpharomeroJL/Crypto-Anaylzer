# Interface contracts

**Purpose:** New/updated interface contracts with function signatures, error handling, and determinism guarantees.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

These contracts are designed to fit your current architecture: small, typed, deterministic functions; SQLite remains the store of record; artifacts remain hash-addressed and logged.

---

## Component: Residualizer

**Inputs**  
- returns_df (wide: index=ts_utc, cols=asset_id + factor cols)  
- factor_cols: list[str]  
- mode: "rolling_ols" | "kalman"  
- window_bars, min_obs  
- as_of_lag_bars (enforces causality; default = 1 for "trade next bar")

**Outputs**  
- FactorOutputs: {betas_dict, alpha_df, r2_df, residual_df, metadata}

**Function signatures (pseudocode)**

```
interface Residualizer:
  compute(
    returns_df: DataFrame,
    factor_cols: list[str],
    config: FactorModelConfig,
    as_of_lag_bars: int = 1
  ) -> FactorOutputs
```

**Error handling**  
- Raise ValueError if factor_cols missing entirely or index not monotonic.  
- Return empty frames if insufficient data per asset (consistent with current "graceful degradation" patterns).

**Determinism guarantees**  
- Sort index ascending; sort columns lexicographically.  
- No global RNG use; if Kalman uses randomness (it shouldn't), require an explicit seed and log it.

**Leakage hardening requirement**  
- Must enforce as_of_lag_bars: residual at time *t* used for signal at *t* must be computed using returns ≤ *t−as_of_lag_bars*. (This fixes the current "full sample OLS" leakage risk in signal_residual_momentum_24h.)

---

## Component: RegimeDetector

**Inputs**  
- market_series (e.g., BTC returns, dispersion, vol proxy)  
- fit_window (train-only window)  
- inference_mode: "filter" (no smoothing in test)

**Outputs**  
- regime_states: series or DataFrame with ts_utc, label, prob

**Function signatures**

```
interface RegimeDetector:
  fit(train_data: DataFrame, config: RegimeConfig) -> RegimeModel
  predict(test_data: DataFrame, mode: str = "filter") -> RegimeStateSeries
```

**Error handling**  
- Raise if asked to run mode="smooth" in test or if train/test windows overlap.

**Determinism guarantees**  
- Fixed optimizer seeds (if any), stable ordering, and strict separation of fit() and predict().

---

## Component: ExecutionCostModel

This unifies today's cost logic in portfolio.apply_costs_to_portfolio() and the per-asset liquidity slippage proxy in cli/backtest.py.

**Inputs**  
- weights_df (target portfolio)  
- prev_weights_df or implicit lag  
- bars_meta (liquidity, volume proxies)  
- model_params (fee_bps, spread_bps_model, impact_model, max_participation)

**Outputs**  
- net_returns time series  
- cost_breakdown per period: fee, spread, impact

**Function signatures**

```
interface ExecutionCostModel:
  apply_costs(
    gross_returns: Series,
    weights: DataFrame,
    market_meta: DataFrame,
    config: ExecutionConfig
  ) -> tuple[Series, CostFrame]
```

**Error handling**  
- If required meta missing: either raise (strict mode) or fall back to conservative defaults (explicitly logged).

**Determinism guarantees**  
- No randomness; if scheduling simulation uses pseudo-random fills, require a seed and persist it.

---

## Component: MultipleTestingAdjuster

**Inputs**  
- table of hypotheses with p-values (e.g., per signal × horizon × parameter)  
- dependency mode ("bh" or "by")

**Outputs**  
- adjusted p-values + "discoveries" boolean flags

**Function signatures**

```
interface MultipleTestingAdjuster:
  adjust(p_values: Series, method: str, q: float) -> AdjustedPValues
```

---

## Component: Bootstrapper

**Inputs**  
- return series  
- method: block_fixed | stationary  
- seed  
- block_length rules

**Outputs**  
- resampled statistic distribution + CI

**Function signatures**

```
interface Bootstrapper:
  sample(series: Series, config: BootstrapConfig) -> ndarray
  ci(samples: ndarray, ci_pct: float) -> tuple[float, float]
```
