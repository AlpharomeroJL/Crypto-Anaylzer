"""Allow python -m crypto_analyzer to print help."""
from __future__ import annotations

from . import __version__

_HELP = f"""\
crypto-analyzer {__version__}

Available CLI commands (run from repo root):
  python cli/app.py              Streamlit dashboard
  python cli/scan.py             Scanner: top opportunities
  python cli/poll.py             Poll DEX / spot prices into SQLite
  python cli/materialize.py      Materialize resampled OHLCV bars
  python cli/research_report_v2.py  Research report (milestone 4)
  python cli/api.py              Launch REST research API
  python cli/backtest.py         Backtest runner
  python cli/analyze.py          Analyze pair data

Or via PowerShell runner:
  .\\scripts\\run.ps1 <command>

Installed as package:
  crypto-analyzer                This help message
"""


def main() -> int:
    print(_HELP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
