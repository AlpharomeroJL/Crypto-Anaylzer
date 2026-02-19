"""Allow python -m crypto_analyzer to print help."""
from __future__ import annotations

from . import __version__

_HELP = f"""\
crypto-analyzer {__version__}

Available CLI commands (run from repo root):
  .\\scripts\\run.ps1 doctor       Preflight system checks
  .\\scripts\\run.ps1 poll         Poll DEX/spot prices (provider chain)
  .\\scripts\\run.ps1 universe-poll --universe  Auto-discover DEX pairs
  .\\scripts\\run.ps1 materialize  Build OHLCV bars from snapshots
  .\\scripts\\run.ps1 reportv2     Research report with overfitting controls
  .\\scripts\\run.ps1 streamlit    Interactive dashboard (12 pages)
  .\\scripts\\run.ps1 api          Local research API (FastAPI)
  .\\scripts\\run.ps1 demo         One-command demo

Or directly:
  python cli/poll.py             Data ingestion (Coinbase -> Kraken fallback)
  python cli/app.py              Streamlit dashboard
  python cli/scan.py             Opportunity scanner
  python -m pytest -q            Run test suite (200 tests)

Installed as package:
  crypto-analyzer                This help message
"""


def main() -> int:
    print(_HELP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
