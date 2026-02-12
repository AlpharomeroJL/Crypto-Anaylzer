@echo off
REM Start the 10s poller (stop with Ctrl+C). After ~50 min run: python -u analyze_from_sqlite.py
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
python dex_poll_to_sqlite.py
pause
