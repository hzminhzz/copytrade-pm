"""Offline, synthetic native-identity cases; no real broker objects or network."""

from copy import deepcopy

import pytest

from copytrade_pm.pm_ml4t_contract import (
    NativeMarket,
    NativeRegistry,
    reconciliation_gate,
    validate_clocks,
)

ACCOUNT = "SYNTHETIC-ACCOUNT"
BTC_USDC = "propr/test:linear:USDC/native-BTC-USDC"
BTC_USD = "propr/test:linear:USD/native-BTC-USD"


def registry():
    return NativeRegistry(
        ACCOUNT,
        [
            NativeMarket("native-1", BTC_USDC, ("BTC", "BTC/USDC")),
            NativeMarket("native-2", BTC_USD, ("BTC", "BTC/USD")),
        ],
    )


def position(identity="position-1", native="native-1"):
    return {
        "account_id": ACCOUNT,
        "position_id": identity,
        "native_market_id": native,
        "signed_quantity": "1.0000000000001",
    }


def order(identity="order-1"):
    return {
        "account_id": ACCOUNT,
        "order_id": identity,
        "client_intent_id": "intent-" + identity,
        "native_market_id": "native-1",
        "signed_quantity": "3",
        "cumulative_filled": "1",
        "status": "PARTIAL",
        "reduce_only": False,
    }


def gate(**changes):
    fields = {
        "expected_positions": {},
        "observed_positions": {},
        "expected_orders": {},
        "observed_orders": {},
        "complete": True,
        "fail_on_reconciliation_mismatch": True,
        "mode": "offline",
        "prior_halt": False,
    }
    return reconciliation_gate(**{**fields, **changes})


def test_btc_alias_never_overwrites_native_quote_inventory():
    reg = registry()
    assert reg.display_lookup("BTC/USDC") == BTC_USDC
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        reg.display_lookup("BTC")
    positions = reg.positions([position(), position("position-2", "native-2")])
    assert set(positions) == {BTC_USDC, BTC_USD}
    with pytest.raises(ValueError, match="UNKNOWN_NATIVE"):
        reg.positions([position(native="BTC")])
    with pytest.raises(ValueError, match="NON_BIJECTIVE"):
        NativeRegistry(ACCOUNT, [NativeMarket("x", BTC_USDC), NativeMarket("y", BTC_USDC)])


def test_duplicate_native_rows_and_unconfirmed_hedge_lots_fail_closed():
    reg = registry()
    with pytest.raises(ValueError, match="DUPLICATE_OR_MISSING"):
        reg.positions([position(), position()])
    with pytest.raises(ValueError, match="HEDGE_POLICY"):
        reg.positions([position(), position("other-lot")])
    with pytest.raises(ValueError, match="WRONG_BROKER_ACCOUNT"):
        reg.positions([{**position(), "account_id": "another-account"}])


def test_identical_order_shapes_keep_native_ids_and_partial_fills():
    reg = registry()
    two = reg.orders([order("one"), order("two")])
    assert len(two) == 2
    assert (
        gate(expected_orders=two, observed_orders=reg.orders([order("one")]))["status"]
        == "NO_TRADE"
    )
    changed = reg.orders([{**order("one"), "cumulative_filled": "2"}, order("two")])
    assert gate(expected_orders=two, observed_orders=changed)["status"] == "NO_TRADE"


@pytest.mark.parametrize("mode", ["offline", "shadow", "read_only"])
def test_every_mode_requires_mismatch_failure_and_retains_halt(mode):
    assert gate(mode=mode, fail_on_reconciliation_mismatch=False)["status"] == "NO_TRADE"
    assert gate(mode=mode, prior_halt=True)["status"] == "NO_TRADE"
    assert gate(mode=mode, complete="true")["status"] == "NO_TRADE"
    assert gate(mode=mode, expected_positions={"a": 1})["status"] == "NO_TRADE"
    with pytest.raises(ValueError, match="NOT_AUTHORIZED"):
        gate(mode="live")


@pytest.mark.parametrize("value", [1.1, True])
def test_lossless_decimal_input_is_required(value):
    with pytest.raises(ValueError, match="LOSSLESS_NATIVE_DECIMAL_REQUIRED"):
        registry().positions([{**position(), "signed_quantity": value}])


def test_exact_quantity_difference_is_not_hidden_by_float_tolerance():
    reg = registry()
    expected = reg.positions([position()])
    observed = reg.positions([{**position(), "signed_quantity": "1.0000000000002"}])
    assert gate(expected_positions=expected, observed_positions=observed)["status"] == "NO_TRADE"


def test_fresh_receipt_does_not_refresh_old_source_and_clock_is_causal():
    with pytest.raises(ValueError, match="STALE"):
        validate_clocks("2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z", "2026-11-01T01:00:01Z", 300)
    with pytest.raises(ValueError, match="CAUSAL"):
        validate_clocks("2026-11-01T01:00:01Z", "2026-11-01T01:00:00Z", "2026-11-01T01:00:02Z", 300)


def test_contract_is_deterministic_nonmutating_and_never_order_authority():
    rows = [position()]
    before = deepcopy(rows)
    reg = registry()
    book = reg.positions(rows)
    first = gate(expected_positions=book, observed_positions=book)
    assert first == gate(expected_positions=book, observed_positions=book)
    assert rows == before
    assert first["status"] == "OFFLINE_CONTRACT_PASS"
    assert first["live_authority"] is first["order_submission"] is False
