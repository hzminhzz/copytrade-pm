"""FP-03 deterministic paper-only PM-03 fill contract."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_journal import T, manifest

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")


def _decision() -> dict:
    return {
        "kind": "SIMULATED_DECISION",
        "event_at": T,
        "hypothetical_fill_at": "2026-11-04T04:00:02+00:00",
        "evidence_class": "FORWARD_PAPER_SIMULATED_v1",
        "order_route": "NONE",
        "fixture_attested": True,
        "proposed": {"PM_A": {BTC.key: "1"}},
        "shocks": [{BTC.key: "-0.1"}],
        "observations": [
            {
                "instrument": BTC.key,
                "source_at": T,
                "first_known_at": T,
                "mark": "100",
                "volume_base": "100",
                "quality": "SYNTHETIC",
                "supported": True,
            }
        ],
        "costs": {
            "fee_bps": "2",
            "full_spread_bps": "4",
            "slippage_bps": "1",
            "impact_bps_at_full_participation": "4",
            "max_participation": "0.1",
            "max_age_seconds": 300,
            "latency_seconds": 1,
        },
    }


def test_costed_paper_fill_replay_and_no_real_order(tmp_path) -> None:
    manifest_row = manifest("run_1", "acct_1")
    rules = replace(manifest_row.rulebook, confirmed=True, permitted=(BTC,))
    campaign = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    campaign.register(replace(manifest_row, rulebook=rules))
    state = campaign.record_event("run_1", "fill_1", _decision())
    assert state["account"]["quantities"][BTC.key] == "1"
    assert D(state["account"]["costs"]) > 0
    assert D(state["account"]["equity"]) < D("10000")
    journal = PaperJournal(tmp_path / "paper")
    result = journal.restore("run_1")["last_event_result"]
    assert result["execution"]["fills"][0]["instrument"] == BTC.key
    assert (
        result["execution"]["fills"][0]["hypothetical_fill_at"]
        == _decision()["hypothetical_fill_at"]
    )
    assert result["execution"]["fills"][0]["fee"] != "0"
    assert journal.restore("run_1")["cursor"] == 1
    assert state["order_route"] == "NONE"


def test_partial_capacity_preserves_unfilled_exposure(tmp_path) -> None:
    original = manifest("run_1", "acct_1")
    rules = replace(original.rulebook, confirmed=True, permitted=(BTC,))
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    campaign.register(replace(original, rulebook=rules))
    event = _decision()
    event["observations"][0]["volume_base"] = "2"
    state = campaign.record_event("run_1", "partial", event)
    result = journal.restore("run_1")["last_event_result"]["execution"]
    assert result["status"] == "PARTIAL"
    assert result["fills"][0]["quantity"] == "0.2"
    assert result["remaining"][BTC.key] == "0.8"
    assert state["account"]["quantities"][BTC.key] == "0.2"
    assert journal.restore("run_1")["account"] == state["account"]


def test_paper_fill_refuses_broker_route_and_unconfirmed_rules(tmp_path) -> None:
    campaign = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    campaign.register(manifest("run_1", "acct_1"))
    with pytest.raises(ValueError, match="PAPER_RULEBOOK_UNCONFIRMED"):
        campaign.record_event("run_1", "fill_1", _decision())
    assert campaign.status("run_1")["cursor"] == 0
    second = replace(manifest("run_2", "acct_2").rulebook, confirmed=True, permitted=(BTC,))
    campaign.register(replace(manifest("run_2", "acct_2"), rulebook=second))
    with pytest.raises(ValueError, match="PAPER_ORDER_ROUTE_FORBIDDEN"):
        campaign.record_event("run_2", "bad", {**_decision(), "order_route": "BYBIT"})
    assert campaign.status("run_2")["cursor"] == 0
