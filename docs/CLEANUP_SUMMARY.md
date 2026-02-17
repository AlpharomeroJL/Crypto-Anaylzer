# Cleanup + fresh start + hardening summary

## Removed (and why)

| File | Reason |
|------|--------|
| `run_poller.bat` | Wrapper; NSSM runs venv Python directly. Manual run: `.\\.venv\\Scripts\\python.exe -u dex_poll_to_sqlite.py --interval 60` from repo root. |
| `ViewPollerLog.ps1` | Optional helper; tail with `Get-Content "C:\ProgramData\CryptoAnalyzer\poller.log" -Wait` (documented in HANDOFF/DEPLOY). |

No other disposable scripts were present (run_poller.ps1, launcher.bat, service_control.ps1, etc. had already been removed in a prior cleanup).

## Kept

- **Core:** `dex_poll_to_sqlite.py`, `dex_discover.py`, `analyze_from_sqlite.py`, `dashboard.py`, `check_db.py`
- **Docs:** `HANDOFF_AUTOPOLLING.md`, `DEPLOY.md`, `requirements.txt`
- **Helpers:** `run_dashboard.ps1` (used by dashboard NSSM service), `reset_data.ps1` (one-command fresh start)
- **Config:** `.gitignore` (updated)

## .gitignore

- Ignores: `.venv/`, `venv/`, `__pycache__/`, `plots/`, `logs/`, `archive/`, `*.sqlite`, `*.sqlite3`, `*.pyc`, `.streamlit/`, `.DS_Store`, `Thumbs.db`
- Documents that service logs live in `C:\ProgramData\CryptoAnalyzer\` (outside repo)

## Reset data (fresh start)

- **Script:** `reset_data.ps1` (run PowerShell as Administrator)
- Stops CryptoPoller, copies `dex_data.sqlite` and `plots/` to `./archive/YYYY-MM-DD_HH-mm/`, deletes them from repo root, restarts CryptoPoller.
- Dashboard/analyzer keep using the DB path in repo root; poller creates a new DB. No code loads from `archive/` unless you point the DB path there.

## Autopoller reliability

- NSSM **Parameters** use **`-u`** (unbuffered) and **`--log-file C:\ProgramData\CryptoAnalyzer\poller.log`**.
- Poller uses `print(..., flush=True)` and `_log_file.flush()`.
- **HANDOFF_AUTOPOLLING.md** has the minimal NSSM config (Application, Parameters, AppDirectory, log paths).

## Windows 24/7 (optional)

- **WINDOWS_24_7.md** added with:
  - (A) No auto-restart with logged-on users: Group Policy (gpedit) and registry fallback, step-by-step.
  - (B) Scheduled restart tasks: documentation only; no automatic changes.
- All steps optional and clearly marked; no sweeping registry edits.
