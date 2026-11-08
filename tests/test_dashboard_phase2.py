"""Phase 2 fixtures exercise evidence statuses, bounded read seams and zero mutations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache
from test_dashboard_adapter import T0, capture, fake_native


def owner(*, provider=None, native=None, root=None):
    return DashboardReader(
        clock=lambda: T0,
        cache=SmallTTLCache(),
        guardian_provider=provider or (lambda cmd: capture(cmd)),
        native_read=native or fake_native,
        research_root=root,
    )


def test_risk_finance_floor_zero_and_pod_budget_unknown():
    def source(command):
        if command == "risk":
            return capture(
                command,
                data={
                    "finance": {
                        "equity": "10000.00",
                        "daily_floor": "0",
                        "internal_floor": "9550.50",
                        "trailing_floor": "9000",
                        "risk_floor": "9550.50",
                        "headroom": "449.50",
                        "realized_made": "0",
                    },
                    "pod_loss_used": {"pod-1": "12.25", "pod-2": "0"},
                    "reservations": {},
                },
            )
        return capture(command)

    report = owner(provider=source).risk_status()
    assert report["metrics"]["daily_floor"]["value"] == "0"
    assert report["metrics"]["headroom"]["value"] == "449.50"
    assert report["metrics"]["daily_floor"]["status"] == "VERIFIED"
    assert report["pod_losses"][1]["loss_used"] == "0"
    assert report["pod_losses"][0]["loss_budget"] is None
    assert report["exposure"]["status"] == "UNKNOWN"
    assert report["reservation_count"] == 0
    assert report["trading_authorized"] is False


def test_risk_guardian_mismatch_suppresses_all_financial_values():
    report = owner(provider=lambda c: capture(c, sequence=2 if c == "broker" else 1)).risk_status()
    assert report["metrics"]["daily_floor"]["value"] is None
    assert report["metrics"]["equity"]["status"] == "BLOCKED"
    assert report["pod_losses"] == []


def test_execution_stable_ids_and_uncertain_outcomes():
    def source(command):
        if command == "portfolio":
            return capture(
                command,
                data={
                    "decisions": [
                        {
                            "decision_id": "D1",
                            "release_sha": "a" * 64,
                            "status": "ACCEPT",
                            "pods": [],
                        },
                        {
                            "decision_id": "D2",
                            "release_sha": "a" * 64,
                            "status": "REJECT",
                            "pods": [],
                        },
                    ]
                },
            )
        if command == "intent":
            return capture(
                command,
                data={
                    "intents": [
                        {
                            "intent_id": "I1",
                            "decision_id": "D1",
                            "release_sha": "a" * 64,
                            "market": "BTC",
                            "quantity": "1",
                            "filled": "0.2",
                            "status": "PARTIAL",
                            "created_at_ms": 5000,
                        },
                        {
                            "intent_id": "I2",
                            "decision_id": "D-UNKNOWN",
                            "release_sha": "a" * 64,
                            "market": "ETH",
                            "quantity": "0",
                            "filled": "0",
                            "status": "UNKNOWN",
                            "created_at_ms": 5100,
                        },
                    ]
                },
            )
        return capture(command)

    data = owner(provider=source).execution_monitor()
    assert data["intents"][0]["decision_link"] == "VERIFIED_ID_MATCH"
    assert data["intents"][0]["broker_fill_at"] is None
    assert data["intents"][1]["decision_link"] == "UNKNOWN"
    assert data["intents"][1]["filled"] == "0"
    assert data["source_events"] == []
    assert data["target_vs_actual"] is None


def test_duplicate_decision_or_release_mismatch_cannot_invent_link():
    def source(command):
        if command == "portfolio":
            return capture(
                command,
                data={
                    "decisions": [
                        {"decision_id": "D", "release_sha": "a" * 64, "status": "ACCEPT"},
                        {"decision_id": "D", "release_sha": "a" * 64, "status": "ACCEPT"},
                    ]
                },
            )
        if command == "intent":
            return capture(
                command,
                data={
                    "intents": [
                        {
                            "intent_id": "I",
                            "decision_id": "D",
                            "release_sha": "a" * 64,
                            "quantity": "1",
                            "filled": "0",
                            "status": "PENDING",
                        },
                    ]
                },
            )
        return capture(command)

    assert owner(provider=source).execution_monitor()["intents"][0]["decision_link"] == "UNKNOWN"
    assert (
        owner(
            provider=lambda c: capture(c, sequence=5 if c == "broker" else 12)
        ).execution_monitor()["link_status"]
        == "UNKNOWN"
    )


def test_portfolio_requires_signature_checked_selection_and_distinguishes_states():
    record = {
        "portfolio_id": "q3/B",
        "version": 2,
        "definition_sha256": "f" * 64,
        "members": ["W031", "W044"],
        "state": "RESEARCH",
        "source_sealed": True,
    }

    def native(command):
        result = dict(fake_native(["portfolios", "current"]))
        result.update(
            status="VERIFIED",
            data={
                "q3/B": record,
            }
            if command[:2] == ["portfolios", "list"]
            else {
                "selection_state": "SIGNATURE_CHECKED_RESEARCH_ONLY",
                "portfolios": [record],
            },
        )
        return result

    data = owner(native=native).portfolio_explorer()
    assert data["records"][0]["portfolio_id"] == "q3/B"
    assert data["records"][0]["research_state"] == "RESEARCH_SELECTED"
    assert data["records"][0]["deployment_state"] == "UNKNOWN"
    assert data["records"][0]["runtime_state"] == "UNKNOWN"
    assert owner(native=native).portfolio_explorer(asof="not utc")["status"] == "BLOCKED"

    def untrusted(command):
        result = native(command)
        if command[:2] == ["portfolios", "current"]:
            result["data"] = {"selection_state": "UNSIGNED", "portfolios": [record]}
        return result

    assert owner(native=untrusted).portfolio_explorer()["records"][0]["research_state"] == "SAVED"


def test_research_missing_cache_and_bounded_filters():
    calls = []

    def native(command):
        calls.append(command)
        result = dict(fake_native(["portfolios", "current"]))
        result.update(
            status="VERIFIED",
            data={
                "schema": "pm_offline_verified_job_catalog_v1",
                "reports": [
                    {"job_id": "case1", "cache_key": "b" * 64, "scientifically_qualified": False}
                ],
                "total": 1,
            },
        )
        return result

    assert owner(native=native).research_reports()["status"] == "UNAVAILABLE"
    assert not calls
    app = owner(native=native, root="/owner-controlled/cache")
    assert app.research_reports(run_id="../secret")["status"] == "BLOCKED"
    assert app.research_reports(limit=1000)["status"] == "BLOCKED"
    assert not calls
    record = app.research_reports(run_id="case1", limit=10, offset=3)
    assert record["status"] == "VERIFIED"
    assert calls[0] == [
        "research",
        "show",
        "case1",
        "--cache-root",
        "/owner-controlled/cache",
        "--limit",
        "10",
        "--offset",
        "3",
    ]


def test_chart_preserves_gaps_utc_reset_and_actual_extrema():
    from copytrade_pm.dashboard.chart_data import prepare_series

    base = datetime(2026, 11, 1, tzinfo=UTC)
    points = []
    for i in range(360):
        stamp = base + timedelta(minutes=i if i < 181 else i + 30)
        points.append(
            {
                "timestamp": stamp.isoformat(),
                "value": "150" if i == 37 else "-80" if i == 284 else str(i % 20),
                "series": "equity",
                "metric": "equity",
                "source_id": "guardian-ledger-sealed",
                "evidence_class": "BROKER_EXECUTED",
                "reset_boundary": i == 144,
            }
        )
    data = prepare_series(points, max_points=96, expected_interval_ms=60_000)
    assert len(data) <= 96
    assert {"150", "-80"}.issubset({p["value_exact"] for p in data})
    assert any(p["gap_before"] for p in data)
    assert any(p["reset_boundary"] for p in data)
    assert len({p["segment"] for p in data}) == 2


def test_chart_rejects_contradictory_evidence_and_unbounded_data():
    from copytrade_pm.dashboard.chart_data import prepare_series

    base = dict(
        timestamp=T0.isoformat(),
        value="0",
        series="equity",
        source_id="S1",
        metric="equity",
        evidence_class="PAPER_SHADOW",
    )
    with pytest.raises(ValueError, match="CONTRADICTORY"):
        prepare_series([base, {**base, "source_id": "S2"}])
    with pytest.raises(ValueError, match="INVALID_OR_UNGRADED"):
        prepare_series([{**base, "evidence_class": "VERIFIED"}])
    with pytest.raises(ValueError, match="UNBOUNDED"):
        prepare_series([base] * 120001)


def test_no_read_path_can_dispatch_financial_mutation(monkeypatch):
    from copytrade_pm.dashboard import adapter

    def prohibited(*args, **kwargs):
        raise AssertionError("DASHBOARD_FINANCIAL_MUTATION")

    monkeypatch.setattr(adapter.subprocess, "run", prohibited)
    monkeypatch.setattr(adapter.registry, "connect", prohibited)
    app = owner()
    assert app.risk_status()["trading_authorized"] is False
    assert app.execution_monitor()["trading_authorized"] is False
