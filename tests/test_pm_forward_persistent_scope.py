import asyncio
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_continuous import MarketScope, SubscriptionBudget
from copytrade_pm.pm_forward_source_stream import discover_persistent_family
from test_pm_e4_prospective import WALLET, SUB

BTC = Instrument.parse("hyperliquid/mainnet:perp:default/BTC")
HEDGE = Instrument.parse("hyperliquid/mainnet:perp:xyz/BRENTOIL")


def test_shared_parent_child_discovery_preserves_native_identity_and_no_nav():
    calls = []

    def info(request):
        calls.append(request)
        value = (
            [None, {"name": "xyz"}]
            if request["type"] == "perpDexs"
            else [{"master": WALLET, "subAccountUser": SUB}]
        )
        raw = json.dumps(value).encode()
        return value, raw, sha256(raw).hexdigest()

    family = asyncio.run(discover_persistent_family({"S035": WALLET}, info=info))
    assert len(calls) == 2
    assert len(family["accounts"]) == 2
    child = [row for alias, row in family["accounts"].items() if alias != "S035"][0]
    assert child["parent_alias"] == "S035"
    assert child["address"] == SUB
    assert family["source_equity"] is None


def test_unknown_child_census_cannot_mean_complete_or_flat():
    def info(request):
        value = (
            [None] if request["type"] == "perpDexs" else [{"master": SUB, "subAccountUser": WALLET}]
        )
        raw = json.dumps(value).encode()
        return value, raw, sha256(raw).hexdigest()

    with pytest.raises(ValueError, match="PARENT_MISMATCH"):
        asyncio.run(discover_persistent_family({"S035": WALLET}, info=info))


def test_dynamic_hedge_scope_and_gap_preserve_required_unknown_legs():
    scope = MarketScope((BTC,), SubscriptionBudget())
    one = scope.update(
        {
            "parent": {"baseline_valid": True, "positions": {}},
            "child": {"baseline_valid": True, "positions": {HEDGE.key: "-4"}},
        },
        expected_accounts=("parent", "child"),
    )
    assert set(one["required_markets"]) == {BTC.key, HEDGE.key}
    assert one["status"] == "SCOPE_ENUMERATED"
    gap = scope.update(
        {"parent": {"baseline_valid": True, "positions": {}}}, expected_accounts=("parent", "child")
    )
    assert gap["missing_accounts"] == ["child"]
    assert HEDGE.key in gap["required_markets"]
    flat = scope.update(
        {
            "parent": {"baseline_valid": True, "positions": {}},
            "child": {"baseline_valid": True, "positions": {}},
        },
        expected_accounts=("parent", "child"),
    )
    assert flat["required_markets"] == [BTC.key]
    assert flat["scope_sha"] != one["scope_sha"]


def test_budget_failure_keeps_denominator_and_missing_hedge_visible():
    scope = MarketScope((BTC,), SubscriptionBudget(max_markets=1))
    result = scope.update(
        {"parent": {"baseline_valid": True, "positions": {HEDGE.key: "-4"}}},
        expected_accounts=("parent",),
    )
    assert result["subscription_plan"] is None
    assert result["budget_failure"] == "STREAM_SCOPE_BUDGET_INVALID"
    assert len(result["required_markets"]) == 2
    assert not result["coverage_complete"]
