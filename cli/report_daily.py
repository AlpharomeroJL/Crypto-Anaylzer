"""Compatibility shim: use crypto-analyzer daily or python -m crypto_analyzer daily."""

from crypto_analyzer.cli.daily import main

if __name__ == "__main__":
    raise SystemExit(main())
