# Deployment (Windows)

Use the **full path** to `nssm.exe` (e.g. `C:\nssm\win64\nssm.exe`). Run PowerShell **as Administrator** when installing or changing services.

---

## CryptoPoller (24/7 data poller)

**NSSM runs venv Python directly** (no wrapper scripts). In NSSM set:

| Field | Value |
|-------|--------|
| **Application** | `C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer\.venv\Scripts\python.exe` |
| **Arguments** | `-u dex_poll_to_sqlite.py --interval 60 --log-file C:\ProgramData\CryptoAnalyzer\poller.log` |
| **Startup directory** | `C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer` |

**Log:** Python writes to `C:\ProgramData\CryptoAnalyzer\poller.log`. Tail with:
```powershell
Get-Content "C:\ProgramData\CryptoAnalyzer\poller.log" -Wait
```

**Control:**
```powershell
& "C:\nssm\win64\nssm.exe" start   CryptoPoller
& "C:\nssm\win64\nssm.exe" stop    CryptoPoller
& "C:\nssm\win64\nssm.exe" restart CryptoPoller
& "C:\nssm\win64\nssm.exe" status  CryptoPoller
```

---

## CryptoAnalyzer (Streamlit dashboard)

- **Application:** `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
- **Arguments:** `-ExecutionPolicy Bypass -File "C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer\run_dashboard.ps1"`
- **Startup directory:** `C:\Users\jo312\OneDrive\Desktop\Github Projects\Crypto-Anaylzer`

Dashboard: http://localhost:8501

---

## NSSM reference

- Install (GUI): `nssm install CryptoPoller` then fill Application/Arguments/Directory
- Edit: `nssm edit CryptoPoller`
- Remove: `nssm remove CryptoPoller confirm`
