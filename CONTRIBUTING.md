# Contributing

Contributions that keep the repository research-grade and maintainable are welcome. This repo is **research-only** — no execution, order routing, or trading keys.

---

## Code Style

- **Python:** Follow PEP 8. Use consistent formatting (e.g. Black or project defaults). Type hints encouraged for public APIs.
- **Imports:** Prefer standard library, then third-party, then local. Avoid unused imports.
- **Docstrings:** Public modules, classes, and functions should have clear docstrings; no need for hype or marketing language.

---

## Testing

- **Scope:** New logic that affects research outputs (returns, factors, portfolio, validation) should have tests.
- **Runner:** `python -m pytest tests/ -q` (or `-v --tb=short` for debugging). The sanity check script runs this as part of system health.
- **No execution:** Tests must not call exchange APIs, place orders, or use live trading credentials. Use fixtures, mocks, or existing SQLite test data only.

---

## Research-Only Boundary

This repository is **research-only**. Do not add:

- Order routing or execution code
- Exchange or broker API keys or live trading hooks
- Code that sends trades or modifies positions

Signals, backtests, and reports are for study and validation. Any deployment or execution layer belongs outside this repo.

---

## Commit Messages

Use present tense, imperative; one short subject line. Examples:

- **Add** universe churn audit table and check_universe.py
- **Fix** doctor exit code when DB is missing
- **Document** run.ps1 commands in README Quickstart

Optionally reference an issue in the body. Keep history readable for collaborators and future you.

---

## Pull Requests

- Keep changes focused. If possible, separate refactors from feature work.
- Ensure `python sanity_check.py` and `python -m pytest tests/` pass before submitting.
