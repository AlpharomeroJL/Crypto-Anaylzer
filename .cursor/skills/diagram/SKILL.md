---
name: diagram
description: Generate or update presentation-grade architecture diagrams (PlantUML or C4) for the Crypto-Analyzer repo. Use when the user asks for architecture diagrams, system diagram, C4 diagram, PlantUML, or to visualize providers, chain, resilience, or DB. Outputs go in docs/diagrams/; export SVG/PNG; diagrams must match the code (providers, chain, resilience, DB).
---

# Architecture Diagrams

## When to Use
- User asks for: architecture diagram, system diagram, C4, PlantUML, "diagram the providers/chain/DB", or presentation-grade visuals for this repo.
- When the user explicitly requests diagram updates after architecture changes, update `docs/diagrams/` so diagrams stay aligned with code.

## Conventions
- **Location**: All diagram sources and exports live under `docs/diagrams/`.
- **Formats**: Prefer PlantUML (`.puml`) for source; export to **SVG** and **PNG** for docs and presentations.
- **Match code**: Diagrams must reflect the actual architecture: provider interfaces (SpotPriceProvider, DexSnapshotProvider), provider chain (ordered fallback), resilience (retry, circuit breaker, last-known-good), DB layer (SQLite, provenance, health), and data flow (ingestion → materialization → modeling → presentation). If in doubt, verify against `docs/design.md` and `crypto_analyzer/providers/`.

## Content to Cover (as relevant)
- **Provider layer**: CEX (Coinbase, Kraken), DEX (Dexscreener); protocols and chain order.
- **Resilience**: Retry/backoff, circuit breaker, LKG cache; wrap around provider calls.
- **DB**: SQLite tables (snapshots, bars_*, provider_health); provenance fields.
- **Pipeline**: Poll → SQLite → materialize bars → research/reports/dashboard.

## Workflow
1. Create or update `.puml` in `docs/diagrams/` (e.g. `architecture.puml`, `providers-chain.puml`).
2. Export to SVG and PNG (if PlantUML is available: `java -jar plantuml.jar -tsvg -tpng docs/diagrams/*.puml`, or document the export command for the user).
3. Optionally reference images in `docs/design.md` or README with relative paths, e.g. `docs/diagrams/architecture.svg`.

## If Export Tooling Is Missing
- Still add the `.puml` source so the user can export later.
- In the skill output, list the exact command to run to generate SVG/PNG (e.g. PlantUML CLI or VS Code PlantUML extension "Export current diagram").

## Output
- **Files changed** (list, e.g. `docs/diagrams/architecture.puml`, `docs/diagrams/architecture.svg`)
- **Commands to run** (if any: e.g. PlantUML export command)
- **What to look for** (diagram matches design.md and provider/chain/DB code)
