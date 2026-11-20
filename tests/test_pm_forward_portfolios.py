"""FP-09 blocked-yet-independent P1 and P14 portfolio admission."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm.pm_forward_admission import admit_source_book
from copytrade_pm.pm_forward_paper import PaperCampaign
from copytrade_pm.pm_forward_portfolios import (
    P1,
    P14,
    PaperPortfolioView,
    load_sealed_paper_portfolio,
)
from copytrade_pm.roster import RosterStore
from copytrade_pm.roster.sealed import timestamp_ms
from roster_fixture import WALLETS, add_account
from test_pm_forward_admission import _alter
from test_pm_forward_fill import _source_book
from test_pm_forward_journal import T, manifest


def test_two_frozen_10k_accounts_and_shared_source_fanout(tmp_path: Path) -> None:
    assert P1.members == ("S035", "S051", "S053")
    assert len(P14.members) == 5 and "S064" in P14.members
    assert "Whale_0x5f94" in P14.members
    assert P1.nominal_risk_per_member == "200"
    assert P14.nominal_risk_per_member == "120"
    coordinator = PaperPortfolioView(
        PaperCampaign(), registry_db=_fixture_registry(tmp_path / "registry.sqlite")
    )
    coordinator.register(P1, replace(manifest("p1", "p1_account"), portfolio_sha=P1.sha))
    coordinator.register(P14, replace(manifest("p14", "p14_account"), portfolio_sha=P14.sha))
    for name in ("P1", "P14"):
        state = coordinator.status(name)
        assert state["account"]["cash"] == "10000"
        assert state["account"]["quantities"] == {}
        assert state["source_admission"] == "BLOCKED"
        assert state["order_route"] == "NONE"
    shared = admit_source_book(
        _source_book(), decision_at=T, fill_at=T, allow_synthetic_fixture=True
    )
    result = coordinator.observe("S035", shared)
    assert result == {"P1": "BLOCKED", "P14": "BLOCKED"}
    assert "S064" in coordinator.status("P14")["missing_members"]
    assert "S064" not in coordinator.status("P1")["missing_members"]
    broken = admit_source_book(
        _alter(_source_book(), source_equity=None),
        decision_at=T,
        fill_at=T,
        allow_synthetic_fixture=True,
    )
    coordinator.observe("S064", broken)
    assert "S064" in coordinator.status("P14")["rejected_members"]
    assert coordinator.status("P1")["rejected_members"] == {}
    assert coordinator.status("P1")["account"] == coordinator.campaign.status("p1")["account"]


def test_resealing_or_cross_portfolio_manifest_fails(tmp_path: Path) -> None:
    view = PaperPortfolioView(
        PaperCampaign(), registry_db=_fixture_registry(tmp_path / "registry.sqlite")
    )
    with pytest.raises(ValueError, match="PORTFOLIO_MANIFEST_SHA_MISMATCH"):
        view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P14.sha))
    view.register(P1, replace(manifest("p1", "acct"), portfolio_sha=P1.sha))
    with pytest.raises(ValueError, match="DUPLICATE_PORTFOLIO_RUN_ID"):
        view.register(P14, replace(manifest("p1", "other"), portfolio_sha=P14.sha))


def _fixture_registry(db_path: Path) -> Path:
    with RosterStore(db_path, create=True) as store:
        for profile in (P1, P14):
            add_account(
                store,
                profile.name,
                dict(zip(profile.members, WALLETS, strict=False)),
                at_ms=timestamp_ms(T),
            )
        add_account(
            store, "dynamic", {"seat_1": WALLETS[1], "seat_2": WALLETS[2]}, at_ms=timestamp_ms(T)
        )
    return db_path


def test_dynamic_sealed_portfolio_loads_seat_ids(tmp_path: Path) -> None:
    path = _fixture_registry(tmp_path / "roster.sqlite")
    portfolio = load_sealed_paper_portfolio("dynamic", path, as_of=T)
    assert portfolio.members == ("seat_1", "seat_2")
    assert portfolio.definition_sha256
    view = PaperPortfolioView(PaperCampaign(), registry_db=path)
    view.register(portfolio, replace(manifest("paper", "acct"), portfolio_sha=portfolio.sha))
    assert view.status("dynamic")["order_route"] == "NONE"
    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        load_sealed_paper_portfolio("unknown", path, as_of=T)


def test_tampered_seal_cannot_register_paper(tmp_path: Path) -> None:
    path = _fixture_registry(tmp_path / "roster.sqlite")
    portfolio = load_sealed_paper_portfolio("dynamic", path, as_of=T)
    with closing(sqlite3.connect(path)) as con, con:
        con.execute("DROP TRIGGER leases_no_update")
        con.execute("UPDATE leases SET wallet='drift' WHERE account_id='dynamic'")
    view = PaperPortfolioView(PaperCampaign(), registry_db=path)
    with pytest.raises(ValueError, match="UNSEALED_FORWARD_PAPER_PORTFOLIO"):
        view.register(portfolio, replace(manifest("paper", "acct"), portfolio_sha=portfolio.sha))
