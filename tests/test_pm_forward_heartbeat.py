"""Observer-only worker heartbeat and independent PID/process-epoch verification."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from copytrade_pm.pm_forward_heartbeat import (
    _process_identity,
    inspect_observer_heartbeat,
    publish_observer_heartbeat,
)
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_status import paper_operator_status
from test_pm_forward_journal import manifest


def started(tmp_path: Path):
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("test_heartbeat", "acct_heartbeat"))
    root = tmp_path / "heartbeats"
    t = datetime.now(UTC)
    recorded = publish_observer_heartbeat(
        root,
        journal=journal,
        run_id="test_heartbeat",
        release_sha="c" * 64,
        transport_recv_at=t.isoformat(),
        source_book_at=t.isoformat(),
        market_quote_at=t.isoformat(),
        observed_at=t.isoformat(),
    )
    assert recorded["status"] == "OBSERVER_HEARTBEAT_RECORDED"
    return journal, root, t


def test_real_pid_start_epoch_verified_but_not_protected(tmp_path):
    journal, root, now = started(tmp_path)
    current = _process_identity(os.getpid())
    assert current["start_ticks"] > 0 and current["uid"] == os.geteuid()
    health = inspect_observer_heartbeat(
        root,
        journal=journal,
        run_id="test_heartbeat",
        as_of=(now + timedelta(seconds=5)).isoformat(),
    )
    assert health["observer_process_verified"]
    assert health["health"] == "DEGRADED"
    assert not health["protected_worker_attested"]
    assert "PROTECTED_OS_IDENTITY_NOT_VERIFIED" in health["reasons"]
    assert health["ages_seconds"]["transport_recv"] == 5
    assert health["order_route"] == "NONE"


def test_stale_feed_detected_despite_fresh_worker_pid(tmp_path):
    journal, root, now = started(tmp_path)
    report = inspect_observer_heartbeat(
        root,
        journal=journal,
        run_id="test_heartbeat",
        as_of=(now + timedelta(seconds=200)).isoformat(),
    )
    assert "TRANSPORT_RECV_STALE_OR_FUTURE" in report["reasons"]
    assert "SOURCE_BOOK_STALE_OR_FUTURE" in report["reasons"]
    assert "MARKET_QUOTE_STALE_OR_FUTURE" in report["reasons"]
    assert "HEARTBEAT_STALE_OR_FUTURE" in report["reasons"]


def test_status_consumes_independently_observed_heartbeat_without_claiming_running(tmp_path):
    journal, root, now = started(tmp_path)
    status = paper_operator_status(
        journal.path,
        run_id="test_heartbeat",
        as_of=(now + timedelta(seconds=3)).isoformat(),
        heartbeat_root=root,
    )
    assert status["health"] == "DEGRADED"
    assert status["real_worker_evidence"] is False
    independent = status["independent_observer_evidence"]
    assert independent["observer_process_verified"]
    assert independent["protected_worker_attested"] is False
    assert status["paper_admitted"] is False
    assert status["order_route"] == "NONE"


def test_forged_pid_start_ticks_and_tamper_fail_readonly(tmp_path):
    journal, root, now = started(tmp_path)
    path = root / "test_heartbeat.heartbeat.json"
    initial = json.loads(path.read_text())
    fake = deepcopy(initial)
    fake["process_identity"]["start_ticks"] += 1
    from copytrade_pm.pm03_account import digest

    fake["payload_sha"] = digest({k: v for k, v in fake.items() if k != "payload_sha"})
    path.write_text(json.dumps(fake))
    unknown = inspect_observer_heartbeat(
        root, journal=journal, run_id="test_heartbeat", as_of=now.isoformat()
    )
    assert unknown["health"] == "UNKNOWN"
    assert "HEARTBEAT_PROCESS_RESTART_OR_SPOOFED" in unknown["reasons"]
    path.write_text(json.dumps({**initial, "run_id": "forged"}))
    unknown = inspect_observer_heartbeat(
        root, journal=journal, run_id="test_heartbeat", as_of=now.isoformat()
    )
    assert "HEARTBEAT_TAMPERED" in unknown["reasons"]


def test_independent_inspector_detects_real_child_sigkill(tmp_path):
    journal = PaperJournal(tmp_path / "paper")
    journal.register(manifest("run_child", "acct_child"))
    heartbeats = tmp_path / "heartbeats"
    child_code = """
import time
from datetime import datetime, UTC
from pathlib import Path
from copytrade_pm.pm_forward_heartbeat import publish_observer_heartbeat
from copytrade_pm.pm_forward_journal import PaperJournal
root = Path(__import__("sys").argv[1])
journal = PaperJournal(root / "paper")
time_at = datetime.now(UTC).isoformat()
publish_observer_heartbeat(
    root / "heartbeats", journal=journal,
    run_id="run_child", release_sha="c"*64,
    transport_recv_at=time_at, source_book_at=None,
    market_quote_at=None, observed_at=time_at,
)
time.sleep(30)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        heartbeat_file = heartbeats / "run_child.heartbeat.json"
        for _ in range(100):
            if heartbeat_file.is_file() or child.poll() is not None:
                break
            time.sleep(0.02)
        assert heartbeat_file.is_file(), child.stderr.read().decode()
        checked = inspect_observer_heartbeat(
            heartbeats,
            journal=journal,
            run_id="run_child",
            as_of=datetime.now(UTC).isoformat(),
        )
        assert checked["observer_process_verified"]
        assert checked["health"] == "DEGRADED"
        child.kill()
        child.wait(timeout=5)
        post = inspect_observer_heartbeat(
            heartbeats,
            journal=journal,
            run_id="run_child",
            as_of=datetime.now(UTC).isoformat(),
        )
        assert post["health"] == "UNKNOWN"
        assert not post["protected_worker_attested"]
        assert journal.restore("run_child")["cursor"] == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_missing_or_inconsistent_financial_head_blocks(tmp_path):
    journal, root, now = started(tmp_path)
    journal.append("test_heartbeat", "halt", {"kind": "HALT", "event_at": now.isoformat()})
    blocked = inspect_observer_heartbeat(
        root, journal=journal, run_id="test_heartbeat", as_of=now.isoformat()
    )
    assert blocked["health"] == "UNKNOWN"
    assert "HEARTBEAT_FINANCIAL_HEAD_CHANGED" in blocked["reasons"]
