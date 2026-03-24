"""Canonical default artifact directories for report CLIs."""

from __future__ import annotations

from crypto_analyzer.cli.report import DEFAULT_REPORT_OUT_DIR
from crypto_analyzer.cli.reportv2 import DEFAULT_REPORTV2_OUT_DIR


def test_report_default_out_dir_constant() -> None:
    assert DEFAULT_REPORT_OUT_DIR == "reports/report"


def test_reportv2_default_out_dir_constant() -> None:
    assert DEFAULT_REPORTV2_OUT_DIR == "reports/reportv2"
