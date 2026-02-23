"""Compatibility shim: use crypto-analyzer api or python -m crypto_analyzer api."""

from crypto_analyzer.cli.api import main

if __name__ == "__main__":
    raise SystemExit(main())
