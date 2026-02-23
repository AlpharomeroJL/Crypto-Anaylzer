#!/usr/bin/env python3
"""Compatibility shim: use crypto-analyzer check-dataset or python -m crypto_analyzer check-dataset."""

from crypto_analyzer.cli.check_dataset import main

if __name__ == "__main__":
    raise SystemExit(main())
