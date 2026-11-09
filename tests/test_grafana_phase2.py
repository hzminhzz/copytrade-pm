"""Phase 2 Grafana operational capability: isolation and negative evidence."""

from __future__ import annotations

# Optional-dependency guards must precede imports of the HTTP gateway.
# ruff: noqa: E402

import asyncio
from datetime import UTC, datetime, timedelta
import json

import pytest

httpx = pytest.importorskip("httpx", reason="dashboard optional extra")
pytest.importorskip("starlette", reason="dashboard optional extra")

from copytrade_pm.dashboard import evidence_plane as ep
from copytrade_pm.dashboard.grafana_capabilities import build_capabilities, validate_capabilities
from copytrade_pm.dashboard.grafana_projection import build_projection, create_app

T0 = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)
TOKEN = "s" * 48


class NativeReader:
    def __init__(self):
        self.calls = []

    def overview(self):
        from test_grafana_projection import snapshot

        snapshot_data = snapshot()
        snapshot_data["retrieved_at"] = T0.isoformat()
        for source in snapshot_data["sources"].values():
            source["retrieved_at"] = T0.isoformat()
            source["captured_at"] = T0.isoformat()
            source["source_observed_at"] = T0.isoformat()
        self.calls.append("overview")
        return snapshot_data

    def portfolio_explorer(self, *, limit):
        self.calls.append("portfolios")
        return {
            "status": "VERIFIED",
            "records": [
                {
                    "portfolio_id": "gemini.phase4/E6",
                    "research_state": "RESEARCH_SELECTED",
                    "members": ["W1", "W2"],
                    "deployment_state": "UNKNOWN",
                    "signed_fixed_k": None,
                }
            ],
            "catalog": {"source_observed_at": T0.isoformat()},
        }

    def execution_monitor(self):
        self.calls.append("execution")
        return {
            "coherent_capture": True,
            "intents": [
                {
                    "intent_id": "intent-1",
                    "decision_id": "decision-1",
                    "market": "BTC",
                    "first_known_at": 1000000,
                    "batch_due_ms": 1300000,
                    "batch_decision_at": 1300000,
                    "guardian_intent_at_ms": 1300001,
                    "broker_acceptance_at": None,
                    "broker_fill_at": None,
                    "confirmed_fills": 0,
                }
            ],
        }

    def health(self):
        self.calls.append("health")
        return {
            "retrieved_at": T0.isoformat(),
            "guardian": {"status": "UNKNOWN", "authority": "owner", "state": "UNKNOWN"},
            "services": {
                "prop-production-guardian.service": {
                    "os_active_state": "active",
                    "state": "UNKNOWN",
                }
            },
        }

    def wallets(self, *, limit):
        self.calls.append("wallets")
        return {
            "status": "VERIFIED",
            "data": {"wallets": [{"alias": "W1", "cohort": "research", "excluded": False}]},
            "inventory_sha256": "a" * 64,
            "source_observed_at": T0.isoformat(),
        }


def test_native_publisher_invokes_each_capability_once(tmp_path, monkeypatch):
    reader = NativeReader()
    data = build_projection(reader)
    assert reader.calls == ["overview", "portfolios", "execution", "health", "wallets"]
    ep.publish_atomic(tmp_path, ep.encode_generation(data, now=T0))
    result = ep.read_generation(tmp_path, now=T0)
    assert result["capabilities"]["portfolios"]["rows"][0]["deployment_state"] == "UNKNOWN"
    assert result["capabilities"]["portfolios"]["rows"][0]["exposure"] is None
    assert result["capabilities"]["portfolios"]["rows"][0]["budget"] is None
    assert result["capabilities"]["execution"]["rows"][0]["due_ms"] == 1300000
    assert result["capabilities"]["execution"]["rows"][0]["reason"] == "SINGLE_INTENT_UNCONFIRMED"
    assert result["capabilities"]["health"]["rows"][-1]["source_grade"] == "UNKNOWN"
    assert result["capabilities"]["wallets"]["rows"][0]["inventory"] == "a" * 64

    def forbidden(*_args, **_kwargs):
        raise AssertionError("GATEWAY_RAN_NATIVE_READER")

    monkeypatch.setattr(reader, "overview", forbidden)
    monkeypatch.setattr(ep, "_utc_now", lambda: T0)

    async def get():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(token=TOKEN, snapshot_dir=tmp_path, allowed_host="localhost")
            ),
            base_url="http://localhost",
        ) as client:
            for _ in range(5):
                answer = await client.get(
                    "/v1/account-risk", headers={"Authorization": f"Bearer {TOKEN}"}
                )
                assert answer.status_code == 200
                assert answer.json()["capabilities"]["wallets"]["rows"][0]["alias"] == "W1"
            for bad in ("/v1/operations", "/v1/wallets", "/v1/guardian/execute"):
                assert (
                    await client.get(bad, headers={"Authorization": f"Bearer {TOKEN}"})
                ).status_code == 404
            assert (
                await client.get(
                    "/v1/account-risk?limit=999999", headers={"Authorization": f"Bearer {TOKEN}"}
                )
            ).status_code == 400

    asyncio.run(get())
    assert len(reader.calls) == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("alias", "0x" + "a" * 40),
        ("alias", "bad\nnew line"),
        ("cohort", "c" * 120),
    ],
)
def test_wallets_reject_private_data(field, value):
    reader = NativeReader()
    cap = build_capabilities(reader)
    cap["wallets"]["rows"][0][field] = value
    with pytest.raises(ep.EvidenceInvalid):
        validate_capabilities(cap)


def test_bad_native_wallet_data_does_not_expose_private_addresses():
    class Bad(NativeReader):
        def wallets(self, *, limit):
            return {
                "status": "VERIFIED",
                "data": {"wallets": [{"alias": "0x" + "a" * 40, "cohort": "private"}]},
            }

    # A compromised native value blocks only this section, never leaks addresses.
    result = build_capabilities(Bad())
    assert result["wallets"]["status"] == "UNAVAILABLE"
    assert "0x" not in json.dumps(result)


def test_stale_capability_cannot_remain_verified(tmp_path):
    data = build_projection(NativeReader())
    ep.publish_atomic(tmp_path, ep.encode_generation(data, now=T0))
    result = ep.read_generation(tmp_path, now=T0 + timedelta(seconds=50))
    assert result["capabilities"]["portfolios"]["status"] == "STALE"
    assert result["capabilities"]["portfolios"]["rows"][0]["grade"] == "STALE"
    assert result["capabilities"]["wallets"]["rows"][0]["grade"] == "STALE"


def test_absent_reader_methods_fail_closed_and_keep_legacy_metrics():
    class OnlyOverview:
        def overview(self):
            return NativeReader().overview()

    result = build_projection(OnlyOverview())
    assert result["capabilities"]["wallets"]["status"] == "UNAVAILABLE"
    assert result["capabilities"]["execution"]["rows"][0]["intent"] == "NO_VERIFIED_RECEIPTS"
    assert result["metrics"][2]["value"] == "0"


def test_one_order_multiple_fills_not_reconstructed():
    reader = NativeReader()
    reader.execution_monitor = lambda: {
        "coherent_capture": True,
        "intents": [
            {
                "intent_id": "i1",
                "decision_id": "d1",
                "market": "ETH",
                "first_known_at": 1000,
                "batch_due_ms": 301000,
                "batch_decision_at": 301000,
                "confirmed_fills": 6,
            },
            {
                "intent_id": "i2",
                "decision_id": "d1",
                "market": "ETH",
                "first_known_at": 1000,
                "batch_due_ms": 301000,
                "batch_decision_at": 1700000,
                "confirmed_fills": 1,
            },
        ],
    }
    rows = build_capabilities(reader)["execution"]["rows"]
    assert len(rows) == 2
    assert rows[0]["fills"] == 6
    assert rows[0]["reason"] == "MULTIPLE_ORDER_INTENTS"
    assert rows[1]["reason"] == "MULTIPLE_ORDER_INTENTS"
    assert all(row["grade"] == "DEGRADED" for row in rows)


def test_published_snapshot_rejects_tampered_capability(tmp_path):
    ep.publish_atomic(tmp_path, ep.encode_generation(build_projection(NativeReader()), now=T0))
    path = tmp_path / "account-risk.json"
    data = json.loads(path.read_bytes())
    data["projection"]["capabilities"]["wallets"]["rows"][0]["alias"] = "0x" + "a" * 40
    path.write_text(json.dumps(data))
    with pytest.raises(ep.EvidenceInvalid, match="EVIDENCE_CORRUPT"):
        ep.read_generation(tmp_path, now=T0)
