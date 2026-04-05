"""Parse `.graperootignore` for GrapeRoot graph_builder directory pruning.

GrapeRoot's bundled `graph_builder.py` only exposes a fixed `SKIP_DIRS` set (see
`graperoot.graph_builder.SKIP_DIRS`). It does not read `.gitignore`. This module
parses one directory basename per line so we can merge extra prunes without
forking upstream.

Semantics match `SKIP_DIRS`: any *directory name* equal to an entry is skipped
during `os.walk` (same as skipping `.git` or `node_modules`).
"""

from __future__ import annotations

from pathlib import Path

# Used when `.graperootignore` is missing (e.g. fresh clone) so behavior stays predictable.
DEFAULT_GRAPEROOT_EXCLUDES: frozenset[str] = frozenset(
    {
        ".claude",
        ".cursor",
        "reports",
        "artifacts",
        "plots",
        "out_exec_evidence",
        "logs",
        "archive",
        "tmp_rerun_1",
        "tmp_rerun_2",
        "tmp_profile_off",
        "tmp_profile_on",
        "crypto_analyzer.egg-info",
        ".pytest_cache",
        ".ruff_cache",
        "graphviz",
    }
)


def parse_graperootignore(repo_root: Path) -> frozenset[str]:
    """Return directory basenames to prune. Empty or missing file → defaults."""
    path = repo_root / ".graperootignore"
    if not path.is_file():
        return DEFAULT_GRAPEROOT_EXCLUDES
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if not line:
            continue
        # Only basename rules (matches upstream walk pruning).
        name = line.replace("\\", "/").rstrip("/").split("/")[-1].strip()
        if name:
            out.add(name)
    return frozenset(out) if out else DEFAULT_GRAPEROOT_EXCLUDES
