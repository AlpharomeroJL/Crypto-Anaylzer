---
name: portfolio-audit
description: Run a portfolio-grade or hiring-manager-style audit on the Crypto-Analyzer repo: phased checklist (repo sanity, README, architecture, DB, dashboard, tests), produce punch list, apply fixes, then output Verification Report and Hiring Manager Verdict. Use when the user asks for portfolio readiness, final review, ruthless audit, hiring manager pass, or statsmodels-level quality check.
---

# Portfolio / Hiring Manager Audit

## When to Use
Apply when the user requests:
- Portfolio-grade or portfolio readiness audit
- Final reviewer / hiring manager / senior engineer review
- Ruthless audit, punch list, verification report
- README or docs at "statsmodels-level" quality
- End-state validation with exact commands and verdict

## Hard Constraints (Do Not Violate)
- No new product features beyond what exists (unless explicitly requested).
- SQLite single source of truth; no API keys; no live network in tests.
- Minimal dependencies; preserve backwards compatibility or document migrations.

## Phased Checklist (Execute in Order)

### Phase 0 — Repo sanity
- Inspect file tree: clean layout (`crypto_analyzer/`, `cli/`, `tests/`, `docs/`).
- One clear way to run: polling, dashboard, tests (document if missing).
- Flag: duplicate logic, god files, unclear naming, dead scripts.

### Phase 1 — README quality
- Layperson test: non-technical reader understands what it does and why.
- Engineer test: architecture, contracts, failure modes, extension points clear.
- Match reality: every claim traceable to code. Required: What it is, Quickstart, How it works, Provider architecture, Data model, Dashboard, Extending providers, Testing, Troubleshooting.

### Phase 2 — Architecture verification (in code)
- Provider interfaces (CEX spot + DEX snapshots), registry/chain, config-driven.
- Coinbase → Kraken fallback; retry/backoff; circuit breaker (skip when disabled_until); last-known-good; quality gates; provenance on every write.

### Phase 3 — DB and migrations
- Migrations idempotent and non-destructive; schema supports provenance and health; writes go through shared DB layer.

### Phase 4 — Dashboard and models
- Dashboard shows provider used, freshness/staleness, health (OK/DEGRADED/DOWN). Models consume data deterministically; no silent mixing of sources.

### Phase 5 — Tests and tooling
- Run tests (deterministic, no network). Unit tests for: provider fallback, circuit breaker, retry/backoff, provenance writes. Integration smoke test: one poll cycle, temp SQLite, mocked HTTP. Run ruff (and format); fix or document.

### Phase 6 — Hiring manager pass
- Entrypoints clean and documented; docs aligned with reality; failure modes handled; code easy to extend; design decisions in docs/design.md.

## Work Style
- Verify claims in code and tests; assume wrong until verified.
- Small, reviewable changes; update docs/tests with behavioral changes.
- Prefer simplest solution that meets the bar.

## Final Output (Required)
1. **Punch list** — issues found before fixes (table: severity, issue, location).
2. **Fixes applied** — what changed and where.
3. **Verification report** — commands run and results:
   - `python -m pytest -q`
   - `ruff check .` (and format if used)
   - Poll run-once (e.g. `.\scripts\run.ps1 poll` or `python cli/poll.py --run-seconds 65`)
   - Dashboard start (e.g. `.\scripts\run.ps1 streamlit`)
4. **Hiring manager verdict** — Portfolio grade YES/NO; why; remaining risks.
5. **Extensibility proof** (if requested) — minimal snippet for adding a new provider and registering it.

## Splitting Work
If the audit is large, split into subagents by phase (e.g. Phase 0–1, Phase 2–3, Phase 4–5, Phase 6 + consolidation). Consolidate into one punch list, apply fixes, then run verification and produce the final output.

## Before Finishing, Always Output
- **Files changed** (list)
- **Commands to run** (exact: pytest, ruff, poll, streamlit)
- **What to look for in output** (e.g. 200 passed, All checks passed, dashboard loads)
