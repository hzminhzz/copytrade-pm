"""Independent E4 integrity verification does not confer source qualification."""

from datetime import UTC, datetime
from hashlib import sha256
import json

from copytrade_pm.pm_e4_source_readiness import audit
from copytrade_pm.pm_e4_stream import PORTFOLIO_PODS


def test_portfolio_rosters_frozen():
    assert PORTFOLIO_PODS == {
        "A": ("W028", "W042", "W030"),
        "B": ("W044", "CA-005", "W031"),
        "C": ("CO-001", "W015", "VS066"),
    }


def test_empty_store_is_not_prospective_evidence(tmp_path):
    result = audit(tmp_path, "A")
    assert not result["all_generations_integrity_pass"]
    assert not result["trading_authorized"]
    assert not result["scientifically_qualified"]


def test_tampered_raw_receipt_fails_closed(tmp_path):
    generation = tmp_path / "gE420261101T100000000000Z-abcd1234"
    (generation / "frames").mkdir(parents=True)
    (generation / "metadata").mkdir()
    frame = b'{"channel":"userFills","data":{}}'
    (generation / "frames" / "00000000.json").write_bytes(frame)
    metadata = {
        "filename": "00000000.json",
        "source_raw_sha256": sha256(frame).hexdigest(),
        "channel": "userFills",
        "locally_received_at": "2026-11-01T10:00:00+00:00",
    }
    (generation / "metadata" / "00000000.json").write_text(json.dumps(metadata))
    started = datetime(2026, 11, 1, tzinfo=UTC).isoformat()
    report = {
        "frames_stored": 1,
        "errors": [],
        "disconnect_reason": "BOUNDED_SESSION_ROTATION",
        "snapshots": {},
        "subaccount_counts": {},
        "started_at": started,
        "finished_at": started,
    }
    (generation / "session-report.json").write_text(json.dumps(report))
    assert audit(tmp_path, "A")["prospective_generations"][0]["verified_frame_count"] == 1
    (generation / "frames" / "00000000.json").write_bytes(b"tampered")
    result = audit(tmp_path, "A")
    assert result["prospective_generations"][0]["status"] == "BLOCKED"
    assert result["prospective_generations"][0]["errors"]
    assert not result["all_generations_integrity_pass"]
