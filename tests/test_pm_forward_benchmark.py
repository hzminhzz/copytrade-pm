"""Smoke-check temporary synthetic full PM03 event/account benchmark contract."""

import json
from pathlib import Path
import subprocess
import sys


def test_private_synthetic_ext4_benchmark_reports_truthful_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "bench_forward_paper.py"),
            "--accounts",
            "2",
            "--marks",
            "2",
            "--burst-multiplier",
            "2",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=25,
        check=True,
    )
    observed = json.loads(completed.stdout)
    assert observed["schema"] == "forward_paper_synthetic_benchmark_v1"
    assert observed["account_count"] == 2
    assert observed["event_count"] == observed["expected_event_count"] == 12
    assert observed["all_accounts_financially_reconciled"]
    assert observed["broker_order_route"] == "NONE"
    assert observed["source_cursors_atomic"]
    assert observed["synthetic_2x_sequential_burst"]
    assert observed["final_sqlite_disk_bytes"] > 0
    assert observed["event_processing_ms_p99"] > 0
    assert not observed["unattended_24h_soak_verified"]
    assert not observed["p99_eligible_due_lag_5s_slo_verified"]
    assert not observed["real_source_or_market_freshness_verified"]
    assert not observed["scientifically_qualified"]
