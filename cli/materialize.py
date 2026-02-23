"""Compatibility shim: use crypto-analyzer materialize or python -m crypto_analyzer materialize."""

from crypto_analyzer.cli.materialize import main

if __name__ == "__main__":
    raise SystemExit(main())
