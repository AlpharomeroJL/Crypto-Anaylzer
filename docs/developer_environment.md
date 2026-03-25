# Developer Environment

This repo now has a shared development setup for shell, Cursor, VS Code, and Codex.

## Goals

- Keep one source of truth for repo-specific AI skills
- Make Cursor and Codex use the same skill content
- Make common setup, test, lint, and verification commands easy to run from the editor
- Reduce noise from generated artifacts, SQLite files, caches, and bundled diagram binaries

## Recommended Setup

### 1. Create the environment

Recommended:

```powershell
uv sync --frozen
```

Fallback:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,ui]"
```

### 2. Open the repo in Cursor or VS Code

The committed `.vscode/` folder is shared by VS Code and Cursor, so both editors pick up:

- interpreter selection for `.venv`
- pytest defaults
- Ruff formatting
- common tasks
- debug launch entries
- search and watcher excludes for generated artifacts
- PlantUML settings for in-repo diagram tooling

### 3. Sync shared AI skills

Canonical skill definitions live in `ai/skills/`.

Sync them into Cursor and the repo root alias with:

```powershell
.venv\Scripts\python.exe .\tools\sync_ai_skills.py
```

That updates:

- `.cursor/skills/<skill>/SKILL.md`
- root `SKILL.md` for the `portfolio-audit` compatibility alias

### 4. Install the same skills for Codex

To copy the shared skills into Codex's skill directory:

```powershell
.venv\Scripts\python.exe .\tools\sync_ai_skills.py --install-codex
```

By default this targets:

- `%CODEX_HOME%\skills` if `CODEX_HOME` is set
- otherwise `%USERPROFILE%\.codex\skills`

## Shared Skill Layout

- Canonical source: `ai/skills/`
- Cursor mirror: `.cursor/skills/`
- Codex install target: `%CODEX_HOME%\skills` or `%USERPROFILE%\.codex\skills`

Edit only the canonical files under `ai/skills/`, then run the sync script.

## Useful Editor Tasks

Open the command palette and run `Tasks: Run Task` for:

- `Setup: uv sync --frozen`
- `Setup: create .venv`
- `Setup: pip install -e .[dev,ui]`
- `Doctor`
- `Verify`
- `Test: default`
- `Test: full`
- `Lint: ruff check`
- `Format: ruff format`
- `AI: sync shared skills`
- `AI: install shared skills in Codex`

## Useful Debug Entries

- `Crypto Analyzer: doctor`
- `Crypto Analyzer: smoke --ci`
- `Pytest: current file`

## Notes

- `.editorconfig` normalizes whitespace and line endings across editors.
- `.vscode/settings.json` hides generated outputs from search and file watching, which keeps the workspace responsive.
- `*.mdc` files are associated with Markdown so Cursor rules are easy to edit.

