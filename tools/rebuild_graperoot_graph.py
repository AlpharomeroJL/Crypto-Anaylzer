#!/usr/bin/env python3
"""Rebuild `.dual-graph/info_graph.json` with repo `.graperootignore` prunes.

GrapeRoot's launcher (`graperoot`, `dgc`) calls upstream `graph_builder` without
reading `.graperootignore`. Run this script for a canonical, higher-signal graph:

  python tools/rebuild_graperoot_graph.py

Requires the `graperoot` package (e.g. `pip install graperoot` in this project's
`.venv`, or GrapeRoot's `~/.dual-graph/venv`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _repo_root() -> Path:
    return _REPO_ROOT


def _graperoot_python() -> Path | None:
    p = Path.home() / ".dual-graph" / "venv" / "Scripts" / "python.exe"
    return p if p.is_file() else None


def _ensure_graperoot_import() -> None:
    try:
        import graperoot.graph_builder  # noqa: F401, PLC0415
    except ImportError:
        alt = _graperoot_python()
        if alt and Path(sys.executable).resolve() != alt.resolve():
            r = subprocess.run([str(alt), *sys.argv], cwd=os.getcwd(), check=False)
            raise SystemExit(r.returncode)
        print(
            "graperoot is not installed. Install with:\n"
            "  .venv\\Scripts\\python -m pip install graperoot\n"
            "or use GrapeRoot's venv: ~/.dual-graph/venv",
            file=sys.stderr,
        )
        raise SystemExit(1)


def main() -> int:
    _ensure_graperoot_import()
    import graperoot.graph_builder as gb  # noqa: PLC0415
    try:
        import graperoot.graph_builder_ast as gba  # noqa: PLC0415
    except ImportError:
        gba = None

    parser = argparse.ArgumentParser(description="Rebuild GrapeRoot info_graph with .graperootignore.")
    parser.add_argument("--root", type=Path, default=None, help="Project root (default: repo root).")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON (default: <root>/.dual-graph/info_graph.json).",
    )
    args = parser.parse_args()
    root = (args.root or _repo_root()).resolve()
    out_path = (args.out or (root / ".dual-graph" / "info_graph.json")).resolve()

    from tools.graperoot_ignore import parse_graperootignore  # noqa: E402, PLC0415

    extra = parse_graperootignore(root)
    gb.SKIP_DIRS.update(extra)
    if gba is not None:
        gba.SKIP_DIRS.update(extra)

    existing_nodes: dict = {}
    if out_path.exists():
        try:
            old_graph = json.loads(out_path.read_text(encoding="utf-8-sig"))
            existing_nodes = {n["id"]: n for n in old_graph.get("nodes", []) if n.get("kind") == "file"}
        except Exception:
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph = gb.scan(root, existing_nodes=existing_nodes or None)
    out_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    sym_index = {
        node["id"]: {
            "line_start": node["line_start"],
            "line_end": node["line_end"],
            "body_hash": node["body_hash"],
            "confidence": node.get("confidence", ""),
            "path": node["path"],
        }
        for node in graph["nodes"]
        if node.get("kind") == "symbol"
    }
    sym_path = out_path.parent / "symbol_index.json"
    sym_path.write_text(json.dumps(sym_index), encoding="utf-8")

    print(
        f"Scanned: {graph['file_count']} files, {graph['symbol_count']} symbols, {graph['edge_count']} edges\n"
        f"Wrote: {out_path}\n"
        f"Symbol index: {sym_path} ({len(sym_index)} symbols)\n"
        f"SKIP_DIRS extras from .graperootignore: {sorted(extra)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
