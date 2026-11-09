"""CF05: a changed source scope reaches each independent offline/online consumer."""

from decimal import Decimal

from copytrade_pm.pm03_account import digest
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observed_paper import ObservedP1Paper
from copytrade_pm.pm_forward_source_stream import PersistentAccount
from copytrade_pm.pm_vike_market_catalog import NativePaperContract
from test_pm_forward_multi_portfolio import full_registry, pin_reviewed_registry
from test_pm_forward_observed_paper import ADDRESSES, BTC, at
from test_pm_vike_paper_integration import official_observer, official_frame, price


def test_cf05_shared_scope_change_offline_portfolio_and_independent_held_finance(
    tmp_path, monkeypatch
):
    pin_reviewed_registry(monkeypatch)
    registry = full_registry(tmp_path)
    tape, prices = PaperJournal(tmp_path / "source"), PaperJournal(tmp_path / "prices")
    affected = official_observer(tape)
    independent = PersistentAccount(
        journal=tape,
        alias="S051",
        address=ADDRESSES["S051"],
        dex_catalog=[None],
        subaccounts=None,
        parent_alias="S051",
        scope_sha="b" * 64,
    )
    independent.begin(at(0))

    def observe_b(seconds, quantity):
        frame = official_frame(seconds, quantity)
        frame["data"]["user"] = ADDRESSES["S051"]
        return independent.observe(frame, at(seconds + 1))

    observe_b(1, 0)
    contract = NativePaperContract(
        instrument=BTC,
        amount_step=Decimal("0.001"),
        minimum_notional=Decimal("10"),
        active=True,
        market_known_at=at(0),
        catalog_sha=digest(["native", BTC.key]),
        hip3=False,
    )

    def reopen(name, first=False):
        return ObservedP1Paper(
            source_db=tape.path,
            price_db=prices.path,
            price_mode="vike_minute",
            registry_db=registry,
            state_root=tmp_path / name,
            run_id="combined_" + name,
            portfolio_id=name,
            catalog={},
            native_contracts={BTC.key: contract},
            **({"started_at": at(0)} if first else {}),
        )

    a, b = reopen("P14", True), reopen("P16", True)
    affected.observe(official_frame(12, 20), at(13))
    observe_b(12, 10)
    for paper in (a, b):
        paper.step(at(14))
    price(prices, 312)
    for paper in (a, b):
        assert paper.step(at(313))["positions"]
    held = [dict(p.run.account.pm_quantities["S035"]) for p in (a, b)]
    independent_held = [
        p.run.account.pm_quantities.get("S051", {}).get(BTC, Decimal("0")) for p in (a, b)
    ]
    assert held[0] != held[1]  # Fixed policies retain separate sizing and risk.
    affected.observe(official_frame(330, 30), at(331))
    observe_b(330, 15)
    for paper in (a, b):
        paper.step(at(332))
    offline_before = b.run.account.snapshot()
    unaffected_epoch = (
        independent.checkpoint["epoch"]
        if "epoch" in independent.checkpoint
        else independent.progress.head["event"]["epoch"]
    )
    affected.reconfigure(
        dex_catalog=[None, {"name": "xyz"}],
        observer_generation="c" * 64,
        contract_generation="d" * 64,
        known_at=at(400),
    )
    online = a.step(at(401))
    assert online["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    assert a.run.account.pm_quantities["S035"] == held[0]
    assert b.run.account.snapshot() == offline_before
    observe_b(618, 15)
    assert independent.progress.head["event"]["epoch"] == unaffected_epoch
    price(prices, 630)
    assert a.step(at(632))["execution_intents"]["S051"]["status"] == "FILLED"
    b = reopen("P16")
    after = b.step(at(633))
    assert after["execution_intents"]["S035"]["status"] == "CANCELED_SOURCE_GAP"
    for index, paper in enumerate((a, b)):
        assert paper.run.account.pm_quantities["S035"] == held[index]
        assert paper.run.account.pm_quantities["S051"][BTC] > independent_held[index]
        assert paper.run.restore()["account"] == paper.run.account.snapshot()
    assert not affected.checkpoint["baseline_valid"]
    assert independent.checkpoint["baseline_valid"]
    assert a.run.account.cash != b.run.account.cash
    assert after["real_broker_fills"] == 0
