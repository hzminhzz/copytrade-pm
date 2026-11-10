"""Strategy-health bridge is redacted, immutable and strictly fail-closed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest

from copytrade_pm.dashboard.evidence_plane import (
    EvidenceInvalid,
    publish_strategy_health_bridge,
)
from copytrade_pm.strategy_health import seal
from copytrade_pm.strategy_health_projection import project, publish, read
from test_strategy_health_v2 import assessment


def test_strategy_bridge_copies_only_valid_redacted_report(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    now = datetime.now(UTC)
    report = seal(assessment().model_copy(update={"as_of": now, "created_at": now}))
    payload = project(report, published_at=now)
    publish(source, payload)

    assert publish_strategy_health_bridge(target, source, now=now)
    assert (target / "strategy-health.json").read_bytes() == payload
    assert read(target, now=now)["trading_authorized"] is False
    assert b"source_alias" not in payload


def test_strategy_bridge_refuses_missing_stale_corrupt_and_symlink(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    now = datetime.now(UTC)
    assert not publish_strategy_health_bridge(target, source, now=now)
    report = seal(assessment().model_copy(update={"as_of": now, "created_at": now}))
    payload = project(report, published_at=now)
    publish(source, payload)

    with pytest.raises(ValueError, match="STALE"):
        publish_strategy_health_bridge(target, source, now=now + timedelta(hours=1))
    assert not target.exists()
    assert publish_strategy_health_bridge(target, source, now=now)
    raw = json.loads(payload)
    raw["opportunity_count"] = 999
    (source / "strategy-health.json").write_text(json.dumps(raw))
    with pytest.raises((ValueError, EvidenceInvalid), match="HASH"):
        publish_strategy_health_bridge(target, source, now=now)
    assert (target / "strategy-health.json").read_bytes() == payload

    (source / "strategy-health.json").unlink()
    (source / "strategy-health.json").symlink_to(target / "strategy-health.json")
    with pytest.raises(OSError):
        publish_strategy_health_bridge(target, source, now=now)
    assert (target / "strategy-health.json").read_bytes() == payload
