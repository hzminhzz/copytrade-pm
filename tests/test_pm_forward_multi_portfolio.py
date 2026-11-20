"""Regression contracts for isolated registry-sealed P14 and P16 paper campaigns."""

from contextlib import closing
from decimal import Decimal as D
import sqlite3

import pytest

from copytrade_pm.roster import RosterStore
from roster_fixture import WALLETS, add_account
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import (
    ObservedP1Paper,
    PAPER_PROFILES,
    _policy,
    _verify_portfolio_selection,
)
from test_pm_forward_observed_paper import (
    ADDRESSES,
    BTC,
    RAW_MARKET,
    add_quote,
    add_source,
    at,
    registry,
)


def full_registry(tmp_path):
    path = registry(tmp_path / "roster.sqlite")
    addresses = {**ADDRESSES, "S064": WALLETS[3], "Whale_0x5f94": WALLETS[4]}
    with RosterStore(path, writable=True) as store:
        for name in ("P14", "P16"):
            profile = PAPER_PROFILES[name]
            add_account(
                store,
                name,
                {seat: addresses[seat] for seat in profile.source_ids},
                k=profile.k,
                risk=profile.risk,
            )
    return path


def test_registry_profile_requires_real_seal_not_just_matching_names(tmp_path):
    path = full_registry(tmp_path)
    for name in ("P14", "P16"):
        selection = _verify_portfolio_selection(path, PAPER_PROFILES[name], as_of=at(0))
        assert selection["definition_sha256"]
        assert selection["version"] == 1
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("DROP TRIGGER leases_no_update")
        con.execute("UPDATE leases SET wallet='drift' WHERE account_id='P14'")
    with pytest.raises(ValueError, match="SELECTION_MEMBER_DRIFT"):
        _verify_portfolio_selection(path, PAPER_PROFILES["P14"], as_of=at(0))


def test_only_reviewed_paper_scenarios_admitted(tmp_path):
    tape = PaperJournal(tmp_path / "source")
    path = full_registry(tmp_path)
    with pytest.raises(ValueError, match="PAPER_PORTFOLIO_HAS_NO_APPROVED_RESEARCH_SCENARIO"):
        ObservedP1Paper(
            source_db=tape.path,
            registry_db=path,
            state_root=tmp_path / "private",
            run_id="triada",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            portfolio_id="regime.macro/TriadA",
            started_at=at(0),
        )
    assert set(PAPER_PROFILES) == {"P1", "P14", "P16"}


def test_two_sealed_research_portfolios_receive_same_source_in_independent_accounts(
    tmp_path,
):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10, size=200)
    path = full_registry(tmp_path)
    portfolio = {}
    for name in ("P14", "P16"):
        portfolio[name] = ObservedP1Paper(
            source_db=tape.path,
            registry_db=path,
            state_root=tmp_path / name,
            run_id="paper_" + name.lower(),
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            portfolio_id=name,
            started_at=at(0),
        )
        assert portfolio[name].profile.nominal_risk == "600"
        assert set(portfolio[name].run.account.pm04_state["policy"]["pods"]) == set(
            PAPER_PROFILES[name].source_ids
        )

    add_source(tape, 1, 12, {BTC.key: "20"})
    for name in ("P14", "P16"):
        pending = portfolio[name].step(at(14))
        assert pending["portfolio_id"] == name
        assert pending["execution_intents"]["S035"]["due_at"] == at(313)
        assert pending["positions"] == {}
        assert pending["real_broker_fills"] == 0

    add_quote(tape, 312, size=200)
    a = portfolio["P14"].step(at(313))
    b = portfolio["P16"].step(at(313))
    assert D(a["positions"][BTC.key]) == D("0.338")
    assert D(b["positions"][BTC.key]) == D("0.50760")
    assert D("0") < D(a["pod_risk"]["S035"]["remaining_drawdown"]) < D("120")
    assert D("0") < D(b["pod_risk"]["S035"]["remaining_drawdown"]) < D("180")
    assert portfolio["P14"].policy["pods"]["S035"]["max_drawdown"] == "120"
    assert portfolio["P16"].policy["pods"]["S035"]["max_drawdown"] == "180"
    assert a["last_event_id"] != "configure"
    assert b["last_event_id"] != "configure"
    assert a["order_route"] == b["order_route"] == "NONE"
    assert a["sizing_evidence_class"] == "GEMINI_PHASE3_REFERENCE_PAPER_SCENARIO"
    assert b["sizing_evidence_class"].startswith("DERIVED_PHASE3")

    for name in ("P14", "P16"):
        original = portfolio[name]
        restarted = ObservedP1Paper(
            source_db=tape.path,
            registry_db=path,
            state_root=tmp_path / name,
            run_id="paper_" + name.lower(),
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            portfolio_id=name,
        )
        assert restarted.run.account.snapshot() == original.run.account.snapshot()
        assert restarted.last_seen["S035"] == 1
        assert restarted.run.ledger.read()[-1]["sha"] == original.run.ledger.read()[-1]["sha"]


def test_wrong_portfolio_id_or_new_registry_seal_cannot_open_existing_run(
    tmp_path,
):
    tape = PaperJournal(tmp_path / "source")
    add_quote(tape, 10)
    path = full_registry(tmp_path)
    original = ObservedP1Paper(
        source_db=tape.path,
        registry_db=path,
        state_root=tmp_path / "private",
        run_id="p14",
        catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        portfolio_id="P14",
        started_at=at(0),
    )
    before = original.run.ledger.read()
    with pytest.raises(ValueError, match="PAPER_RESTART_MANIFEST_POLICY_DRIFT"):
        ObservedP1Paper(
            source_db=tape.path,
            registry_db=path,
            state_root=tmp_path / "private",
            run_id="p14",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            portfolio_id="P16",
        )

    with closing(sqlite3.connect(path)) as con, con:
        con.execute("DROP TRIGGER books_no_update")
        con.execute("UPDATE books SET book_sha='drift' WHERE account_id='P14'")
    with pytest.raises(ValueError, match="SELECTION_MEMBER_DRIFT"):
        ObservedP1Paper(
            source_db=tape.path,
            registry_db=path,
            state_root=tmp_path / "private",
            run_id="p14",
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
            portfolio_id="P14",
        )
    assert original.run.ledger.read() == before


def test_risk_budget_profile_sum_and_p1_legacy_parity():
    p14 = PAPER_PROFILES["P14"]
    p16 = PAPER_PROFILES["P16"]
    assert sum(map(D, p14.risk.values()), D("0")) == D("600")
    assert sum(map(D, p16.risk.values()), D("0")) == D("600")
    assert _policy()["fixed_k_by_pod"] == {
        "S035": "0.0282",
        "S051": "0.0430",
        "S053": "0.0296",
    }
    assert _policy()["pods"]["S035"] == {
        "budget_ref": "p1_observed_paper_S035",
        "daily_loss": "150",
        "max_drawdown": "200",
        "stress_loss": "200",
    }
