"""Three independent v4 portfolio ledgers share one Vike minute price journal."""
from decimal import Decimal as D

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
from test_pm_forward_observed_paper import BTC, RAW_MARKET, add_source, at
from test_pm_vike_paper_integration import price


def test_vike_price_reuse_across_three_sealed_virtual_financial_accounts(tmp_path, monkeypatch):
    pin_reviewed_registry(monkeypatch)
    registry_path = full_registry(tmp_path)
    sources = PaperJournal(tmp_path / "shared-sources")
    prices = PaperJournal(tmp_path / "shared-vike-prices")
    price(prices, 10)
    portfolios = {
        name: ObservedP1Paper(
            source_db=sources.path, price_db=prices.path,
            price_mode="vike_minute", registry_db=registry_path,
            state_root=tmp_path / name, run_id="vike_" + name,
            portfolio_id=name, started_at=at(0),
            catalog={RAW_MARKET["symbol"]: RAW_MARKET},
        ) for name in ("P1", "P14", "P16")
    }
    add_source(sources, 1, 12, {BTC.key: "20"})
    for portfolio in portfolios.values():
        state = portfolio.step(at(14))
        assert state["execution_intents"]["S035"]["due_at"] == at(313)
    price(prices, 312)
    opened = {name: paper.step(at(313)) for name, paper in portfolios.items()}
    assert D(opened["P1"]["positions"][BTC.key]) == D("0.564")
    assert D(opened["P14"]["positions"][BTC.key]) == D("0.338")
    assert D(opened["P16"]["positions"][BTC.key]) == D("0.50760")
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
