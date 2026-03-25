"""Sync shared AI skills into tool-specific locations.

This repo keeps canonical skill definitions under ``ai/skills`` and mirrors them
into ``.cursor/skills``. The same source can also be copied into ``CODEX_HOME``
so Codex and Cursor use identical repo-specific instructions.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "ai" / "skills"
CURSOR_ROOT = REPO_ROOT / ".cursor" / "skills"
ROOT_SKILL_ALIASES = {
    "portfolio-audit": REPO_ROOT / "SKILL.md",
}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
DESCRIPTION_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)
SKILL_DIR_RE = re.compile(r"^[a-z0-9-]+$")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    source_path: Path
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that generated targets already match the canonical skills.",
    )
    parser.add_argument(
        "--install-codex",
        action="store_true",
        help="Copy the canonical skills into the user's Codex skills directory.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        help="Override CODEX_HOME when using --install-codex.",
    )
    return parser.parse_args()


def load_skill(skill_dir: Path) -> Skill:
    if not SKILL_DIR_RE.match(skill_dir.name):
        raise ValueError(f"Invalid skill directory name: {skill_dir.name}")
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise ValueError(f"Missing SKILL.md in {skill_dir}")

    text = skill_path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{skill_path} is missing YAML frontmatter")

    frontmatter = match.group(1)
    name_match = NAME_RE.search(frontmatter)
    description_match = DESCRIPTION_RE.search(frontmatter)
    if not name_match or not description_match:
        raise ValueError(f"{skill_path} must define name and description")

    name = name_match.group(1).strip()
    description = description_match.group(1).strip()
    if name != skill_dir.name:
        raise ValueError(f"{skill_path} name '{name}' must match directory '{skill_dir.name}'")

    return Skill(name=name, description=description, source_path=skill_path, text=text)


def iter_skills() -> list[Skill]:
    if not SOURCE_ROOT.exists():
        raise ValueError(f"Missing canonical skills directory: {SOURCE_ROOT}")

    skills = [load_skill(path) for path in sorted(SOURCE_ROOT.iterdir()) if path.is_dir()]
    if not skills:
        raise ValueError(f"No skills found under {SOURCE_ROOT}")
    return skills


def write_if_needed(target_path: Path, text: str, check: bool) -> bool:
    current = target_path.read_text(encoding="utf-8") if target_path.exists() else None
    if current == text:
        return False
    if check:
        raise ValueError(f"Out of sync: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(text, encoding="utf-8", newline="\n")
    return True


def default_codex_home() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home)
    return Path.home() / ".codex"


def sync_cursor(skills: list[Skill], check: bool) -> int:
    changes = 0
    for skill in skills:
        target = CURSOR_ROOT / skill.name / "SKILL.md"
        changes += int(write_if_needed(target, skill.text, check))
    return changes


def sync_root_aliases(skills: list[Skill], check: bool) -> int:
    changes = 0
    by_name = {skill.name: skill for skill in skills}
    for skill_name, alias_path in ROOT_SKILL_ALIASES.items():
        skill = by_name.get(skill_name)
        if skill is None:
            raise ValueError(f"Root alias points to missing canonical skill: {skill_name}")
        changes += int(write_if_needed(alias_path, skill.text, check))
    return changes


def sync_codex(skills: list[Skill], codex_home: Path, check: bool) -> int:
    codex_root = codex_home / "skills"
    changes = 0
    for skill in skills:
        target = codex_root / skill.name / "SKILL.md"
        changes += int(write_if_needed(target, skill.text, check))
    return changes


def main() -> int:
    args = parse_args()
    skills = iter_skills()

    changes = 0
    changes += sync_cursor(skills, check=args.check)
    changes += sync_root_aliases(skills, check=args.check)

    if args.install_codex:
        codex_home = args.codex_home or default_codex_home()
        changes += sync_codex(skills, codex_home=codex_home, check=args.check)

    if args.check:
        print(f"Shared skills are in sync across {len(skills)} skill(s).")
    else:
        print(f"Synced {len(skills)} shared skill(s). Updated {changes} file(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
