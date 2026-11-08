"""Cross-repo operator capture consumer fixtures (source-only, no protected IO)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from copytrade_pm.dashboard.adapter import DashboardReader, SmallTTLCache
from test_dashboard_adapter import T0, capture, fake_native

SHA = "a" * 64


def reader(producer, *, native=None):
    return DashboardReader(
        clock=lambda: T0,
        guardian_provider=producer,
        native_read=native or fake_native,
        cache=SmallTTLCache(),
    )


def capture_with_history(command):
    if command != "history":
        return capture(command)
    prior = int((T0 - timedelta(minutes=2)).timestamp() * 1000)
    current = int((T0 - timedelta(seconds=1)).timestamp() * 1000)
    return capture(
        command,
        data={
            "evidence_class": "PAPER_SHADOW",
            "source_coverage": "RECENT_BOUNDED_TAIL_NOT_COMPLETE_HISTORY",
            "scientifically_qualified": False,
            "rows": [
                {
                    "observed_at_ms": prior,
                    "journal_sequence": 9,
                    "release_sha": SHA,
                    "equity": "9990.00",
                    "risk_floor": "9600",
                    "headroom": "390.00",
                    "day": 20300,
                },
                {
                    "observed_at_ms": current,
                    "journal_sequence": 12,
                    "release_sha": SHA,
                    "equity": "10000.00",
                    "risk_floor": "9600",
                    "headroom": "400.00",
                    "day": 20301,
                },
            ],
            "rows_truncated_to": 256,
        },
    )


def test_verified_owner_shadow_finance_chart_keeps_account_release_and_reset():
    subject = reader(capture_with_history)
    history = subject.performance_history()
    assert history["status"] == "VERIFIED_OWNER_SHADOW_TAIL"
    assert any(p["value_exact"] == "9990.00" for p in history["points"])
    assert all(p["evidence_class"] == "PAPER_SHADOW" for p in history["points"])
    assert all(p["source_id"] == SHA for p in history["points"])
    assert any(p["reset_boundary"] for p in history["points"])
    assert history["trading_authorized"] is False


@pytest.mark.parametrize(
    "failure",
    [
        "mismatched_account",
        "mismatched_sequence",
        "missing_history",
        "tampered_science",
        "conflicting_finance",
    ],
)
def test_finance_history_is_not_promoted_when_boundaries_fail(failure):
    def provider(command):
        if command == "history" and failure == "missing_history":
            raise FileNotFoundError()
        rec = capture_with_history(command)
        if command == "history" and failure == "mismatched_account":
            rec["native"]["account_binding_sha"] = "b" * 64
        if command == "history" and failure == "mismatched_sequence":
            rec["native"]["journal_sequence"] = 99
        if command == "history" and failure == "tampered_science":
            rec["native"]["scientifically_qualified"] = True
        if command == "history" and failure == "conflicting_finance":
            point = rec["native"]["rows"][0]
            rec["native"]["rows"].insert(1, {**point, "equity": "9991.00"})
        return rec

    history = reader(provider).performance_history()
    assert not history["points"]
    assert history["status"] in {"BLOCKED", "UNAVAILABLE"}


def test_mixed_publication_epoch_is_never_promoted_as_one_capture():
    def provider(command):
        result = capture_with_history(command)
        if command == "broker":
            result["captured_at"] = (T0 - timedelta(seconds=1)).isoformat()
            result["source_observed_at"] = (T0 - timedelta(seconds=1)).isoformat()
        return result

    subject = reader(provider)
    overview = subject.overview()
    assert overview["metrics"]["equity"]["value"] is None
    assert overview["sources"]["risk"]["status"] == "BLOCKED"
    assert subject.execution_monitor()["link_status"] == "UNKNOWN"
    assert subject.performance_history()["status"] == "BLOCKED"


def test_owner_confirmed_decision_receipts_and_broker_fills_link_by_id_only():
    def provider(command):
        if command == "portfolio":
            return capture(
                command,
                data={
                    "decisions": [
                        {
                            "decision_id": "D1",
                            "release_sha": SHA,
                            "status": "PREVIEW",
                            "first_known_ms": 1000,
                            "due_ms": 301000,
                            "batch_decision_ms": 301000,
                            "guardian_decision_at_ms": 301000,
                            "source_receipts": [
                                {
                                    "receipt_sha": "a" * 64,
                                    "source_event_ms": 999,
                                    "source_known_ms": 1000,
                                    "local_known_ms": 1000,
                                    "source_sequence": 1,
                                }
                            ],
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
                            "release_sha": SHA,
                            "status": "PARTIAL",
                            "market": "BTC",
                            "quantity": "2",
                            "filled": "1",
                            "created_at_ms": 301000,
                            "sent_at_ms": 301000,
                        },
                        {
                            "intent_id": "I2",
                            "decision_id": "UNKNOWN",
                            "release_sha": SHA,
                            "status": "UNKNOWN",
                            "market": "ETH",
                            "quantity": "1",
                            "filled": "0",
                            "created_at_ms": 301000,
                        },
                    ]
                },
            )
        if command == "broker":
            return capture(
                command,
                data={
                    "certainty": "COHERENT",
                    "broker_epoch": 3,
                    "last_snapshot_ms": 301002,
                    "fills": [
                        {
                            "execution_id_sha": "f" * 64,
                            "intent_id": "I1",
                            "market": "BTC",
                            "quantity": "1",
                            "price": "100",
                            "fee": "0.1",
                            "known_at_ms": 301001,
                        }
                    ],
                },
            )
        return capture(command)

    data = reader(provider).execution_monitor()
    assert data["link_status"] == "VERIFIED_CAPTURE_BINDING"
    assert data["source_events"][0]["source_event_ms"] == 999
    assert data["source_events"][0]["first_known_ms"] == 1000
    assert data["batch_decisions"][0]["batch_due_ms"] == 301000
    assert data["intents"][0]["decision_link"] == "VERIFIED_ID_MATCH"
    assert data["intents"][0]["broker_fill_at"] == 301001
    assert data["intents"][0]["confirmed_fills"] == 1
    assert data["intents"][0]["broker_acceptance_at"] is None
    assert data["intents"][1]["decision_link"] == "UNKNOWN"
    assert data["intents"][1]["broker_fill_at"] is None


def test_bad_source_clock_and_duplicate_fill_cannot_be_joined():
    def provider(command):
        if command == "portfolio":
            return capture(
                command,
                data={
                    "decisions": [
                        {
                            "decision_id": "D1",
                            "release_sha": SHA,
                            "status": "PREVIEW",
                            "first_known_ms": 1000,
                            "due_ms": 301000,
                            "batch_decision_ms": 301000,
                            "source_receipts": [
                                {
                                    "receipt_sha": SHA,
                                    "source_event_ms": 3000,
                                    "source_known_ms": 1000,
                                    "local_known_ms": 1000,
                                }
                            ],
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
                            "release_sha": SHA,
                            "status": "UNKNOWN",
                            "market": "BTC",
                            "quantity": "1",
                            "filled": "0",
                            "created_at_ms": 301000,
                        }
                    ]
                },
            )
        if command == "broker":
            return capture(
                command,
                data={
                    "certainty": "UNKNOWN",
                    "fills": [
                        {
                            "execution_id_sha": SHA,
                            "intent_id": "I1",
                            "market": "BTC",
                            "quantity": "1",
                            "price": "1",
                            "fee": "0",
                            "known_at_ms": 301001,
                        },
                        {
                            "execution_id_sha": SHA,
                            "intent_id": "I1",
                            "market": "BTC",
                            "quantity": "1",
                            "price": "1",
                            "fee": "0",
                            "known_at_ms": 301002,
                        },
                    ],
                },
            )
        return capture(command)

    data = reader(provider).execution_monitor()
    assert data["source_events"] == []
    assert data["duplicate_fill_identity"] is True
    assert data["intents"][0]["broker_fill_at"] is None


def test_owner_exposure_requires_verified_source_and_integrity():
    def provider(command):
        if command == "risk":
            return capture(
                command,
                data={
                    "finance": {"equity": "0", "headroom": "0"},
                    "exposure": {
                        "status": "VERIFIED_OWNER_MARK_SNAPSHOT",
                        "gross": "12.50",
                        "net": "-1.25",
                        "observed_at_ms": 123,
                    },
                },
            )
        return capture(command)

    report = reader(provider).risk_status()
    assert report["exposure"]["gross"] == "12.50"
    assert report["exposure"]["net"] == "-1.25"
    assert report["exposure"]["status"] == "VERIFIED_OWNER_MARK_SNAPSHOT"


def test_scenario_rules_are_native_read_only_and_never_a_simulation():
    calls = []

    def native(args):
        calls.append(args)
        assert args == ["contracts", "rules"]
        return {
            "schema": "copytrade_contract_rule_catalog_v1",
            "trading_authorized": False,
            "scientifically_qualified": False,
            "rule_set_version": "unverified",
            "rules_sha256": SHA,
            "contracts": [
                {
                    "id": "A Flex",
                    "rule_sha256": SHA,
                    "rule_authority": "USER_SUPPLIED_UNVERIFIED_ARCHETYPE",
                    "missing_terms": ["Account-specific conditions"],
                    "configuration": {"target": 1000},
                }
            ],
        }

    result = reader(capture_with_history, native=native).contract_rules()
    assert result["status"] == "VERIFIED"
    assert result["data"]["status"] == "SCENARIO_ONLY"
    assert len(result["data"]["contracts"]) == 1
    assert calls == [["contracts", "rules"]]
    assert result["trading_authorized"] is False


def test_chart_rejects_unrepresentable_decimal_without_truncating_owner_finance():
    from copytrade_pm.dashboard.chart_data import prepare_series

    with pytest.raises(ValueError, match="CHART_DECIMAL_PRECISION"):
        prepare_series(
            [
                {
                    "timestamp": T0.isoformat(),
                    "value": "100000000000000000000",
                    "series": "owner-shadow-equity",
                    "metric": "equity",
                    "source_id": SHA,
                    "evidence_class": "PAPER_SHADOW",
                }
            ]
        )


def test_portfolio_filter_and_pagination_remain_bounded_and_read_only():
    names = ["q3/A", "q3/B", "gemini.phase5/B"]

    def native(args):
        result = dict(fake_native(["portfolios", "current"]))
        if args[:2] == ["portfolios", "list"]:
            result.update(
                status="VERIFIED",
                data={
                    name: {
                        "portfolio_id": name,
                        "version": 2,
                        "definition_sha256": SHA,
                        "members": ["W031"],
                        "source_sealed": True,
                    }
                    for name in names
                },
            )
        return result

    subject = reader(capture_with_history, native=native)
    outcome = subject.portfolio_explorer(query="q3/", limit=1, offset=1)
    assert outcome["total"] == 3
    assert outcome["total_matches"] == 2
    assert outcome["records"][0]["portfolio_id"] == "q3/B"
    assert outcome["records"][0]["runtime_state"] == "UNKNOWN"
    assert outcome["truncated"] is False
    assert subject.portfolio_explorer(query="\n")["status"] == "BLOCKED"
    assert subject.portfolio_explorer(offset=10001)["status"] == "BLOCKED"


def test_owner_history_separates_releases_without_promotion():

    def provider(command):
        rec = capture_with_history(command)
        if command == "history":
            rec["native"]["rows"][0]["release_sha"] = "b" * 64
        return rec

    history = reader(provider).performance_history()
    assert history["status"] == "VERIFIED_OWNER_SHADOW_TAIL"
    assert {p["source_id"] for p in history["points"]} == {"a" * 64, "b" * 64}
    assert all(datetime.fromisoformat(p["timestamp"]).tzinfo == UTC for p in history["points"])


@pytest.mark.parametrize(
    "corruption",
    [
        "future_clock",
        "malformed_clock",
        "malformed_decimal",
        "missing_release",
        "out_of_range_sequence",
        "regressed_sequence",
        "malformed_day",
    ],
)
def test_owner_history_rejects_corrupt_rows_without_partial_promotion(corruption):
    def provider(command):
        rec = capture_with_history(command)
        if command == "history":
            rows = rec["native"]["rows"]
            if corruption == "future_clock":
                rows[1]["observed_at_ms"] = int((T0 + timedelta(days=1)).timestamp() * 1000)
            elif corruption == "malformed_clock":
                rows[1]["observed_at_ms"] = "invalid"
            elif corruption == "malformed_decimal":
                rows[1]["equity"] = "NaN"
            elif corruption == "missing_release":
                rows[1]["release_sha"] = None
            elif corruption == "out_of_range_sequence":
                rows[1]["journal_sequence"] = 13
            elif corruption == "regressed_sequence":
                rows[0]["journal_sequence"] = 13
            elif corruption == "malformed_day":
                rows[1]["day"] = "20301"
        return rec

    history = reader(provider).performance_history()
    assert history["status"] == "BLOCKED"
    assert history["points"] == []


def test_owner_history_marks_unknown_long_intervals_as_chart_gaps():

    def provider(command):
        rec = capture_with_history(command)
        if command == "history":
            rec["native"]["rows"][0]["observed_at_ms"] = int(
                (T0 - timedelta(hours=12)).timestamp() * 1000
            )
        return rec

    history = reader(provider).performance_history()
    assert history["status"] == "VERIFIED_OWNER_SHADOW_TAIL"
    equity = [p for p in history["points"] if p["metric"] == "equity"]
    assert len(equity) == 2
    assert len({p["segment"] for p in equity}) == 2
    assert equity[1]["gap_before"] is True
