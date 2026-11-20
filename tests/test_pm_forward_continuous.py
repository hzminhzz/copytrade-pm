"""Persistent observer public preflight and stream contracts."""

from datetime import UTC, datetime
import json
import sqlite3

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_continuous import MarketScope, SubscriptionBudget, candidate_preflight

BTC = Instrument("hyperliquid", "mainnet:perp:default", "BTC")
AT = datetime(2026, 11, 6, 12, tzinfo=UTC).isoformat()


def test_preflight_rejects_collision_before_reading_registry(tmp_path):
    old = PaperJournal(tmp_path / "old")
    before = old.path.read_bytes()
    with pytest.raises(ValueError, match="STATE_COLLISION"):
        candidate_preflight(
            registry_db=tmp_path / "absent",
            state_root=old.root,
            protected_roots=(old.root,),
            instruments=(BTC,),
            revision="a" * 40,
            as_of=AT,
            budget=SubscriptionBudget(),
            portfolio_ids=("acct",),
        )
    assert old.path.read_bytes() == before


def test_preflight_has_no_network_or_directory_side_effect_on_bad_registry(tmp_path):
    root = tmp_path / "candidate"
    with pytest.raises((ValueError, FileNotFoundError, sqlite3.Error)):
        candidate_preflight(
            registry_db=tmp_path / "absent",
            state_root=root,
            instruments=(BTC,),
            revision="a" * 40,
            as_of=AT,
            budget=SubscriptionBudget(),
            portfolio_ids=("acct",),
        )
    assert not root.exists()


def test_explicit_shared_ip_budget_and_all_native_hedges():
    budget = SubscriptionBudget(reserved_connections=7, max_connections=10)
    assert budget.plan((BTC,), account_count=5)["candidate_connections"] == 3
    with pytest.raises(ValueError, match="CONNECTION_BUDGET"):
        SubscriptionBudget(reserved_connections=8).plan((BTC,), account_count=5)
    with pytest.raises(ValueError, match="USER_BUDGET"):
        SubscriptionBudget(reserved_users=6).plan((BTC,), account_count=5)
    # Actual A-window census already consumes the documented ten unique users.
    # A selected three-manager canary cannot share that IP concurrently.
    with pytest.raises(ValueError, match="USER_BUDGET"):
        SubscriptionBudget(reserved_users=10).plan((BTC,), account_count=3)
    with pytest.raises(ValueError, match="DUPLICATE"):
        budget.plan((BTC, BTC), account_count=1)
    hedge = Instrument("hyperliquid", "mainnet:perp:xyz", "CL")
    plan = SubscriptionBudget().plan((hedge, BTC), account_count=5)
    assert plan["required_markets"] == sorted([BTC.key, hedge.key])
    assert plan["subscription_count"] == 11
    assert plan["account_orderability"] == "UNKNOWN"


def test_selected_scope_ignores_unconfigured_market_but_requires_exact_hedge():
    hedge = Instrument("hyperliquid", "mainnet:perp:xyz", "BTC")
    unrelated = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
    scope = MarketScope((BTC,), SubscriptionBudget())
    selected = scope.update(
        {"leader": {"baseline_valid": True, "positions": {hedge.key: "1"}}},
        expected_accounts=("leader",),
    )
    assert selected["required_markets"] == sorted([BTC.key, hedge.key])
    assert unrelated.key not in selected["required_markets"]
    assert selected["status"] == "SCOPE_ENUMERATED"

    # A lost snapshot cannot erase the required hedge or fabricate its exit.
    stale = scope.update(
        {"leader": {"baseline_valid": False}},
        expected_accounts=("leader",),
    )
    assert stale["required_markets"] == selected["required_markets"]
    assert stale["status"] == "DEGRADED_SCOPE"
    assert stale["coverage_complete"] is False


def test_newly_discovered_child_never_silently_exceeds_shared_ip_budget():
    scope = MarketScope((BTC,), SubscriptionBudget(reserved_users=8))
    first = scope.update(
        {
            "p1": {"baseline_valid": True, "positions": {}},
            "p2": {"baseline_valid": True, "positions": {}},
        },
        expected_accounts=("p1", "p2"),
    )
    assert first["status"] == "SCOPE_ENUMERATED"
    assert first["subscription_plan"]["account_count"] == 2

    # An additional real subaccount must become a hard budget degradation.
    child = scope.update(
        {
            "p1": {"baseline_valid": True, "positions": {}},
            "p2": {"baseline_valid": True, "positions": {}},
            "child": {"baseline_valid": True, "positions": {}},
        },
        expected_accounts=("p1", "p2", "child"),
    )
    assert child["status"] == "DEGRADED_SCOPE"
    assert child["budget_failure"] == "STREAM_USER_BUDGET_EXCEEDED"
    assert child["subscription_plan"] is None
    assert child["coverage_complete"] is False
    assert child["order_route"] == "NONE"


def test_preflight_manifest_binds_registry_and_old_evidence(tmp_path):
    from copytrade_pm.roster import RosterStore
    from roster_fixture import WALLETS, add_account

    registry = tmp_path / "registry.sqlite"
    with RosterStore(registry, create=True) as store:
        book = add_account(store, "P1", {"seat_1": WALLETS[0]})
    inventory = RosterStore.authority_health(registry)["inventory_sha256"]
    old = PaperJournal(tmp_path / "old")
    before = old.path.read_bytes()
    report = candidate_preflight(
        registry_db=registry,
        state_root=tmp_path / "new",
        protected_roots=(old.root,),
        instruments=(BTC,),
        revision="a" * 40,
        as_of=AT,
        budget=SubscriptionBudget(),
        portfolio_ids=("P1",),
        expected_inventory_sha=inventory,
    )
    assert report["status"] == "PREFLIGHT_VERIFIED_OBSERVER_ONLY"
    assert report["unique_wallet_count"] == 1
    assert report["order_route"] == "NONE"
    assert report["financial_admission"] == "BLOCKED_NO_TRADE"
    assert report["portfolio_seals"]["P1"]["book_sha256"] == book.sha
    assert len(report["manifest_sha"]) == 64
    assert WALLETS[0] not in json.dumps(report)
    assert old.path.read_bytes() == before
    assert not (tmp_path / "new").exists()
    with pytest.raises(ValueError, match="REGISTRY_GENERATION_CHANGED"):
        candidate_preflight(
            registry_db=registry,
            state_root=tmp_path / "new",
            instruments=(BTC,),
            revision="a" * 40,
            as_of=AT,
            budget=SubscriptionBudget(),
            portfolio_ids=("acct",),
            expected_inventory_sha="d" * 64,
        )
