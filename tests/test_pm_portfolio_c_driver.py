"""Portfolio C true PM-04 account handoff and exact native HIP-3 safety contracts."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
import json

import pytest

from copytrade_pm.pm03_account import Account, Instrument
from copytrade_pm.pm03_execution import _allocate, CostModel, MarketObservation, execute_targets
from copytrade_pm.pm04_shadow import _fund_independent_pod_budgets
from copytrade_pm.pm_portfolio_c_driver import (
    PODS,
    START,
    _policy,
    _rulebook,
    native_to_pm,
    pm_to_native,
    permitted_class,
    run_one,
)
from copytrade_pm.pm36_e3 import session_multiplier
from copytrade_pm.pm_shadow import MinuteBar
from test_pm04_shadow import engine, event, make_run, signal, target


def test_exact_namespace_is_bijective_and_propr_scope_separate():
    for native in (
        "hyperliquid:mainnet:perp:xyz:CL",
        "hyperliquid:mainnet:perp:xyz:XYZ100",
        "hyperliquid:mainnet:perp:default:BTC",
    ):
        assert pm_to_native(native_to_pm(native)) == native
    assert native_to_pm("hyperliquid:mainnet:perp:xyz:CL") != native_to_pm(
        "hyperliquid:mainnet:perp:default:CL"
    )
    with pytest.raises(ValueError):
        pm_to_native("propr/challenge/CL")
    snapshot = {
        "market_symbols": {
            "crypto": ["BTC"],
            "indices": ["XYZ100"],
            "commodities": ["CL"],
            "equities": [],
        }
    }
    assert permitted_class("xyz:CL", snapshot) == "TENTATIVE_XYZ_HIP3_DISPLAY_MATCH"
    assert permitted_class("xyz:XYZ100", snapshot) == "TENTATIVE_XYZ_HIP3_DISPLAY_MATCH"
    assert permitted_class("io:CL", snapshot) is None
    assert permitted_class("BTC", snapshot) == "DISPLAY_NATIVE_CRYPTO_MATCH"


def test_partial_allocation_never_exceeds_requested_pod_delta():
    books = {
        "CO-001": D("0.000000000000000000000001"),
        "VS066": D("0.1333333333333333333333333333"),
        "W015": D("0.1000000000000000000000000000"),
    }
    requested = sum(books.values(), D(0))
    for portion in (requested, requested * D("0.9"), D("0.001")):
        allocated = _allocate(portion, books)
        assert abs(sum(allocated.values(), D(0)) - portion) < D("1e-26")
        assert all(D(0) <= v <= books[k] for k, v in allocated.items())


def test_session_volatility_ignores_missing_hours_and_future_marks():
    now = datetime(2026, 7, 1, tzinfo=UTC)
    history = []
    for i in range(841, 0, -1):
        at = now - timedelta(hours=i)
        if at.weekday() >= 5:
            continue
        index = 841 - i
        price = D("100") + D(index) / D("10") + D(index % 7) / D("5")
        history.append((at, price))
    x = session_multiplier(history, now)
    assert x is not None and D(0) < x <= D(1)
    assert session_multiplier(history + [(now, D("999999"))], now) == x
    assert session_multiplier(history[:30], now) is None


def test_three_pod_synthetic_budgets_are_independently_funded():
    rule = _rulebook(["hyperliquid/mainnet:perp:xyz/CL"])
    account = Account.start(rule, START.isoformat())
    funded = _fund_independent_pod_budgets(account, _policy("E2", "IMMEDIATE"))
    assert funded["stress_reserved"] == "180"
    assert funded["stress_available"] == "180"
    assert len(_policy("E2", "IMMEDIATE")["pods"]) == len(PODS) == 3
    assert rule.account_terms_confirmed is False


class FakeMarket:
    def __init__(self, root):
        self.root = root

    def get(self, native, at):
        if native != "hyperliquid:mainnet:perp:xyz:CL":
            raise AssertionError("UNEXPECTED_NATIVE_SYMBOL")
        return MinuteBar(at, D("100"), D("100000"), "a" * 64)


@pytest.mark.parametrize("method", ["E1", "E2", "E3"])
def test_historical_real_account_event_replay(tmp_path, monkeypatch, method):
    import copytrade_pm.pm_portfolio_c_driver as driver

    monkeypatch.setattr(driver, "VerifiedHyperliquidMinuteSource", FakeMarket)
    # A late first entry must never pay for the idle hours before its entry.
    at_open = START + timedelta(hours=2, minutes=1)
    at_close = START + timedelta(hours=2, minutes=14)
    market_id = native_to_pm("hyperliquid:mainnet:perp:xyz:CL")
    manifest = {
        "events": [
            {
                "time": at_open.isoformat(),
                "source_at": (at_open - timedelta(seconds=15)).isoformat(),
                "pod": "CO-001",
                "coin": "xyz:CL",
                "instrument": market_id,
                "relative_units_per_dollar": "0.01",
                "vol_factor": "0.8",
                "tid": 1,
            },
            {
                "time": at_close.isoformat(),
                "source_at": (at_close - timedelta(seconds=15)).isoformat(),
                "pod": "CO-001",
                "coin": "xyz:CL",
                "instrument": market_id,
                "relative_units_per_dollar": "0",
                "vol_factor": "0.8",
                "tid": 2,
            },
        ],
        "ranges": [
            {
                "start": at_open.isoformat(),
                "end": (at_close + timedelta(minutes=5)).isoformat(),
                "instrument": market_id,
                "pod": "CO-001",
            }
        ],
        "instruments": [market_id],
        "market_day_shas": {"synthetic@2026-07-01": "a" * 64},
    }
    result = run_one(
        manifest,
        "a" * 64,
        tmp_path,
        tmp_path / f"{method.lower()}-account",
        method=method,
        execution="IMMEDIATE",
        cost_multiplier=1,
    )
    data = json.loads(Path(result["result"]).read_text(encoding="utf-8"))
    assert data["ledger_replay_verified"] is True
    assert data["data_blocker"] is None
    assert data["ledger_event_count"] >= 3
    assert data["net_pnl_usd"] != "0"
    assert abs(
        sum((D(v) for v in data["pod_pnl_usd"].values()), D(0)) - D(data["net_pnl_usd"])
    ) < D("1e-12")
    assert data["remaining_account_positions"] == {}
    assert data["broker_executable"] is False
    path = next((tmp_path / f"{method.lower()}-account").glob("pc-*/events.jsonl"))
    events = [json.loads(row)["event"] for row in path.read_text().splitlines()]
    assert not any(
        ev["kind"] == "FUNDING" and ev["decision_at"] <= at_open.isoformat() for ev in events
    )
    assert any(ev["kind"] == "FUNDING" for ev in events)


def test_zero_liquidity_exit_near_floor_preserves_inventory_and_halts():
    key = Instrument.parse(native_to_pm("hyperliquid:mainnet:perp:xyz:CL"))
    account = Account.start(_rulebook([key.key]), START.isoformat())
    account.mark({key: D("100")}, START.isoformat())
    account.simulate_fill(
        key,
        D("10"),
        D("100"),
        D("0"),
        accepted=True,
        allocated={"CO-001": D("10")},
    )
    at = (START + timedelta(minutes=1)).isoformat()
    account.mark({key: D("74")}, at)
    assert account.equity == D("9740")
    observation = MarketObservation(
        instrument=key,
        event_at=at,
        first_known_at=at,
        mark=D("74"),
        volume_base=D("0"),
        quality="OHLCV_1M_PROXY",
        supported=True,
    )
    costs = CostModel(D(0), D(0), D(0), D(0), D("0.05"), 300, 1)
    result = execute_targets(
        account,
        {"CO-001": {key: D(0)}},
        {key: observation},
        costs,
        decision_at=at,
        hypothetical_fill_at=(START + timedelta(minutes=1, seconds=2)).isoformat(),
        permitted=True,
    )
    assert result["rejections"] == [f"NO_EXECUTION_CAPACITY:{key.key}"]
    assert account.quantities[key] == D("10")
    account.mark({key: D("69")}, (START + timedelta(minutes=2)).isoformat())
    assert account.breached
    assert account.halt_reason == "CONTRACTUAL_EQUITY_FLOOR"
    assert account.quantities[key] == D("10")


def test_pm04_flattened_instrument_does_not_need_future_quote(tmp_path):
    run = make_run(tmp_path, execution_policy="IMMEDIATE")
    signal(run, "open", [target("W028", 2, 1, first_known_seconds=60)], 60)
    signal(run, "close", [target("W028", 0, 2, first_known_seconds=120)], 120)
    assert run.account.quantities.get(
        Instrument.parse("hyperliquid/mainnet:perp:default/BTC"), D(0)
    ) == D(0)
    payload = {**engine(180), "observations": [], "shocks": [{}]}
    run.record(event("no-quote-for-flat", "PM04_TICK", payload, 180))
    assert str(run.account.risk) != "HALT"
