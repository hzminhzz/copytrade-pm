"""Three independent v4 portfolio ledgers share one Vike minute price journal."""
from decimal import Decimal as D

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_vike_market_catalog import NativePaperContract
from copytrade_pm.pm03_account import digest
from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
from test_pm_forward_observed_paper import BTC, at
from test_pm_vike_paper_integration import official_frame, official_observer, price


def test_vike_price_reuse_across_three_sealed_virtual_financial_accounts(tmp_path, monkeypatch):
    pin_reviewed_registry(monkeypatch)
    registry_path = full_registry(tmp_path)
    sources = PaperJournal(tmp_path / "shared-sources")
    prices = PaperJournal(tmp_path / "shared-vike-prices")
    official = official_observer(sources)
    native = NativePaperContract(
        instrument=BTC, amount_step=D("0.001"),
        minimum_notional=D("10"), active=True,
        market_known_at=at(0), catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )
    portfolios = {
        name: ObservedP1Paper(
            source_db=sources.path, price_db=prices.path,
            price_mode="vike_minute", registry_db=registry_path,
            state_root=tmp_path / name, run_id="vike_" + name,
            portfolio_id=name, started_at=at(0), catalog={},
            native_contracts={BTC.key: native},
        ) for name in ("P1", "P14", "P16")
    }
    official.observe(official_frame(12, 20), at(13))
    for portfolio in portfolios.values():
        state = portfolio.step(at(14))
        assert state["execution_intents"]["S035"]["due_at"] == at(313)
        assert BTC in portfolio.run.account.rulebook.permitted
    price(prices, 312)
    opened = {name: paper.step(at(313)) for name, paper in portfolios.items()}
    assert D(opened["P1"]["positions"][BTC.key]) == D("0.564")
    assert D(opened["P14"]["positions"][BTC.key]) == D("0.338")
    assert D(opened["P16"]["positions"][BTC.key]) == D("0.507")
    assert len({state["ledger_head_sha"] for state in opened.values()}) == 3
    assert [opened[name]["pod_risk"]["S035"]["remaining_drawdown"]
            for name in ("P1", "P14", "P16")] != [
                opened["P1"]["pod_risk"]["S035"]["remaining_drawdown"]
            ] * 3
    assert all(
        state["execution_policy_version"].endswith("v4")
        and state["real_broker_fills"] == 0
        for state in opened.values()
    )
    price(prices, 319)
    official.observe(official_frame(319, 0), at(320))
    closed = {name: paper.step(at(321)) for name, paper in portfolios.items()}
    assert all(state["positions"] == {} for state in closed.values())
    assert all(state["pending_exits"]["S035"]["status"] == "EXIT_FILLED"
               for state in closed.values())
    assert len({state["ledger_head_sha"] for state in closed.values()}) == 3
