"""Compatibility shim: use crypto-analyzer analyze or python -m crypto_analyzer analyze."""

from crypto_analyzer.cli.analyze import main

if __name__ == "__main__":
    raise SystemExit(main())
