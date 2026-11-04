"""FP-08 signed funding, duplicate-interval and margin unknown contracts."""

from dataclasses import replace

import pytest

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_paper import PaperCampaign
from test_pm_forward_fill import BTC, _decision
from test_pm_forward_journal import manifest


def _funding(*, margin=True) -> dict:
    t = "2026-11-04T04:05:00+00:00"
    model = {
        "schema": "paper_margin_contract_v1",
        "synthetic_fixture": True,
        "margin_mode": "CROSS",
        "first_known_at": t,
        "initial_margin_fraction": "0.1",
        "maintenance_margin_fraction": "0.05",
    }
    return {
        "kind": "FUNDING",
        "event_at": t,
        "source_event_at": t,
        "first_known_at": t,
        "fixture_attested": True,
        "instrument": BTC.key,
        "interval_id": "funding-20261104-0405",
        "amount": "-0.02",
        "allocated": {"PM_A": "-0.02"},
        "marks": {BTC.key: "110"},
        "margin_contract": {**model, "contract_sha": digest(model)} if margin else None,
    }


def _filled(tmp_path) -> tuple[PaperCampaign, PaperJournal]:
    journal = PaperJournal(tmp_path / "paper")
    campaign = PaperCampaign(journal=journal)
    m = manifest("run_1", "acct_1")
    rules = replace(m.rulebook, confirmed=True, permitted=(BTC,))
    campaign.register(replace(m, rulebook=rules))
    campaign.record_event("run_1", "fill", _decision())
    return campaign, journal


def test_funding_cash_and_mark_reconcile_after_restart(tmp_path) -> None:
    campaign, journal = _filled(tmp_path)
    first = campaign.status("run_1")
    posted = campaign.record_event("run_1", "funding", _funding())
    assert posted["cursor"] == 2
    assert posted["account"]["funding"] == "-0.02"
    assert posted["account"]["quantities"] == first["account"]["quantities"]
    assert posted["account"]["marks"][BTC.key] == "110"
    assert posted["account"]["risk"] != "HALT"
    actual = PaperJournal(journal.root).restore("run_1")
    assert actual["account"] == posted["account"]
    assert actual["last_event_result"]["margin"]["status"] == "MODELED_MARGIN_OK"
    assert actual["last_event_result"]["forced_exit_assumed"] is False
    assert campaign.record_event("run_1", "funding", _funding()) == posted
    with pytest.raises(ValueError, match="DUPLICATE_FUNDING_INTERVAL"):
        campaign.record_event("run_1", "funding_second_id", _funding())
    assert journal.restore("run_1")["cursor"] == 2


def test_unknown_funding_and_margin_never_infer_zero_or_liquidation(tmp_path) -> None:
    campaign, journal = _filled(tmp_path)
    status = campaign.record_event(
        "run_1", "unknown", {"kind": "FUNDING_UNKNOWN", "event_at": "2026-11-04T04:03:00+00:00"}
    )
    assert status["account"]["risk"] == "RED"
    assert status["account"]["funding"] == "0"
    assert status["account"]["quantities"][BTC.key] == "1"
    other, j2 = _filled(tmp_path / "other")
    result = other.record_event("run_1", "fund", _funding(margin=False))
    assert result["account"]["risk"] == "RED"
    assert j2.restore("run_1")["last_event_result"]["margin"]["status"] == "UNKNOWN_LIQUIDATION"
    assert result["account"]["quantities"][BTC.key] == "1"


def test_funding_requires_observed_causal_interval(tmp_path) -> None:
    campaign, journal = _filled(tmp_path)
    bad = _funding()
    bad["first_known_at"] = "2026-11-04T04:06:00+00:00"
    with pytest.raises(ValueError, match="FUNDING_CLOCK_ORDER_INVALID"):
        campaign.record_event("run_1", "bad", bad)
    assert journal.restore("run_1")["cursor"] == 1
