# Risk audit

**Purpose:** Leakage vectors, overfitting risk, regime dependence, capacity/slippage illusions, data snooping, and what NOT to implement yet.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Risk audit

**Leakage vectors (highest priority)**
- **Full-sample beta fitting in signal construction**: signal_residual_momentum_24h fits OLS betas on all available data via compute_ols_betas() and then computes residual returns—this is direct lookahead if used in evaluation/backtesting. Current status: signal_residual_momentum_24h default is allow_lookahead=False; research_report.py does not pass explicit flag (default remains causal).
- **Regime modeling leakage** (future state): any regime method that smooths across time using future observations must be banned in test; only filtering allowed. (Your current regime classifier is deterministic and does not leak by itself, but new statistical regimes can.)  
- **Cost/capacity leakage**: if "liquidity" or "ADV" is computed using future data, slippage becomes optimistic. Today's slippage proxy is per-bar based on contemporaneous liquidity_usd, but adding ADV-style features must be trailing/lagged.  
- **Multiple testing selection bias**: you already warn about many trials, but without formal correction you can still "promote noise."

**Overfitting risk from research additions**  
- Adding regimes + more signals increases degrees of freedom multiplicatively; must be paired with sweep registry + corrected inference (BH/BY + data snooping controls).  
- Kalman/Bayesian/representation learning increases model capacity; without strict walk-forward and "null suite" gating, false discoveries become likely.

**Regime dependence**  
- Current regime logic is rule-based; it may create the illusion of regime conditioning without genuine predictive stability. You already compute regime-conditioned performance tables; the key is to require out-of-sample persistence for any "regime-gated" alpha.

**Capacity/slippage illusions**
- Today's liquidity proxy slippage is a useful placeholder, but it's not size-dependent enough to produce realistic capacity cliffs.
- You must report performance as a function of notional size (AUM curve) before accepting signals as "tradable."
- `cli/scan.py` _add_capacity_slippage_tradable is research-only proxy; do not use for promotion/execution evidence without explicit disclaimer.

**Data snooping & multiple testing**  
- Deflated Sharpe implementation explicitly warns its assumptions are rough (iid / normality approximations); as you expand sweeps, you must stop relying on it as a stand-alone gate.

**What NOT to implement yet (with reasons)**  
- **Autoencoder/IPCA/representation learning**: high complexity, high overfit risk, and requires careful feature governance + much larger datasets. Defer until after corrected inference + execution realism are enforced.  
- **Tick-level execution simulation**: your stack is bar-based; pretending to simulate microstructure without tick/L2 data will produce fragile "realism theater." Focus on bar-consistent spread/impact proxies first.  
- **Full Reality Check / Romano–Wolf suite across huge strategy libraries**: implement the scaffolding (sweep registry + family definitions + bootstrap engine) first; then add advanced tests incrementally once the harness proves stable.

**Failure modes (detection)**
- When leakage is present (e.g. full-sample residual): detect via sentinel test (test_leakage_sentinel) and CI gate.
- When regime smoothing is used in test: detect via raise in RegimeDetector (mode="smooth" in test must raise).
