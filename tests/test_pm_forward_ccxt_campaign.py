"""CCXT L2 public paper-campaign handoff must not invent executed volume."""

from dataclasses import replace

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_ccxt_market import fixture
from test_pm_forward_fill import BTC, _decision
from test_pm_forward_journal import manifest


def test_ccxt_public_l2_to_campaign_never_invents_trade_volume(tmp_path):
    quote, observed, _, _ = fixture()
    base = manifest("ccxt_paper", "virtual_ccxt")
    worker = PaperCampaign(journal=PaperJournal(tmp_path / "paper"))
    worker.register(
        replace(base, rulebook=replace(base.rulebook, confirmed=True, permitted=(BTC,)))
    )
    event = _decision()
    event["event_at"] = "2026-11-04T04:00:04+00:00"
    event["hypothetical_fill_at"] = "2026-11-04T04:00:06+00:00"
    event["observations"] = [
        {
            "instrument": observed["instrument"],
            "source_at": observed["event_at"],
            "first_known_at": observed["first_known_at"],
            "mark": observed["mark"],
            "volume_base": None,
            "quality": "VERIFIED_QUOTE",
            "supported": True,
        }
    ]
    event["market_contracts"] = {
        BTC.key: quote.contract(costs=event["costs"], as_of=event["event_at"])
    }
    event["market_evidence"] = {BTC.key: quote.payload()}
    committed = worker.record_event("ccxt_paper", "l2_only", event)
    assert committed["cursor"] == 1
    assert committed["account"]["quantities"] == {}
    assert committed["account"]["cash"] == "10000"
    assert committed["account"]["risk"] == "RED"
    receipt = PaperJournal(tmp_path / "paper").restore("ccxt_paper")
    assert receipt["last_event_result"] == {"status": "BLOCKED", "reason": "INCOMPLETE_MARKET"}
    assert not hasattr(worker, "order")
    assert not hasattr(worker, "fill")
    assert committed["order_route"] == "NONE"
