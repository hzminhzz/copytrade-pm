"""Persistent halt, funding and reduction faults in retained PM03 journals."""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from test_pm_forward_fill import BTC


def decision_at(stamp, *, fresh_quote):
    from test_pm_forward_fill import _decision

    event = _decision()
    event["event_at"] = stamp
    event["hypothetical_fill_at"] = (
        datetime.fromisoformat(stamp) + timedelta(seconds=1)
    ).isoformat()
    event["proposed"] = {}
    book = event["source_book"]
    book.update(first_known_at=stamp, source_event_at=stamp)
    book["snapshot_sha"] = digest({k: v for k, v in book.items() if k != "snapshot_sha"})
    contract = event["market_contracts"][BTC.key]
    contract["first_known_at"] = stamp
    contract["contract_sha"] = digest({k: v for k, v in contract.items() if k != "contract_sha"})
    if fresh_quote:
        event["observations"][0].update(first_known_at=stamp, source_at=stamp)
    return event


@pytest.mark.parametrize("loss_amount,can_reduce", [("-150", True), ("-1500", False)])
def test_cf02_loss_halt_funding_stale_exit_restart_reduction_or_unresolved(
    tmp_path, loss_amount, can_reduce
):
    from test_pm_forward_funding import _filled, _funding

    campaign, journal = _filled(tmp_path)
    funding = _funding()
    funding.update(amount=loss_amount, allocated={"PM_A": loss_amount})
    loss = campaign.record_event("run_1", "loss", funding)
    assert Decimal(loss["account"]["equity"]) < 10000
    if can_reduce:
        loss = journal.append(
            "run_1",
            "loss-budget-halt",
            {
                "kind": "HALT",
                "reason": "LOSS_BUDGET_HALT",
                "event_at": "2026-11-04T04:05:00+00:00",
            },
        )
    assert loss["account"]["risk"] == "HALT"
    reason = loss["account"]["halt_reason"]
    unknown = journal.append(
        "run_1",
        "unknown",
        {
            "kind": "FUNDING_UNKNOWN",
            "event_at": "2026-11-04T04:05:01+00:00",
        },
    )
    assert unknown["account"]["risk"] == "HALT"
    stale = decision_at("2026-11-04T04:10:00+00:00", fresh_quote=False)
    blocked = journal.append("run_1", "failed-exit", stale)
    assert blocked["account"]["quantities"][BTC.key] == "1"
    assert blocked["account"]["risk"] == "HALT"
    resumed = PaperJournal(journal.root)
    assert resumed.restore("run_1") == blocked
    valid = decision_at("2026-11-04T04:10:01+00:00", fresh_quote=True)
    reduced = resumed.append("run_1", "valid-reduction", valid)
    expected = 0 if can_reduce else 1
    assert Decimal(reduced["account"]["quantities"].get(BTC.key, "0")) == expected
    if not can_reduce:
        assert "UNAUTHORIZED_OR_BREACHED" in reduced["last_event_result"]["execution"]["rejections"]
    assert reduced["account"]["risk"] == "HALT"
    assert reduced["account"]["halt_reason"] == reason
    assert resumed.append("run_1", "valid-reduction", valid) == reduced
    with pytest.raises(ValueError, match="PAPER_ORDER_ROUTE_FORBIDDEN"):
        resumed.append("run_1", "broker-route", {**valid, "order_route": "BROKER"})
    assert resumed.restore("run_1") == reduced
