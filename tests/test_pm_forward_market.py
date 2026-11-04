"""FP-07 fail-closed paper market and lot evidence contracts."""

from dataclasses import replace

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_fill import BTC, _decision
from test_pm_forward_journal import manifest


def _change_contract(event: dict, **changes) -> dict:
    previous = event["market_contracts"][BTC.key]
    changed = {key: value for key, value in previous.items() if key != "contract_sha"}
    changed.update(changes)
    return {**event, "market_contracts": {BTC.key: {**changed, "contract_sha": digest(changed)}}}


@pytest.mark.parametrize(
    ("delta", "reason"),
    [
        ({"session_open": False}, "MARKET_SESSION_UNKNOWN_OR_CLOSED"),
        ({"market_permitted": False}, "MARKET_NOT_PERMITTED"),
        ({"quality": "VERIFIED_QUOTE"}, "MARKET_QUALITY_MISMATCH"),
        ({"first_known_at": "2026-11-04T04:01:00+00:00"}, "MARKET_CONTRACT_NOT_YET_KNOWN"),
        (
            {"quantity_step": "0.3", "minimum_quantity": "0.3"},
            "MARKET_UNSUPPORTED_QUANTITY_INCREMENT",
        ),
        ({"instrument": "hyperliquid/mainnet:perp:xyz/BTC"}, "MARKET_NATIVE_ID_MISMATCH"),
    ],
)
def test_contract_refuses_market_without_synthetic_fill(tmp_path, delta, reason) -> None:
    m = manifest("run_1", "acct_1")
    rules = replace(m.rulebook, confirmed=True, permitted=(BTC,))
    campaign = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    campaign.register(replace(m, rulebook=rules))
    event = _change_contract(_decision(), **delta)
    state = campaign.record_event("run_1", "blocked_market", event)
    assert state["account"]["quantities"] == {}
    assert state["cursor"] == 1
    result = PaperJournal(tmp_path / "paper").restore("run_1")["last_event_result"]
    assert result["status"] == "BLOCKED_MARKET"
    assert reason in result["reason_codes"]


def test_cost_policy_hash_mismatch_blocks(tmp_path) -> None:
    m = manifest("run_1", "acct_1")
    rules = replace(m.rulebook, confirmed=True, permitted=(BTC,))
    campaign = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    campaign.register(replace(m, rulebook=rules))
    event = _decision()
    event["costs"]["fee_bps"] = "200"
    state = campaign.record_event("run_1", "tampered_costs", event)
    assert state["account"]["quantities"] == {}
    result = PaperJournal(tmp_path / "paper").restore("run_1")["last_event_result"]
    assert "MARKET_COST_POLICY_SHA_MISMATCH" in result["reason_codes"]
