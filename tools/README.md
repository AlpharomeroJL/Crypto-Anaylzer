# Diagram export tools (in-repo, no admin)

Portable PlantUML + Graphviz for reproducible diagram export from `docs/diagrams/*.puml`.

## Layout

- **tools/plantuml/plantuml.jar** — PlantUML jar (download via setup script).
- **tools/graphviz/** — Portable Graphviz; **tools/graphviz/bin/dot.exe** must exist.

## Setup (one-time)

From repo root (requires network):

```powershell
.\scripts\setup_diagram_tools.ps1
```

This downloads `plantuml.jar` and the Graphviz Windows zip and unpacks so `tools/graphviz/bin/dot.exe` exists.

## Export diagrams

Requires **Java on PATH** (JRE or JDK). Then from repo root:

```powershell
.\scripts\export_diagrams.ps1
```

Exports every `*.puml` under `docs/diagrams/` to SVG and PNG using the in-repo jar and Graphviz.
