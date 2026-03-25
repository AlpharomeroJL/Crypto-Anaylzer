---
name: repo-workflow
description: Repo-wide workflow guide for working on Crypto-Analyzer. Use when implementing, debugging, refactoring, reviewing, documenting, or verifying changes in this repo and you need the project constraints, architecture boundaries, preferred commands, and finish checklist. This skill is intended to work in both Codex and Cursor.
---

# Repo Workflow

## Hard Constraints
- Keep SQLite as the single source of truth.
- Do not add API keys or authenticated endpoints.
- Keep tests offline with mocked HTTP.
- Add minimal dependencies and justify any new one.
- Preserve backward compatibility or provide migrations and upgrade notes.

## Decision Defaults
- Prefer minimal diffs over opportunistic cleanup.
- Keep analytics and research logic pure when possible.
- Keep side effects in `db/`, `store/`, `providers/`, and `cli/` layers.
- If a change affects architecture boundaries, call that out explicitly in the final output.

## Canonical Commands
- Preferred setup: `uv sync --frozen`
- Preferred entrypoint: `.\scripts\run.ps1 <command> [args...]`
- Default tests: `uv run python -m pytest -m "not slow and not network" -q --tb=short`
- Full verification: `.\scripts\run.ps1 verify`
- Lint: `uv run ruff check crypto_analyzer cli tests tools`

## Source Of Truth Docs
- `CONTRIBUTING.md` for setup, style, and provider extension workflow
- `docs/design.md` and `docs/architecture.md` for architecture and boundaries
- `docs/research_validation_workflow.md` for report and case-study execution flow
- `docs/spec/` for canonical implementation expectations

## Before Finishing
- List files changed
- List exact commands to run
- Say what success looks like in the output

