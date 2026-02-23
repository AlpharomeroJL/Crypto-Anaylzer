"""Compatibility shim: use crypto-analyzer walkforward or python -m crypto_analyzer walkforward."""

from crypto_analyzer.cli.walkforward import main

if __name__ == "__main__":
    raise SystemExit(main())
