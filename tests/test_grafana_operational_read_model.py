"""Adversarial contract tests for the single operational read-model interface.

These exercise publisher -> immutable generation -> gateway, not private helpers.
"""

from __future__ import annotations

# Optional-dependency guards must precede imports of the HTTP gateway.
# ruff: noqa: E402

import asyncio
from datetime import timedelta

import pytest

httpx = pytest.importorskip("httpx", reason="dashboard optional extra")
pytest.importorskip("starlette", reason="dashboard optional extra")

from copytrade_pm.dashboard import evidence_plane as ep
from copytrade_pm.dashboard.grafana_capabilities import build_capabilities, validate_capabilities
from copytrade_pm.dashboard.grafana_projection import build_projection, create_app
from test_grafana_phase2 import NativeReader, T0, TOKEN


def publish(reader, tmp_path, *, now=T0):
    data = build_projection(reader)
    ep.publish_atomic(tmp_path, ep.encode_generation(data, now=now))
    return ep.read_generation(tmp_path, now=now)


def alert_flags(tmp_path, monkeypatch, *, now=T0):
    monkeypatch.setattr(ep, "_utc_now", lambda: now)

    async def get():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="localhost")
            ),
            base_url="http://localhost",
        ) as client:
            response = await client.get(
                "/v1/account-risk", headers={"Authorization": f"Bearer {TOKEN}"}
            )
            assert response.status_code == 200
            return response.json()["monitoring"]

    return asyncio.run(get())


def test_health_row_expires_even_when_parent_was_not_verified(tmp_path):
    reader = NativeReader()
    reader.health = lambda: {
        "retrieved_at": T0.isoformat(),
        "guardian": {
            "status": "VERIFIED",
            "state": "RUNNING",
            "authority": "guardian.owner",
            "source_observed_at": T0.isoformat(),
        },
        "broker": {"status": "UNKNOWN", "state": "UNKNOWN", "authority": "guardian.owner"},
        "services": {},
    }
    data = build_projection(reader)
    ep.publish_atomic(tmp_path, ep.encode_generation(data, now=T0))
    expired = ep.read_generation(tmp_path, now=T0 + timedelta(seconds=50))
    rows = expired["capabilities"]["health"]["rows"]
    assert all(row["source_grade"] != "VERIFIED" for row in rows)
    assert expired["capabilities"]["health"]["status"] != "VERIFIED"


def test_publisher_end_clock_accepts_sequential_owner_reads(tmp_path):
    reader = NativeReader()
    reader.wallets = lambda *, limit: {
        "status": "VERIFIED",
        "data": {"wallets": [{"alias": "W1", "cohort": "research"}]},
        "inventory_sha256": "a" * 64,
        "source_observed_at": (T0 + timedelta(seconds=1)).isoformat(),
    }
    # The overview was observed at T0, but subsequent native readers run later.
    # Valid clocks must be compared to completion of the publisher's read cycle.
    end = T0 + timedelta(seconds=2)
    projection = build_projection(reader, clock=lambda: end)
    ep.publish_atomic(tmp_path, ep.encode_generation(projection, now=end))
    result = ep.read_generation(tmp_path, now=end)
    assert result["capabilities"]["wallets"]["status"] == "VERIFIED"
    assert result["capabilities"]["wallets"]["rows"][0]["alias"] == "W1"


def test_future_capability_source_is_rejected_at_publication():
    data = build_projection(NativeReader())
    data["capabilities"]["wallets"]["source_observed_at"] = (T0 + timedelta(days=90)).isoformat()
    with pytest.raises(ep.EvidenceInvalid, match="FUTURE"):
        ep.encode_generation(data, now=T0)


def test_no_verified_section_with_unavailable_placeholder():
    reader = NativeReader()
    reader.portfolio_explorer = lambda *, limit: {
        "status": "VERIFIED",
        "records": [],
        "catalog": {"source_observed_at": T0.isoformat()},
    }
    owner = {
        "status": "VERIFIED",
        "source_observed_at": T0.isoformat(),
        "captured_at": T0.isoformat(),
        "account_binding_sha": "d" * 64,
        "revision": "a" * 64,
        "journal_sequence": 3,
    }
    reader.execution_monitor = lambda: {
        "coherent_capture": True,
        "intents": [],
        "sources": {key: dict(owner) for key in ("status", "portfolio", "intent", "broker")},
    }
    reader.wallets = lambda *, limit: {
        "status": "VERIFIED",
        "data": {"wallets": []},
        "inventory_sha256": "f" * 64,
        "source_observed_at": T0.isoformat(),
    }
    capabilities = build_capabilities(reader)
    for key in ("portfolios", "execution", "wallets"):
        item = capabilities[key]
        assert item["rows"] == []
        assert item["completeness"] == "EMPTY"
        assert item["status"] == "VERIFIED"


def test_reject_unknown_parent_claiming_verified_child():
    data = build_capabilities(NativeReader())
    data["health"]["status"] = "UNKNOWN"
    row = data["health"]["rows"][0]
    row["source_grade"] = "VERIFIED"
    row["source_time"] = T0.isoformat()
    with pytest.raises(ep.EvidenceInvalid, match="CONTRADICT"):
        validate_capabilities(data)


def test_single_intent_six_late_fills_is_not_verified():
    reader = NativeReader()
    reader.execution_monitor = lambda: {
        "coherent_capture": True,
        "retrieved_at": T0.isoformat(),
        "truncated": False,
        "reconciliation": "RECONCILED",
        "intents": [
            {
                "intent_id": "one",
                "decision_id": "one-decision",
                "market": "BTC",
                "first_known_at": 1_000_000,
                "batch_due_ms": 1_300_000,
                "batch_decision_at": 1_300_000,
                "guardian_intent_at_ms": 1_300_001,
                "broker_acceptance_at": None,
                "broker_fill_at": 1_300_000 + 24 * 60_000,
                "confirmed_fills": 6,
                "fill_trace_status": "VERIFIED_OWNER_FILL_ID",
            }
        ],
    }
    item = build_capabilities(reader)["execution"]["rows"][0]
    assert item["grade"] == "DEGRADED"
    assert "FILL_LATE" in item["reason"]
    assert item["fills"] == 6
    assert item["reason"] != "MULTIPLE_ORDER_INTENTS"


def test_missing_broker_acceptance_cannot_be_claimed_verified():
    reader = NativeReader()
    row = build_capabilities(reader)["execution"]["rows"][0]
    assert row["grade"] != "VERIFIED"
    assert "ACCEPTANCE" in row["reason"] or "UNCONFIRMED" in row["reason"]


def test_truncated_receipts_are_explicitly_unqualified():
    reader = NativeReader()
    original = reader.execution_monitor
    reader.execution_monitor = lambda: {**original(), "truncated": True}
    section = build_capabilities(reader)["execution"]
    assert section["status"] != "VERIFIED"
    assert section["error_code"] == "TRUNCATED_NATIVE_RECEIPTS"
    assert all(row["grade"] != "VERIFIED" for row in section["rows"])


def test_optional_portfolio_membership_does_not_break_verified_finance(tmp_path, monkeypatch):
    reader = NativeReader()
    before = reader.overview

    def full_overview():
        snapshot = before()
        for key, value in (
            ("equity", "0"),
            ("headroom", "250"),
            ("daily_headroom", "100"),
            ("trailing_headroom", "175"),
        ):
            snapshot["metrics"][key] = {"value": value, "status": "VERIFIED"}
        return snapshot

    reader.overview = full_overview
    projection = publish(reader, tmp_path)
    assert projection["coverage"] == "INCOMPLETE"  # Optional membership still unknown.
    assert alert_flags(tmp_path, monkeypatch)["account_evidence_fault"] == 0


def test_unknown_optional_health_does_not_permanently_fire_operational_alert(tmp_path, monkeypatch):
    reader = NativeReader()
    publish(reader, tmp_path)
    flags = alert_flags(tmp_path, monkeypatch)
    assert flags["generation_fault"] == 0
    assert flags["operational_evidence_fault"] == 0


def test_genuine_verified_incident_fires_then_recovers(tmp_path, monkeypatch):
    reader = NativeReader()
    reader.health = lambda: {
        "retrieved_at": T0.isoformat(),
        "guardian": {
            "status": "VERIFIED",
            "state": "HALTED",
            "authority": "guardian.owner",
            "source_observed_at": T0.isoformat(),
        },
        "services": {},
    }
    publish(reader, tmp_path)
    assert alert_flags(tmp_path, monkeypatch)["operational_evidence_fault"] == 1

    reader.health = lambda: {
        "retrieved_at": T0.isoformat(),
        "guardian": {
            "status": "VERIFIED",
            "state": "RUNNING",
            "authority": "guardian.owner",
            "source_observed_at": T0.isoformat(),
        },
        "services": {},
    }
    publish(reader, tmp_path)
    assert alert_flags(tmp_path, monkeypatch)["operational_evidence_fault"] == 0


def test_one_capability_failure_does_not_poison_unrelated_evidence(tmp_path):
    reader = NativeReader()

    def unavailable_portfolios(*, limit):
        raise RuntimeError("PRIVATE_SOURCE_UNAVAILABLE")

    reader.portfolio_explorer = unavailable_portfolios
    outcome = publish(reader, tmp_path)
    assert outcome["capabilities"]["portfolios"]["status"] == "UNAVAILABLE"
    assert outcome["capabilities"]["wallets"]["rows"][0]["alias"] == "W1"


def test_future_source_clock_on_row_is_not_sanitized_into_current(tmp_path):
    reader = NativeReader()
    reader.health = lambda: {
        "retrieved_at": T0.isoformat(),
        "guardian": {
            "status": "VERIFIED",
            "state": "RUNNING",
            "authority": "guardian.owner",
            "source_observed_at": (T0 + timedelta(days=90)).isoformat(),
        },
    }
    # The publisher quarantines this one invalid source and preserves others.
    result = publish(reader, tmp_path)
    assert result["capabilities"]["health"]["status"] == "UNAVAILABLE"
    assert result["capabilities"]["health"]["error_code"] == "CAUSALLY_INVALID_SOURCE_CLOCK"
    assert result["capabilities"]["wallets"]["status"] == "VERIFIED"
