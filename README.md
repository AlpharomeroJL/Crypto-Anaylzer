# Crypto-Analyzer

A local crypto/DEX analytics stack: a **poller** writes DEX and spot price data into SQLite, and a **Streamlit dashboard** (and optional analyzer scripts) read from that DB for charts and analysis.

## Prerequisites

- **Python 3.10+**
- **PowerShell** (for the suggested commands; adjust for your OS/shell if needed)

## 1. Clone and set up the environment

```powershell
git clone <your-repo-url>
cd Crypto-Anaylzer
```

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

Optional: install `st-keyup` for keyboard shortcuts in the dashboard (e.g. theme toggle). The app works without it.

```powershell
pip install st-keyup
```

## 2. Run the poller (to populate data)

The poller fetches DEX pair and spot prices and writes them to `dex_data.sqlite` in the repo root. Run it from the repo directory so the DB is created there:

```powershell
cd Crypto-Anaylzer
.\.venv\Scripts\Activate
python dex_poll_to_sqlite.py --interval 60
```

Leave it running (or run it as a Windows service; see docs in the repo). It creates `dex_data.sqlite` and the tables on first run. Use `Ctrl+C` to stop.

To write logs to a file:

```powershell
python dex_poll_to_sqlite.py --interval 60 --log-file "C:\ProgramData\CryptoAnalyzer\poller.log"
```

## 3. Run the dashboard

From the repo root with the same venv activated:

```powershell
python -m streamlit run dashboard.py --server.port 8501
```

Or use the helper script (edit the path inside if your clone is elsewhere):

```powershell
.\run_dashboard.ps1
```

Then open **http://localhost:8501** in your browser.

- **SQLite DB path:** In the sidebar, set the path to your `dex_data.sqlite`. If you run the dashboard from the repo root, you can use the full path to your clone, e.g. `C:\Users\You\...\Crypto-Anaylzer\dex_data.sqlite`, or a relative path like `dex_data.sqlite` when the working directory is the repo.
- Use **Reload data** in the sidebar after the poller has written new data (or after a reset).
- Turn on **Auto-refresh** to update the charts periodically.

## 4. Optional: clear or reset data

- **Clear all table data (keep DB file):** Run while the poller is stopped. Then start the poller again and use **Reload data** in the dashboard.
  ```powershell
  python clear_db_data.py
  ```
- **Full reset (archive DB + plots, delete, restart poller):** Use the script if you have NSSM and the CryptoPoller service installed. Run PowerShell as Administrator.
  ```powershell
  .\reset_data.ps1
  ```

## Project layout (main pieces)

| Path | Purpose |
|------|--------|
| `dashboard.py` | Streamlit app: charts, metrics, theme/settings. |
| `dex_poll_to_sqlite.py` | Poller: fetches DEX + spot data, writes to SQLite. |
| `analyze_from_sqlite.py` | CLI/analysis using the same DB. |
| `clear_db_data.py` | Deletes all rows in DB tables for a fresh dataset. |
| `reset_data.ps1` | Stops poller, archives DB/plots, deletes them, restarts poller (Windows + NSSM). |
| `run_dashboard.ps1` | Starts Streamlit (edit path if needed). |
| `dex_data.sqlite` | Created by the poller; used by dashboard and analyzer. |

## Docs in the repo

- **DEPLOY.md** – Deployment and running the dashboard in production.
- **HANDOFF_AUTOPOLLING.md** – Poller and NSSM service setup.
- **WINDOWS_24_7.md** – Running the poller 24/7 on Windows.

## License

See the repository for license information.
