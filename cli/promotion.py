"""Compatibility shim: use crypto-analyzer promotion or python -m crypto_analyzer promotion."""

from crypto_analyzer.cli.promotion import main

if __name__ == "__main__":
    raise SystemExit(main())
