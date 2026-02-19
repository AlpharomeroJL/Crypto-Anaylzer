---
name: commit-push
description: Produce a conventional commit message and PR description (deterministic text output). Use when the user asks for a clean commit, commit message, push description, PR description, or release summary. Output is copy-paste text only; do not imply the agent can push to remote.
---

# Commit and PR Description

## When to Use
- User asks for: clean commit, commit message, push description, PR description, or release/changelog summary.
- Output is **text only** for the user to copy-paste (e.g. into GitHub Desktop or PR body). Do not state that the agent will push; the user pushes.

## Workflow
1. Run (or ask user to confirm): `git status` to see what will be committed.
2. Run verification: `python -m pytest -q`, `ruff check .` (and optionally `.\scripts\run.ps1 doctor`). Record pass/fail.
3. Compose the outputs below from the changed files and verification results.

## Output Template (Always Include)

### 1. Git status expectation
- Short sentence: what will be committed (e.g. "27 files changed, 3,050 insertions, 235 deletions" or "2 files: .cursor/rules/project-context.mdc, .cursor/skills/commit-push/SKILL.md").

### 2. Commands run + pass/fail
| Command | Result |
|---------|--------|
| `python -m pytest -q` | … |
| `ruff check .` | … |
| (optional) `.\scripts\run.ps1 doctor` | … |

### 3. Conventional commit
- **Title** (one line): `type(scope): short description` (e.g. `feat(providers): add provider architecture with CEX/DEX plugin system`).
- **Body**: 1–3 sentences explaining what and why; wrap at ~72 chars.

### 4. Changelog bullets (for PR description or release notes)
- 3–8 bullets: what changed from a user/reader perspective (features, fixes, docs, tests).

### 5. Risk / rollback note
- One short paragraph: how to roll back or what to watch (e.g. "Rollback: revert commit and re-run migrations if schema changed. Watch: provider health in dashboard after deploy."). MBSE and hiring managers value this.

## Example (concise)
**Git status:** 5 files (rules + skills).  
**Commands:** pytest 200 passed; ruff all checks passed.  
**Commit:** `docs(cursor): add project rules and commit-push skill`  
**Body:** Add .cursor rules (project context, Python/providers, tests) and commit-push skill for conventional commit + PR description output.  
**Changelog:** • Project rules: decision defaults, do-not-touch, verification commands • Commit-push skill: commit title/body, changelog bullets, risk note  
**Risk:** None; rules/skills are additive. Rollback: remove .cursor/rules/*.mdc and .cursor/skills/commit-push if desired.
