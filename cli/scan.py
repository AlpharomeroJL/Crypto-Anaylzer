"""Compatibility shim: use crypto-analyzer scan or python -m crypto_analyzer scan."""

from crypto_analyzer.cli.scan import main

if __name__ == "__main__":
    raise SystemExit(main())
