"""Read-only publisher bridge: no native registry/Guardian/trading authority."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os

import pytest

from copytrade_pm.dashboard.evidence_plane import EvidenceInvalid, publish_health_bridge
from copytrade_pm.wallet_health import assess
from copytrade_pm.wallet_health_projection import project, publish, read
from test_wallet_health import NOW, seeded


def test_bridge_copies_only_validated_redacted_snapshot(tmp_path):
    db = seeded(tmp_path)
    report = assess(db, as_of=NOW)
    source = tmp_path / "redacted"
    output = tmp_path / "evidence"
    raw = project(report, published_at=NOW)
    old_mask = os.umask(0o077)
    try:
        publish(source, raw)
    finally:
        os.umask(old_mask)
    assert (source / "wallet-health.json").stat().st_mode & 0o777 == 0o644
    assert publish_health_bridge(output, source, now=NOW)
    assert (output / "wallet-health.json").read_bytes() == raw
    data = read(output, now=NOW)
    assert data["wallet_count"] == 1
    assert data["trading_authorized"] is False
    assert data["monitoring"]["health_unknown_count"] == 1
    assert data["monitoring"]["health_evidence_fault"] == 1


def test_missing_stale_and_tampered_bridge_fail_closed(tmp_path):
    db = seeded(tmp_path)
    source = tmp_path / "redacted"
    output = tmp_path / "evidence"
    assert publish_health_bridge(output, source, now=NOW) is False
    assert not output.exists()
    raw = project(assess(db, as_of=NOW), published_at=NOW)
    publish(source, raw)
    assert publish_health_bridge(output, source, now=NOW + timedelta(days=3))
    assert read(output, now=NOW + timedelta(days=3))["stale"] is True
    payload = json.loads(raw)
    payload["wallet_count"] = 999
    (source / "wallet-health.json").write_text(json.dumps(payload))
    with pytest.raises((ValueError, EvidenceInvalid), match="HASH"):
        publish_health_bridge(output, source, now=NOW)
    (source / "wallet-health.json").write_text("[]")
    with pytest.raises(ValueError, match="TYPE"):
        publish_health_bridge(output, source, now=NOW)
    # Invalid private source cannot overwrite the last valid published generation.
    assert (output / "wallet-health.json").read_bytes() == raw


def test_bridge_rejects_symlinked_health_input(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "other.json"
    target.write_text("{}")
    (source / "wallet-health.json").symlink_to(target)
    with pytest.raises(OSError):
        publish_health_bridge(tmp_path / "out", source, now=datetime.now(UTC))
