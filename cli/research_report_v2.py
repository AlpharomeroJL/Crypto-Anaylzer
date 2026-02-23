"""Compatibility shim: use crypto-analyzer reportv2 or python -m crypto_analyzer reportv2."""

from crypto_analyzer.cli.reportv2 import main

if __name__ == "__main__":
    raise SystemExit(main())
