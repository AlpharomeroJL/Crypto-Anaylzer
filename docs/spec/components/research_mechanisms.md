# Research mechanism extraction

**Purpose:** Capture per-report research mechanism specs (goal, inputs, transformations, outputs, assumptions, validation, operational constraints, failure modes).  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Report A mechanism spec

**Goal (1–2 sentences)**  
Upgrade the existing research stack from "institutional hygiene + solid architecture" into "institutional inference + execution realism + model originality," while keeping outputs reproducible and defensible under many-trials research workflows.

**Inputs (data fields, frequency, universe constraints)**  
SQLite-stored OHLCV bars (multiple frequencies) plus upstream snapshot provenance and reference factors (BTC/ETH), with a cross-sectional universe subject to liquidity/quality constraints and "run manifests / dataset fingerprinting" for lineage.

**Core transformations (math/logic steps)**  
Rolling multi-factor beta decomposition (baseline) → expand with:  
- Formal **multiple-testing control** and "data snooping" defenses (FDR variants; Reality Check / stepwise procedures) instead of warnings.  
- Replace rolling-window beta (hard cutoff) with **state-space / Kalman dynamic beta** plus uncertainty bands.  
- Add "trading physics": spread + participation/impact cost curves + scheduling (TWAP/VWAP) + latency/staleness modeling; report capacity-vs-performance degradation.  
- Optional "math depth" extensions: Bayesian regression / posterior uncertainty propagation into portfolio weights.  
- Optional "alpha originality" extensions: latent factors (autoencoder/IPCA), topology/network regimes, DEX microstructure-derived features.

**Outputs (signals, forecasts, weights, risk estimates)**  
A standardized "validation bundle" per signal variant: IC series, t-stats, bootstrap CIs, multiple-testing-adjusted p-values, sensitivity summaries, null/permutation diagnostics, plus portfolio weights and regime/cost-conditioned performance artifacts.

**Assumptions (stationarity, liquidity, independence, etc.)**  
Hidden assumptions that must be made explicit to avoid false certainty:  
- Multiple-testing control: BH-style procedures assume independence or a defined dependence structure; dependency-robust variants are more conservative but still require careful interpretation.  
- Reality Check / strategy comparisons implicitly assume the resampling scheme preserves dependence structure sufficiently for the null distribution to be meaningful.  
- Execution/capacity models assume a stable mapping from liquidity/volume proxies to spread/impact and that backtest trade sizes are "small enough" to be approximated at bar granularity.  
- State-space beta assumes a (usually Gaussian, linear) latent evolution model; mis-specification risk is high in regime shifts.

**Validation method (exact metrics + splits + anti-leakage)**  
- Walk-forward (train/test separation), block/bootstrap uncertainty, deflated Sharpe / PBO-style controls, plus formal multiple-testing controls for "many signals/horizons/variants."

**Operational constraints (latency, capacity, costs, slippage model)**  
- Costs must be state-dependent and size-dependent (spread + impact), with explicit participation constraints and sensitivity curves vs AUM/notional size.

**Failure modes (when it breaks, how to detect)**  
- "Passing by search": a single great backtest emerging from many trials; detect via corrected inference and reporting "survivors."  
- "Tradability cliff": signal disappears under spread/impact/latency; detect via capacity-vs-Sharpe curves and latency sweeps.  
- "Regime overfit": performance concentrated in one micro-regime; detect via regime-conditioned IC/PnL and stability artifacts.

**Hidden statistical assumptions & leakage risks (Report A emphasis)**  
- **Leakage risk: "research upgrades" that require fitting** (Kalman beta, Bayesian regression, latent factors) can easily become full-sample fits unless the pipeline enforces *per-fold* estimation and strictly causal filtering (no smoothing using future data).  
- **Leakage risk: parameter sweeps** turn the research process into an implicit optimizer over the same dataset; without corrected inference, you will select noise.  
- **Assumption risk: bootstrap choice**—naïve shuffles destroy serial dependence and can understate uncertainty; time-series bootstraps must preserve dependence.

---

## Report B mechanism spec

**Goal (1–2 sentences)**  
Build a coherent "Evidence layer" that standardizes signal evaluation, adds execution realism, introduces regime conditioning, and installs robustness defenses that prevent promoting noise to "production-grade research conclusions."

**Inputs (data fields, frequency, universe constraints)**  
- Bars and returns (multi-frequency), research universe filtered by liquidity/volume, factor returns (BTC/ETH), plus provenance/quality gates and experiment registry/manifest lineage.

**Core transformations (math/logic steps)**  
- Statistical rigor layer: automatic IC tracking (incl. t-stat), rolling stability, sensitivity sweeps, bootstrap CIs, structured tear-sheet-like artifacts.  
- Execution realism layer: explicit spread model + participation-based slippage/impact + position caps (liquidity/ADV), and consistent enforcement through optimizer & simulator.  
- Regime module: move from purely heuristic labels to statistically anchored volatility/regime models (ARCH/GARCH; Markov switching) and use regime probabilities when possible.  
- Robustness defense: permutation/shuffle nulls (properly dependence-aware), and explicit data-snooping controls (Reality Check / stepwise multiple testing).

**Outputs (signals, forecasts, weights, risk estimates)**  
- Standard artifacts: IC distributions, stability series, regime-conditioned performance, cost/capacity-aware PnL, plus "promotion criteria" outputs that tell you what is credible vs exploratory.

**Assumptions (stationarity, liquidity, independence, etc.)**  
- Treating volatility clustering models or regime switching as stable enough for out-of-sample usefulness; assumes underlying process can be approximated by those families.  
- Spread/impact models constructed from proxies assume those proxies are reasonably monotone with true microstructure costs in the venues you study.

**Validation method (exact metrics + splits + anti-leakage)**  
- Walk-forward evaluation as the primary split; bootstrap and robustness tests layered on top; Reality Check / stepwise procedures for "many variants tried."

**Operational constraints (latency, capacity, costs, slippage model)**  
- Costs must be enforced consistently (screening → optimizer → simulator); regime and cost interaction is first-class (risk-off widens spreads/impact).

**Failure modes (when it breaks, how to detect)**  
- Regime model overfit / "decorative regimes" that don't change decisions; detect when regime-conditioned IC/PnL does not materially differ or does not persist out-of-sample.  
- False inference from dependent data using naïve tests; detect via dependence-aware bootstrap/permutation and corrected p-values.

**Hidden statistical assumptions & leakage risks (Report B emphasis)**  
- **Leakage risk: regime inference**—Markov switching / volatility models can leak if you compute full-sample states and then evaluate "as if known." You must use train-only estimation and *filtering* (online state) in test.  
- **Leakage risk: cost proxies like ADV**—if "ADV" or liquidity thresholds are computed using future volume/liquidity, costs and capacity constraints become lookahead-biased.  
- **Assumption risk: null tests**—randomly shuffling timestamps breaks autocorrelation; if you use it to claim significance, you will materially mis-estimate the null.

**Single recommended direction when the reports diverge**  
Both reports propose ambitious optional upgrades (Bayesian + representation learning + network topology). The recommended direction is to **implement "inference discipline + causal regime modeling + execution realism" first** and postpone representation learning until the platform proves it can reject false discoveries at scale. This is aligned with the reports' shared emphasis that the credibility jump comes from defensible inference and trading physics, not feature proliferation.
