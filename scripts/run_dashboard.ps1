# Legacy dashboard launcher. Prefer: .\scripts\run.ps1 streamlit
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
Set-Location $root
& $py -m streamlit run cli/app.py --server.address 0.0.0.0 --server.port 8501
