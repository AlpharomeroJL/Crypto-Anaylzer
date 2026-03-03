## Cursor Cloud specific instructions

### Services overview

This is a single-process, local-first Python application backed by SQLite. No external services, Docker, or API keys are required.

| Service | How to run | Notes |
|---|---|---|
| CLI | `source .venv/bin/activate && python -m crypto_analyzer <command>` | See `python -m crypto_analyzer --help` for all commands |
| Tests | `python -m pytest -m "not slow" -q --tb=short` | 600+ tests, all mocked HTTP, no network |
| Lint | `python -m ruff check .` and `python -m ruff format --check .` | Config in `pyproject.toml` |
| Doctor (CI) | `python -m crypto_analyzer doctor --ci` | No-network preflight |
| Smoke (CI) | `CRYPTO_ANALYZER_NO_NETWORK=1 python -m crypto_analyzer smoke --ci` | Validates migrations, dataset_id_v2, run identity |

### Key gotchas

- **`crypto_analyzer/artifacts.py` was accidentally deleted from the repo.** It must be restored (from git history at `e4cab3d^:crypto_analyzer/artifacts.py`) for the package to build or import. The update script handles this automatically via `git show`. Without this file, `pip install -e .` and all imports fail with `ModuleNotFoundError: No module named 'crypto_analyzer.artifacts'`.
- **`uv sync` does not work** because the build requires importing `crypto_analyzer/__init__.py` which pulls in numpy/pandas before they are installed. Use `pip install -r requirements.txt && pip install --no-build-isolation -e ".[dev]"` instead.
- **Activate the venv** before running any commands: `source .venv/bin/activate`. The `.venv` is at repo root.
- **All scripts in `scripts/` are PowerShell (`.ps1`)** — they don't work on Linux. Use `python -m crypto_analyzer <command>` directly.
- The `test_profiling_on_timings_written` test is flaky when run in the full suite but passes in isolation.
- For standard CLI commands and testing tiers, see the README `## Development / Verification` section.
