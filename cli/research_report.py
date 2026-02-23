"""Compatibility shim: use crypto-analyzer report or python -m crypto_analyzer report."""

from crypto_analyzer.cli.report import main

if __name__ == "__main__":
    raise SystemExit(main())
