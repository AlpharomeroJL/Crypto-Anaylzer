#!/usr/bin/env python3
"""
Scan README.md and docs/**/*.md for relative Markdown links; validate file targets exist.
Ignores http/https/mailto. Strip anchors (#...) for existence check.
Do not add as dependency; stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path


def iter_md_files(root: Path):
    """README.md and docs/**/*.md."""
    readme = root / "README.md"
    if readme.exists():
        yield readme
    docs = root / "docs"
    if docs.exists():
        for p in docs.rglob("*.md"):
            yield p


# Match markdown links: [text](url). Capture url.
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def iter_relative_links(path: Path, root: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, url) for links that look relative (no scheme, or start with ./, ../, docs/)."""
    results = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return results
    for i, line in enumerate(text.splitlines(), 1):
        for _label, url in LINK_RE.findall(line):
            url = url.strip()
            if not url or url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:"):
                continue
            base = url.split("#")[0].strip()
            if not base or base.endswith("/") or "..." in base or "/foo." in base:
                continue  # skip placeholders like components/..., components/foo.md
            if (
                base.startswith("./")
                or base.startswith("../")
                or base.startswith("docs/")
                or base.endswith(".md")
                or "/" in base
            ):
                results.append((i, url))
    return results


def resolve_target(source: Path, url: str, root: Path) -> Path | None:
    """Resolve link target to absolute path. Strip anchor. Return None if not file."""
    base = url.split("#")[0].strip()
    if not base:
        return source  # same-file anchor
    if base.startswith("docs/"):
        target = root / base
    else:
        target = (source.parent / base).resolve()
    try:
        return target.resolve() if target.exists() else None
    except Exception:
        return None


def main():
    root = Path(__file__).resolve().parent.parent
    missing = []
    for md in iter_md_files(root):
        rel = md.relative_to(root) if root in md.resolve().parents else md.name
        for line_no, url in iter_relative_links(md, root):
            base = url.split("#")[0].strip()
            if not base:
                continue
            if base.startswith("docs/"):
                target = root / base
            else:
                target = (md.parent / base).resolve()
            if not target.exists():
                try:
                    target = target.resolve()
                except Exception:
                    pass
                if not target.exists():
                    missing.append((str(rel), line_no, url))
    for rel, line_no, url in sorted(missing):
        print(f"{rel}:{line_no}: missing target: {url}")
    return 1 if missing else 0


if __name__ == "__main__":
    exit(main())
