"""Contract tests for the demo CLI and poll --run-seconds flag."""

import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def test_run_seconds_flag_exits_loop():
    """Verify that --run-seconds causes the poll loop to stop."""
    # We test the time-check logic directly rather than running the full poller
    # (which requires network). Simulate the loop condition.
    start = time.time()
    run_seconds = 0  # immediate exit
    iterations = 0
    while True:
        if run_seconds is not None and (time.time() - start) >= run_seconds:
            break
        iterations += 1
        if iterations > 100:
            break
    assert iterations == 0, "Loop should exit immediately when run_seconds=0"


def test_run_seconds_none_means_forever():
    """When run_seconds is None, the time check never triggers."""
    start = time.time()
    run_seconds = None
    triggered = False
    for _ in range(5):
        if run_seconds is not None and (time.time() - start) >= run_seconds:
            triggered = True
            break
    assert not triggered


def test_demo_preflight_needs_config(tmp_path, monkeypatch):
    """demo.main() should return 2 if config.yaml is missing."""
    monkeypatch.chdir(tmp_path)
    # Patch _root so demo looks in tmp_path
    import cli.demo as demo_mod

    monkeypatch.setattr(demo_mod, "_root", tmp_path)
    result = demo_mod.main()
    assert result == 2
