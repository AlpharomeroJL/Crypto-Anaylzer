# Spec directory — Crypto-Analyzer research upgrades

Canonical source: [master_architecture_spec.md](master_architecture_spec.md). Do not delete or replace the master spec; it remains the authoritative full document.

## Contents

- [Master Architecture Spec](master_architecture_spec.md) — full canonical document
- [System overview](system_overview.md) — pipeline lifecycle, data model, determinism, stats stack, feature flags, promotion
- [Implementation Ledger](implementation_ledger.md) — requirement → status, PRs, evidence
- [Operational Runbook: Liqshock Case Study](case_study_liqshock_release.md) — one-command usage, outputs, snapshot semantics

## Component specs

| Component | Description |
|-----------|-------------|
| [components/pipeline_contracts.md](components/pipeline_contracts.md) | Pipeline stage inputs/outputs/invariants/error handling |
| [components/dependency_graph.md](components/dependency_graph.md) | Baseline and refined Mermaid dependency graphs |
| [components/research_mechanisms.md](components/research_mechanisms.md) | Research mechanism extraction (Report A/B): goal, inputs, outputs, assumptions, validation, failure modes |
| [components/research_repo_mapping.md](components/research_repo_mapping.md) | Research mechanism ↔ pipeline stage mapping table |
| [components/schema_plan.md](components/schema_plan.md) | Schema evolution: proposed tables, migrations, rollback |
| [components/interfaces.md](components/interfaces.md) | New/updated interface contracts (Residualizer, RegimeDetector, ExecutionCostModel, etc.) |
| [components/testing_acceptance.md](components/testing_acceptance.md) | Unit/integration/statistical tests, correction strategy, acceptance criteria |
| [components/versioning_release.md](components/versioning_release.md) | SemVer, config/model versioning, reproducibility metadata |
| [components/performance_scale.md](components/performance_scale.md) | Complexity hotspots, runtime, caching, SQLite limits and migration path |
| [components/risk_audit.md](components/risk_audit.md) | Leakage vectors, overfitting, regime dependence, what NOT to implement |
| [components/phased_execution.md](components/phased_execution.md) | Phase 1/2/3 execution checklist |

All component files link back to the [master spec](master_architecture_spec.md).
