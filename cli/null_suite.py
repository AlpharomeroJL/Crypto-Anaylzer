"""Compatibility shim: use crypto-analyzer null_suite or python -m crypto_analyzer null_suite."""

from crypto_analyzer.cli.null_suite import main

if __name__ == "__main__":
    raise SystemExit(main())
