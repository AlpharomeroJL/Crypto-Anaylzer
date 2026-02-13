# CryptoPoller: NSSM service and logs (minimal config)

Service name: **CryptoPoller**. NSSM runs venv Python directly (no wrappers).

## Working NSSM configuration

Set these in NSSM (e.g. `nssm edit CryptoPoller` or at install):

| Field | Value |
|-------|--------|
| **Application** | `C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer\.venv\Scripts\python.exe` |
| **Parameters** | `-u dex_poll_to_sqlite.py --interval 60 --log-file C:\ProgramData\CryptoAnalyzer\poller.log` |
| **AppDirectory** | `C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer` |

- **`-u`** = unbuffered stdout/stderr so logs are live.
- **`--log-file`** = Python appends all output to that path (works when run as Local System).
- **AppDirectory** = working directory so the poller finds `dex_data.sqlite` in the repo and writes there.

## Log paths (outside repo)

- **Stdout / main log:** `C:\ProgramData\CryptoAnalyzer\poller.log`
- **Stderr:** NSSM can redirect stderr to `C:\ProgramData\CryptoAnalyzer\poller_error.log` in the NSSM GUI (I/O tab) if desired; otherwise errors go to the same log via Python’s `_log()`.

Tail the main log:
```powershell
Get-Content "C:\ProgramData\CryptoAnalyzer\poller.log" -Wait
```

## Poller reliability

- `dex_poll_to_sqlite.py` uses `print(..., flush=True)` and `_log_file.flush()` so output is not buffered.
- NSSM restarts the process if it exits; run Python with `-u` so logs are live.

## Control (PowerShell as Administrator)

```powershell
& "C:\nssm\win64\nssm.exe" start   CryptoPoller
& "C:\nssm\win64\nssm.exe" stop    CryptoPoller
& "C:\nssm\win64\nssm.exe" restart CryptoPoller
& "C:\nssm\win64\nssm.exe" status  CryptoPoller
```

## Fresh start (reset data)

Run as Administrator:
```powershell
cd "C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer"
.\reset_data.ps1
```
Stops the service, archives `dex_data.sqlite` and `plots/` to `./archive/YYYY-MM-DD_HH-mm/`, removes them from the repo root, restarts the service. Dashboard and analyzer keep using the DB path in repo root (new DB created by poller).
