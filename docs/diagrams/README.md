# Architecture diagrams

Diagrams for the Crypto Quantitative Research Platform live here.

- **Source**: PlantUML (`.puml`) or C4.
- **Exports**: SVG and PNG for docs and presentations.
- **Keep aligned with code**: When architecture changes (providers, chain, resilience, DB), update diagrams when explicitly requested; see project rule "Docs as Source of Truth → Diagrams".

To generate SVG/PNG from PlantUML (if Java and PlantUML jar are installed):

```bash
java -jar plantuml.jar -tsvg -tpng docs/diagrams/*.puml
```

Or use the VS Code "PlantUML" extension and "Export current diagram".
