"""Compatibility shim: use crypto-analyzer dashboard or python -m crypto_analyzer dashboard."""

from crypto_analyzer.cli.dashboard import main

if __name__ == "__main__":
    raise SystemExit(main())
