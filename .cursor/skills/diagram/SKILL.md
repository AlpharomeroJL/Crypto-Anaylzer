---
name: diagram
description: Generate or update presentation-grade architecture diagrams for the Crypto-Analyzer repo. Use when the user asks for a system diagram, PlantUML, C4, provider architecture, resilience flow, DB flow, or any repo diagram update. Diagram sources live in `docs/diagrams/` and exports should be kept aligned with the code.
---

# Architecture Diagrams

## Conventions
- Keep diagram sources in `docs/diagrams/`.
- Prefer PlantUML source files (`.puml`).
- Export SVG and PNG when the tooling is available.
- Make diagrams match the actual code and docs, especially provider interfaces, resilience flow, DB lineage, and pipeline boundaries.

## What To Verify Before Drawing
- Provider interfaces and registry wiring under `crypto_analyzer/providers/`
- Data flow and boundaries in `docs/design.md` and `docs/architecture.md`
- CLI or pipeline behavior if the diagram touches execution flow

## Workflow
1. Create or update the `.puml` file in `docs/diagrams/`.
2. Export the diagram with `.\scripts\export_diagrams.ps1` when PlantUML and Graphviz are available.
3. If export tooling is unavailable, still commit the `.puml` source and list the exact export command in the final output.

## Output
- Files changed, including `.puml`, `.svg`, and `.png` files when exported
- Commands to run for export
- What to look for: diagram matches the code and renders cleanly

