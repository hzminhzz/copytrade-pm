"""FP-05/09 synthetic full-book -> shared receipt -> native PM04 T+300 -> PM03.

These are model-contract tests. No live wallet attestation, broker, or service.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from copytrade_pm.pm_forward_portfolios import P1, P14
from test_pm_forward_admission import _alter
from test_pm_forward_fill import BTC, _source_book
from test_pm_forward_journal import T, manifest


def at(seconds: int) -> str:
    return (datetime.fromisoformat(T) + timedelta(seconds=seconds)).isoformat()


def policy(members: tuple[str, ...], allocation: str) -> dict:
    return {
        "schema": "pm04_research_policy_v1",
        "version": "forward-paper-fixture-v1",
        "approval_reference": "synthetic-only",
        "pods": {
            name: {
                "budget_ref": f"fixture-budget-{name}",
                "daily_loss": "40",
                "max_drawdown": "80",
                "stress_loss": "100",
            }
            for name in members
        },
        "follower_allocations": {name: allocation for name in members},
        "nominal_portfolio_risk": "600",
        "max_gross_notional": "1000",
        "max_instrument_fraction_equity": "0.5",
        "max_stress_loss": "600",
        "reserve": "10",
        "max_signal_age_seconds": 300,
        "broker_max_age_seconds": 300,
        "reconcile_tolerance": "0.001",
        "batch_seconds": 300,
        "execution_policy": "ASYMMETRIC",
        "broker_required": False,
    }


def event(name: str, kind: str, second: int, policy_sha: str, inputs: dict) -> dict:
    return {
        "kind": kind,
        "run_id": name,
        "event_at": at(second),
        "source_event_at": at(second),
        "first_known_at": at(second),
        "hypothetical_fill_at": at(second + 2),
        "source_sha": digest(inputs),
        "sealed_policy_sha": policy_sha,
        "fixture_attested": True,
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
        "order_route": "NONE",
        "input": inputs,
    }


def engine(second: int, *, targets: list | None = None) -> dict:
    costs = {
        "fee_bps": "2",
        "full_spread_bps": "4",
        "slippage_bps": "1",
        "impact_bps_at_full_participation": "4",
        "max_participation": "0.1",
        "max_age_seconds": 300,
        "latency_seconds": 1,
    }
    return {
        "observations": [
            {
                "instrument": BTC.key,
                "event_at": at(second),
                "first_known_at": at(second),
                "mark": "100",
                "volume_base": "1000",
                "quality": "SYNTHETIC",
                "supported": True,
            }
        ],
        "shocks": [{BTC.key: "-0.05"}, {BTC.key: "0.05"}],
        "evidence": {
            "trusted": True,
            "account_state_known": True,
            "market_state_known": True,
            "market_coverage_valid": True,
            "pending_unknown_orders": False,
            "input_status": "RESEARCH_SYNTHETIC",
            "pm02_qualified": False,
            "hedge_break_loss": "10",
        },
        "costs": costs,
        "targets": targets if targets is not None else [],
    }


def market_contract(second: int, costs: dict) -> dict:
    row = {
        "schema": "paper_market_contract_v1",
        "instrument": BTC.key,
        "quality": "SYNTHETIC",
        "costs_sha": digest(costs),
        "session_open": True,
        "market_permitted": True,
        "first_known_at": at(second),
        "quantity_step": "0.01",
        "minimum_quantity": "0.01",
    }
    return {**row, "contract_sha": digest(row)}


def paper_signal(run_id, second, policy_sha, book, quantity, *, revision=1, volume="1000") -> dict:
    inputs = engine(
        second,
        targets=[
            {
                "pod": "S035",
                "instrument": BTC.key,
                "quantity": str(quantity),
                "revision": revision,
                "source_event_at": book["source_event_at"],
                "first_known_at": book["first_known_at"],
                "source_sha": book["snapshot_sha"],
                "budget_ref": "fixture-budget-S035",
            }
        ],
    )
    inputs["observations"][0]["volume_base"] = volume
    raw = event(run_id, "PM04_SIGNAL", second, policy_sha, inputs)
    raw["source_book"] = book
    raw["market_contracts"] = {BTC.key: market_contract(second, inputs["costs"])}
    return raw


def paper_tick(run_id, second, policy_sha) -> dict:
    inputs = engine(second)
    raw = event(run_id, "PM04_TICK", second, policy_sha, inputs)
    raw["market_contracts"] = {BTC.key: market_contract(second, inputs["costs"])}
    return raw


def _setup(tmp_path, *, source_mark="100"):
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    policies = {"P1": policy(P1.members, "3000"), "P14": policy(P14.members, "1600")}
    for portfolio in (P1, P14):
        row = manifest(portfolio.name, portfolio.name + "_account")
        book = replace(row.rulebook, confirmed=True, permitted=(BTC,))
        sealed = replace(
            row,
            rulebook=book,
            portfolio_sha=portfolio.sha,
            policy_sha=digest(policies[portfolio.name]),
        )
        campaign.register(sealed)
        campaign.record_event(
            portfolio.name,
            "configure",
            event(
                portfolio.name,
                "PM04_CONFIG",
                0,
                sealed.policy_sha,
                {"policy": policies[portfolio.name]},
            ),
        )
    source = _alter(
        _source_book(),
        wallet_id="S035",
        source_event_at=at(60),
        first_known_at=at(60),
        source_equity="20000",
        positions={BTC.key: "2"},
        source_marks={BTC.key: source_mark},
    )
    receipt = {
        "schema": "paper_first_known_source_v1",
        "source_id": "S035",
        "source_event_at": at(60),
        "first_known_at": at(60),
        "captured_at": at(60),
        "payload_sha": source["snapshot_sha"],
    }
    journal.append_source_receipt("S035", 1, "source_1", receipt)
    return journal, campaign, policies, source, receipt


def test_shared_receipt_respects_two_native_pm04_batch_engines(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    for run_id, qty in (("P1", "0.3"), ("P14", "0.16")):
        signal = paper_signal(run_id, 60, digest(policies[run_id]), book, qty)
        signal["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
        state = campaign.record_source_decision(run_id, "signal_1", signal)
        assert state["account"]["quantities"] == {}
        assert state["account"]["pm04"]["batch_open"][BTC.key] == at(60)
        early = campaign.record_event(
            run_id, "early", paper_tick(run_id, 359, digest(policies[run_id]))
        )
        assert early["account"]["quantities"] == {}
        due = campaign.record_event(
            run_id, "due", paper_tick(run_id, 360, digest(policies[run_id]))
        )
        assert due["account"]["quantities"][BTC.key] == qty
        assert due["source_cursors"] == {"S035": 1}
        assert journal.restore(run_id)["account"] == due["account"]
        assert journal.restore(run_id)["last_event_result"]["no_live_order_path"] is True
    assert (
        campaign.status("P1")["account"]["quantities"][BTC.key]
        != campaign.status("P14")["account"]["quantities"][BTC.key]
    )
    assert journal.source_status("S035")["cursor"] == 1


def test_later_whole_book_replaces_pending_not_due_clock(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    sha = digest(policies["P1"])
    first = paper_signal("P1", 60, sha, book, "0.3")
    first["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
    campaign.record_source_decision("P1", "first", first)
    newer_book = _alter(
        book,
        source_event_at=at(120),
        first_known_at=at(120),
        source_equity="40000",
        positions={BTC.key: "8"},
    )
    newer_receipt = {
        **receipt,
        "source_event_at": at(120),
        "first_known_at": at(120),
        "captured_at": at(120),
        "payload_sha": newer_book["snapshot_sha"],
    }
    journal.append_source_receipt("S035", 2, "source_2", newer_receipt)
    latest = paper_signal("P1", 120, sha, newer_book, "0.6", revision=2)
    latest["source_ref"] = {
        "source_id": "S035",
        "sequence": 2,
        "receipt_sha": digest(newer_receipt),
    }
    state = campaign.record_source_decision("P1", "latest", latest)
    assert state["account"]["pm04"]["batch_open"][BTC.key] == at(60)
    assert state["account"]["quantities"] == {}
    due = campaign.record_event("P1", "due", paper_tick("P1", 360, sha))
    assert due["account"]["quantities"][BTC.key] == "0.6"
    assert due["source_cursors"] == {"S035": 2}


def test_unfillable_reduction_preserves_signed_inventory(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    sha = digest(policies["P1"])
    first = paper_signal("P1", 60, sha, book, "0.3")
    first["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
    campaign.record_source_decision("P1", "first", first)
    due = campaign.record_event("P1", "due", paper_tick("P1", 360, sha))
    assert due["account"]["quantities"][BTC.key] == "0.3"
    flat_book = _alter(
        book,
        source_event_at=at(420),
        first_known_at=at(420),
        positions={},
    )
    flat_receipt = {
        **receipt,
        "source_event_at": at(420),
        "first_known_at": at(420),
        "captured_at": at(420),
        "payload_sha": flat_book["snapshot_sha"],
    }
    journal.append_source_receipt("S035", 2, "source_2", flat_receipt)
    reduction = paper_signal("P1", 420, sha, flat_book, "0", revision=2, volume="0")
    reduction["source_ref"] = {
        "source_id": "S035",
        "sequence": 2,
        "receipt_sha": digest(flat_receipt),
    }
    state = campaign.record_source_decision("P1", "reduce", reduction)
    assert state["account"]["quantities"][BTC.key] == "0.3"
    assert state["source_cursors"] == {"S035": 2}
    assert journal.restore("P1")["account"] == state["account"]


def test_source_notional_vs_different_follower_price_uses_native_weight_contract(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path, source_mark="110")
    target = paper_signal("P1", 60, digest(policies["P1"]), book, "0.33")
    target["source_ref"] = {
        "source_id": "S035",
        "sequence": 1,
        "receipt_sha": digest(receipt),
    }
    before = campaign.record_source_decision("P1", "source_mark_110", target)
    assert before["account"]["quantities"] == {}
    result = campaign.record_event("P1", "due", paper_tick("P1", 360, digest(policies["P1"])))
    assert Decimal(result["account"]["quantities"][BTC.key]) == Decimal("0.33")
    # Incorrect quantity-only scaling would have requested 0.30 BTC.
    assert Decimal(result["account"]["quantities"][BTC.key]) != Decimal("0.30")
    assert journal.restore("P1")["account"] == result["account"]


def test_source_target_override_rejected_before_account_effect(tmp_path) -> None:
    journal, campaign, policies, book, receipt = _setup(tmp_path)
    bad = paper_signal("P1", 60, digest(policies["P1"]), book, "100")
    bad["source_ref"] = {"source_id": "S035", "sequence": 1, "receipt_sha": digest(receipt)}
    with pytest.raises(ValueError, match="PM04_SOURCE_EQUITY_SIZING_MISMATCH"):
        campaign.record_source_decision("P1", "override", bad)
    assert journal.restore("P1")["cursor"] == 1
    assert journal.restore("P1")["source_cursors"] == {}
