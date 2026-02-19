# Dependency graph

**Purpose:** Baseline and refined pipeline dependency graphs (Mermaid) showing stage order and where new research components plug in.  
**Canonical spec:** [../master_architecture_spec.md](../master_architecture_spec.md)

---

## Baseline dependency graph

```mermaid
graph TD
  A[Ingestion] --> B[Bars]
  B --> C[Factors]
  C --> D[Signals]
  D --> E[Validation]
  E --> F[Optimizer]
  F --> G[Walk-Forward Backtest]
  G --> H[Stats Corrections]
  H --> I[Reporting/UI/API]
```

---

## Refined graph with new research components

Refined graph with **new research components inserted where they belong** (and without breaking existing stage boundaries):

```mermaid
graph TD
  A[Ingestion] --> B[Bars]
  B --> C[Factors]
  B --> R[Regime Models]
  R --> E[Validation]
  R --> X[Execution Realism]
  C --> D[Signals]
  D --> E[Validation]
  E --> S[Rigor & Robustness Harness]
  S --> F[Optimizer]
  F --> X[Execution Realism]
  X --> G[Walk-Forward Backtest]
  G --> H[Stats Corrections]
  H --> I[Reporting/UI/API]
  I --> J[Experiment Registry & Manifests]
```
