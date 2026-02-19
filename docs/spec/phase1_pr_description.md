# Phase 1 merge — PR description (copy/paste)

Use the bullets below in the PR description when cutting the Phase 1 merge.

---

## Evidence bullets

- **Leakage fix:** signal_residual_momentum_24h now uses causal residualization with as_of_lag_bars=1; lookahead path quarantined behind allow_lookahead=True and not used by report flows.

- **Determinism:** CRYPTO_ANALYZER_DETERMINISTIC_TIME stabilizes run_id + manifest timestamps; write_json_sorted + stable CSV writer produce byte-identical artifacts under deterministic mode.

- **ValidationBundle:** reportv2 emits per-signal ValidationBundle JSON referencing IC/decay/turnover artifacts (relative paths) with stable hashing.

- **Cost model unification:** single ExecutionCostModel used by both portfolio.py and cli/backtest.py.

- **Verification:** `.\scripts\run.ps1 verify` passes (doctor, pytest, ruff, research-only, diagrams).
