#!/usr/bin/env python3
r"""
Normalize Markdown for GitHub rendering:
  1) Convert LaTeX-ish math delimiters to GitHub math:
       \( ... \)  -> $ ... $
       \[ ... \]  -> $$ ... $$
       \begin{align}...\end{align} -> $$\begin{aligned}...\end{aligned}$$
  2) Remove unnecessary backslash escapes in prose:
       \+ -> +, \= -> =, and list bullets \- -> - at line start.
  3) DOES NOT touch link labels like [\[1\]](...) (kept intentionally).
  4) Safe by default: only rewrites files under docs/ and README.md unless overridden.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

MATH_INLINE_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
# Do not match \[ when part of link label [\[1\]](url)
MATH_DISPLAY_RE = re.compile(r"(?<!\[)\\\[(.+?)\\\]", re.DOTALL)

# Common environments people paste from LaTeX.
ENV_ALIGN_RE = re.compile(
    r"\\begin\{align\*?\}(.+?)\\end\{align\*?\}",
    re.DOTALL,
)
ENV_EQUATION_RE = re.compile(
    r"\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}",
    re.DOTALL,
)

# "Unnecessary escapes" in normal prose.
# IMPORTANT: do not blindly replace "\[" or "\]" because those are also used in link labels [\[1\]].
PLUS_EQ_RE = re.compile(r"\\([+=])")

# Replace "\-" only when it's a list bullet at the start of a line (optionally preceded by spaces).
LIST_BULLET_RE = re.compile(r"(?m)^(?P<indent>\s*)\\-\s+")


def _convert_math(text: str) -> str:
    def _env_to_display(inner: str) -> str:
        inner = inner.strip()
        return "$$\\begin{aligned}\n" + inner + "\n\\end{aligned}$$"

    text = ENV_ALIGN_RE.sub(lambda m: _env_to_display(m.group(1)), text)
    text = ENV_EQUATION_RE.sub(lambda m: "$$" + m.group(1).strip() + "$$", text)

    text = MATH_DISPLAY_RE.sub(lambda m: "$$" + m.group(1).strip() + "$$", text)
    text = MATH_INLINE_RE.sub(lambda m: "$" + m.group(1).strip() + "$", text)
    return text


def _unescape_prose(text: str) -> str:
    # Convert '\-' bullets to '-' bullets (only at line start)
    text = LIST_BULLET_RE.sub(lambda m: f"{m.group('indent')}- ", text)

    # Convert '\+' and '\=' in prose.
    text = PLUS_EQ_RE.sub(lambda m: m.group(1), text)
    return text


def normalize_markdown(text: str) -> str:
    text2 = _convert_math(text)
    text2 = _unescape_prose(text2)
    return text2


def iter_targets(root: Path) -> Iterable[Path]:
    # Default scope: docs/**.md and README.md
    readme = root / "README.md"
    if readme.exists():
        yield readme
    docs = root / "docs"
    if docs.exists():
        for p in docs.rglob("*.md"):
            yield p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root (default: .)")
    ap.add_argument("--check", action="store_true", help="Exit non-zero if changes would be made")
    ap.add_argument("--paths", nargs="*", help="Optional explicit file paths to process")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    targets = [root / p for p in args.paths] if args.paths else list(iter_targets(root))

    changed = []
    for path in targets:
        if not path.exists() or path.is_dir():
            continue
        old = path.read_text(encoding="utf-8")
        new = normalize_markdown(old)
        if new != old:
            changed.append(path)
            if not args.check:
                path.write_text(new, encoding="utf-8")

    if args.check and changed:
        print("Would modify:")
        for p in changed:
            print(f"  - {p.relative_to(root)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
