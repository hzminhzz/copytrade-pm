from decimal import Decimal as D
import json

import pytest

from copytrade_pm.pm03_account import Account, Instrument, RiskState, Rulebook
from copytrade_pm.pm03_memory import Event, Ledger


T = "2026-10-31T04:00:00+00:00"
BTC = Instrument("hyperliquid", "perp", "BTC")
HIP = Instrument("hyperliquid", "hip3:xyz", "BTC")


def rules(**changes):
    params = dict(
        program="SYNTHETIC Classic 1-Step",
        stage="evaluation",
        source="synthetic-fixture",
        observed_at=T,
        version="test-v1",
        timezone="UTC",
        initial_balance=D("10000"),
        profit_target=D("1000"),
        daily_loss=D("500"),
        static_loss=D("1000"),
        trailing_loss=D("800"),
        trailing_cap=D("10000"),
        confirmed=True,
        permitted=(BTC, HIP),
        max_gross_leverage=D("2"),
    )
    params.update(changes)
    return Rulebook(**params)


def test_netting_namespace_and_attribution():
    a = Account.start(rules(), T)
    proposed = {"a": {BTC: D("2"), HIP: D("1")}, "b": {BTC: D("-1")}}
    assert a.external_targets(proposed) == {BTC: D("1"), HIP: D("1")}
    r = a.evaluate(proposed, {BTC: D("100"), HIP: D("100")}, trusted=True, market_known=True)
    assert r["allowed"]
    a.simulate_fill(
        BTC, D("1"), D("100"), D("0.2"), accepted=True, allocated={"a": D("2"), "b": D("-1")}
    )
    a.mark({BTC: D("101")}, "2026-10-31T04:01:00+00:00")
    a.verify()
    assert a.equity == D("10000.8")
    assert a.costs == D("0.2")
    assert a.pm_quantities["a"][BTC] == D("2")


def test_intraday_floor_persists_and_reset_rejected():
    a = Account.start(rules(), T)
    a.simulate_fill(BTC, D("10"), D("100"), D("0"), accepted=True, allocated={"a": D("10")})
    a.mark({BTC: D("40")}, "2026-10-31T05:00:00+00:00")
    assert a.risk == RiskState.HALT
    assert a.halt_reason == "CONTRACTUAL_EQUITY_FLOOR"
    with pytest.raises(ValueError, match="PERSISTS"):
        a.manual_reset(authorization="operator-signed-01", as_of=T)
    with pytest.raises(ValueError, match="HALT_NO_INCREASE"):
        a.simulate_fill(BTC, D("1"), D("40"), D("0"), accepted=True, allocated={"a": D("1")})


def test_unknown_and_unconfirmed_fail_closed():
    a = Account.start(rules(confirmed=False), T)
    d = a.evaluate({"x": {BTC: D("1")}}, {BTC: D("100")}, trusted=True, market_known=True)
    assert not d["allowed"]
    assert "UNVERIFIED_INPUT_OR_RULEBOOK" in d["reasons"]
    a = Account.start(rules(), T)
    assert not a.evaluate({"x": {BTC: D("1")}}, {}, trusted=True, market_known=False)["allowed"]


def test_trailing_cap_and_causal_gates(tmp_path):
    a = Account.start(rules(), T)
    a.mark({}, "2026-10-31T05:00:00+00:00")
    assert a.floor()[1]["trailing"] == D("9200")
    a.high_water = D("13000")
    assert a.floor()[1]["trailing"] == D("10000")
    ledger = Ledger(tmp_path / "private")
    event = Event("e1", T, T, T, T, "DECISION", {"allowed": False}, "abc")
    head = ledger.append(event)
    assert ledger.append(event) == head
    assert len(ledger.read()) == 1
    cp = ledger.checkpoint({"risk": "HALT"})
    assert ledger.load_checkpoint(cp) == {"risk": "HALT"}
    with pytest.raises(ValueError, match="CONFLICTING_EVENT"):
        ledger.append(Event("e1", T, T, T, T, "DECISION", {"allowed": True}, "abc"))
    with pytest.raises(ValueError, match="INVALID_CAUSAL_EVENT"):
        ledger.append(Event("e2", T, "2026-10-30T04:00:00+00:00", T, T, "FILL", {}, "abc"))
    path = ledger.path / f"{cp}.checkpoint.json"
    obj = json.loads(path.read_text())
    obj["payload"]["state"] = {"risk": "GREEN"}
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH"):
        ledger.load_checkpoint(cp)


def test_rejected_fill_does_not_create_position():
    a = Account.start(rules(), T)
    a.simulate_fill(BTC, D("3"), D("100"), D("1"), accepted=False, allocated={"x": D("3")})
    a.verify()
    assert a.cash == D("10000") and not a.quantities
