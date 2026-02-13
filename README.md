# Crypto-Analyzer

A local crypto/DEX analytics stack: a **poller** writes DEX and spot price data into SQLite, and a **Streamlit dashboard** (and optional analyzer scripts) read from that DB for charts and analysis.

## Prerequisites

- **Python 3.10+**
- A shell: **PowerShell** (Windows), **Terminal/zsh** (macOS), or **bash** (Pop!_OS / Linux)

---

## 1. Clone and set up the environment

```bash
git clone <your-repo-url>
cd Crypto-Anaylzer
```

Create a virtual environment and install dependencies.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

**macOS / Pop!_OS (Linux) — bash or zsh:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional: install `st-keyup` for keyboard shortcuts in the dashboard. The app works without it.

```bash
pip install st-keyup
```

---

## 2. Run the poller (to populate data)

The poller writes to `dex_data.sqlite` in the repo root. Run it from the repo directory.

**Windows (PowerShell):**

```powershell
cd Crypto-Anaylzer
.\.venv\Scripts\Activate
python dex_poll_to_sqlite.py --interval 60
```

**macOS / Pop!_OS (Linux):**

```bash
cd Crypto-Anaylzer
source .venv/bin/activate
python dex_poll_to_sqlite.py --interval 60
```

Leave it running (or run it as a service; see docs). It creates `dex_data.sqlite` and tables on first run. Use `Ctrl+C` to stop.

**Optional — log to a file:**

- Windows: `--log-file "C:\ProgramData\CryptoAnalyzer\poller.log"`
- macOS / Linux: `--log-file /var/log/crypto-analyzer/poller.log` (create the directory first if needed)

---

## 3. Run the dashboard

From the repo root with the same venv activated.

**Windows (PowerShell):**

```powershell
python -m streamlit run dashboard.py --server.port 8501
```

Or use the helper script (edit the path inside if your clone is elsewhere):

```powershell
.\run_dashboard.ps1
```

**macOS / Pop!_OS (Linux):**

```bash
python -m streamlit run dashboard.py --server.port 8501
```

Then open **http://localhost:8501** in your browser.

- **SQLite DB path:** In the sidebar, set the path to your `dex_data.sqlite`. From the repo root you can use a relative path: `dex_data.sqlite`. Or use the full path to your clone (e.g. `/Users/you/Crypto-Anaylzer/dex_data.sqlite` on macOS, `/home/you/Crypto-Anaylzer/dex_data.sqlite` on Pop!_OS).
- Use **Reload data** in the sidebar after the poller has written new data (or after a reset).
- Turn on **Auto-refresh** to update the charts periodically.

---

## 4. Optional: clear or reset data

The **dashboard never clears or deletes** your historical data; there is no clear button in the app. Clearing is only done by running the script below (with explicit `--yes`).

**Clear all table data (keep DB file)** — run while the poller is stopped, then start the poller again and refresh the dashboard (F5).

- `python clear_db_data.py` — dry run: shows row counts, does not delete.
- `python clear_db_data.py --yes` — **permanently** deletes all table data (use when you want a fresh dataset).

**Full reset (archive DB + plots, delete, restart poller):**

- **Windows:** Use `reset_data.ps1` if you have NSSM and the CryptoPoller service. Run PowerShell as Administrator: `.\reset_data.ps1`
- **macOS / Linux:** The provided `reset_data.ps1` is for Windows. To do a full reset manually: stop the poller, move or delete `dex_data.sqlite` and the `plots/` folder, then start the poller again.

---

## Project layout (main pieces)

| Path | Purpose |
|------|--------|
| `dashboard.py` | Streamlit app: charts, metrics, theme/settings. |
| `dex_poll_to_sqlite.py` | Poller: fetches DEX + spot data, writes to SQLite. |
| `analyze_from_sqlite.py` | CLI/analysis using the same DB. |
| `clear_db_data.py` | Clears all rows only when run with `--yes` (dashboard never clears data). |
| `reset_data.ps1` | Stops poller, archives DB/plots, restarts poller **(Windows + NSSM)**. |
| `run_dashboard.ps1` | Starts Streamlit **(Windows)**; on Mac/Linux run the `streamlit run` command above. |
| `dex_data.sqlite` | Created by the poller; used by dashboard and analyzer. |

---

## Docs in the repo

- **DEPLOY.md** – Deployment and running the dashboard in production.
- **HANDOFF_AUTOPOLLING.md** – Poller and NSSM service setup (Windows).
- **WINDOWS_24_7.md** – Running the poller 24/7 on Windows.

On **macOS** or **Pop!_OS**, you can run the poller in the background with `tmux`, `screen`, or a systemd user service (Linux) / launchd (macOS) instead of NSSM.

---

## License

See the repository for license information.
