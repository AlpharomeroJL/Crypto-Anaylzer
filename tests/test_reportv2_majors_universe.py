"""reportv2 --universe majors validation."""

from __future__ import annotations

from crypto_analyzer.cli import reportv2 as reportv2_mod


def test_reportv2_majors_requires_1h_freq() -> None:
    rc = reportv2_mod.main(["--universe", "majors", "--freq", "5min", "--out-dir", "."])
    assert rc == 1
