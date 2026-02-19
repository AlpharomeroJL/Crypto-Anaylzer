# Phase 1 — Commit message and PR description (copy/paste)

Use the sections below when cutting the Phase 1 merge. Replace `*(PR link)*` in `implementation_ledger.md` with your actual PR URL after the PR is created.

---

## 1. Before committing

- Ensure `tmp_rerun_1/` and `tmp_rerun_2/` are not staged (they are in `.gitignore`).
- Run: `.\scripts\run.ps1 verify` and confirm all steps pass.

---

## 2. Conventional commit

**Title (one line):**

```
feat(spec): Phase 1 — causal residualizer, ValidationBundle, deterministic rerun, ExecutionCostModel
```

**Body:**

```
Implement Phase 1 of the Architecture Review and Integration Plan: eliminate
full-sample beta leakage in signal_residual_momentum_24h via causal
residualization (as_of_lag_bars=1); add ValidationBundle contract and
reportv2 per-signal emission; add deterministic rerun integration test
(CRYPTO_ANALYZER_DETERMINISTIC_TIME); unify cost logic in ExecutionCostModel
used by portfolio.py and cli/backtest.py. No SQLite schema changes.
```

---

## 3. PR description (paste into GitHub PR body)

**Title:** Same as commit title, or shorten to: `Phase 1: leakage fix, ValidationBundle, determinism, unified cost model`

**Body:**

### Summary

Phase 1 of the Architecture Review and Integration Plan: leakage hardening, ValidationBundle contract, deterministic rerun test, and unified ExecutionCostModel. No SQLite schema changes.

### Evidence bullets

- **Leakage fix:** signal_residual_momentum_24h now uses causal residualization with as_of_lag_bars=1; lookahead path quarantined behind allow_lookahead=True and not used by report flows.

- **Determinism:** CRYPTO_ANALYZER_DETERMINISTIC_TIME stabilizes run_id + manifest timestamps; write_json_sorted + stable CSV writer produce byte-identical artifacts under deterministic mode.

- **ValidationBundle:** reportv2 emits per-signal ValidationBundle JSON referencing IC/decay/turnover artifacts (relative paths) with stable hashing.

- **Cost model unification:** single ExecutionCostModel used by both portfolio.py and cli/backtest.py.

- **Verification:** `.\scripts\run.ps1 verify` passes (doctor, pytest, ruff, research-only, diagrams).

### Commands run

| Command | Result |
|---------|--------|
| `.\scripts\run.ps1 verify` | doctor → pytest → ruff → research-only → diagrams (all pass) |

### Risk / rollback

Rollback: revert the merge; no schema migrations. Watch: reportv2 and backtest use the same CLI flags; cost behavior is unchanged and now centralized in ExecutionCostModel.

---

## 4. After the PR is merged

In `docs/spec/implementation_ledger.md`, replace each `*(PR link)*` in the four Phase 1 rows with your actual PR URL (e.g. `https://github.com/AlpharomeroJL/Crypto-Anaylzer/pull/123`).
