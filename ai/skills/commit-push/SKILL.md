---
name: commit-push
description: Produce a conventional commit message and PR description for this repo. Use when the user asks for a clean commit, commit message, push summary, PR description, or release summary. Output text only and do not imply that the agent can push to a remote by itself.
---

# Commit And PR Description

## Workflow
1. Inspect `git status` so the commit scope is explicit.
2. Run or summarize verification status from `python -m pytest -q`, `ruff check .`, and optionally `.\scripts\run.ps1 doctor`.
3. Write the outputs below from the actual changed files and verification results.

## Output Template

### 1. Git status expectation
- One short sentence describing what will be committed.

### 2. Commands run and pass/fail
- Report each verification command and whether it passed.

### 3. Conventional commit
- Title format: `type(scope): short description`
- Body: 1-3 sentences describing what changed and why.

### 4. Changelog bullets
- Write 3-8 bullets describing the user-visible or reviewer-relevant changes.

### 5. Risk and rollback note
- Add one short paragraph describing rollback steps or what to watch after merge.

## Example Shape
- Git status: 5 files changed in rules and skills
- Commands: pytest passed, ruff passed
- Commit: `docs(cursor): add shared repo rules and skill sync`
- Risk: additive docs and tooling only; rollback is a normal revert

