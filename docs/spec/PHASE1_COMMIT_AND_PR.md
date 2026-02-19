# Phase 1 — Production-grade commit and PR description (copy/paste)

Replace `*(PR link)*` in `implementation_ledger.md` with your PR URL after merge.

**Before committing:** Ensure `tmp_rerun_1/` and `tmp_rerun_2/` are not staged; run `.\scripts\run.ps1 verify` and confirm all steps pass.

---

## 1. Conventional commit (production-grade)

**Title (72 chars or fewer):**

```
feat(spec): Phase 1 — causal residualizer, ValidationBundle, determinism, ExecutionCostModel
```

**Body (wrap ~72 chars):**

```
Implement Phase 1 of the Architecture Review and Integration Plan.

- Leakage: Replace full-sample OLS in signal_residual_momentum_24h with
  causal residualization (as_of_lag_bars=1). Lookahead path quarantined
  behind allow_lookahead=True; not used by report flows.
- ValidationBundle: Dataclass contract; reportv2 emits per-signal bundle
  JSON + IC/decay/turnover CSVs (relative paths, stable hashing).
- Determinism: CRYPTO_ANALYZER_DETERMINISTIC_TIME stabilizes run_id and
  manifest; write_json_sorted and stable CSV writer for byte-identical
  artifacts. Integration test: test_deterministic_rerun_identical_bundle_and_manifest.
- Cost model: Single ExecutionCostModel (crypto_analyzer/execution_cost.py)
  used by portfolio.apply_costs_to_portfolio and cli/backtest strategies.

No SQLite schema changes. Backward compatible CLI flags.
```

**Footer (optional):**

```
Verification: .\scripts\run.ps1 verify (doctor, pytest, ruff, research-only, diagrams).
Refs: docs/spec/master_architecture_spec.md, docs/spec/implementation_ledger.md.
```

---

## 2. PR description (paste into GitHub PR body)

**PR title:** `feat(spec): Phase 1 — causal residualizer, ValidationBundle, determinism, ExecutionCostModel`

**PR body (markdown):**

```markdown
## Summary

Phase 1 of the Architecture Review and Integration Plan: leakage hardening, ValidationBundle contract, deterministic rerun guarantees, and unified execution cost model. No SQLite schema changes; CLI interfaces remain backward compatible.

---

## Scope

| Area | Change |
|------|--------|
| **Leakage fix** | `signal_residual_momentum_24h` uses causal residualization (`as_of_lag_bars=1`). Full-sample path quarantined behind `allow_lookahead=True` (default `False`); report/reportv2 never use it. |
| **Determinism** | `CRYPTO_ANALYZER_DETERMINISTIC_TIME` stabilizes `run_id` and manifest timestamps. `write_json_sorted` + stable CSV writer produce byte-identical artifacts. |
| **ValidationBundle** | New `crypto_analyzer/validation_bundle.py`; reportv2 emits per-signal bundle JSON + IC series/decay/turnover CSVs (relative paths, stable hashing). |
| **Cost model** | New `crypto_analyzer/execution_cost.py`; `portfolio.apply_costs_to_portfolio` and `cli/backtest` both delegate to `ExecutionCostModel`. |

---

## Evidence

- **Leakage:** Causal residual momentum does not exploit future factor info; sentinel test `test_causal_residual_momentum_no_abnormal_ic` enforces. Lookahead path gated by `allow_lookahead=True`.
- **Determinism:** With `CRYPTO_ANALYZER_DETERMINISTIC_TIME` set, two reportv2 runs yield identical `run_id`, path-normalized manifest, byte-identical ValidationBundle JSON, and matching artifact SHA256 (`test_deterministic_rerun_identical_bundle_and_manifest`).
- **ValidationBundle:** Schema: `run_id`, `dataset_id`, `signal_name`, `freq`, `horizons`, `ic_summary_by_horizon`, `ic_decay_table`, `meta`, artifact paths (relative).
- **Cost model:** Unit tests: same inputs → identical net returns; higher turnover → higher costs; missing liquidity → conservative fallback (50 bps). Portfolio and backtest share one implementation.

---

## Verification

| Command | Result |
|---------|--------|
| `.\scripts\run.ps1 verify` | doctor → pytest → ruff → research-only → diagrams (all pass) |

---

## Files changed (key)

- **New:** `crypto_analyzer/timeutils.py`, `crypto_analyzer/execution_cost.py`, `crypto_analyzer/validation_bundle.py`; `tests/test_leakage_sentinel.py`, `tests/test_reportv2_deterministic_rerun.py`, `tests/test_execution_cost.py`, `tests/test_ingest_context.py`; `docs/spec/*` (ledger, phase1 PR, components).
- **Modified:** `crypto_analyzer/factors.py` (causal_residual_returns), `crypto_analyzer/alpha_research.py` (signal_residual_momentum_24h causal by default), `crypto_analyzer/portfolio.py` (delegate to ExecutionCostModel), `cli/backtest.py` (use ExecutionCostModel), `cli/research_report_v2.py` (ValidationBundle per signal, early run_id/dataset_id, write_json_sorted); `crypto_analyzer/artifacts.py`, `crypto_analyzer/governance.py`, `crypto_analyzer/ingest/__init__.py`; `pyproject.toml`, `scripts/run.ps1`, `.gitignore`.

---

## Risk and rollback

- **Rollback:** Revert merge; no schema migrations. No data migration required.
- **Watch:** reportv2 and backtest retain same CLI flags; cost behavior is unchanged and now centralized. If cost semantics ever need to diverge, extend `ExecutionCostModel` config rather than forking logic.
```

---

## 3. After merge

In `docs/spec/implementation_ledger.md`, replace each `*(PR link)*` in the four Phase 1 rows with your PR URL.
