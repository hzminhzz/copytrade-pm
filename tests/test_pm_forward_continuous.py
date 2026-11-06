"""Persistent observer public preflight and stream contracts."""

from contextlib import closing
from datetime import UTC, datetime
import json
import sqlite3

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_continuous import SubscriptionBudget, candidate_preflight

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
        )
    assert not root.exists()


def test_explicit_shared_ip_budget_and_all_native_hedges():
    budget = SubscriptionBudget(reserved_connections=7, max_connections=10)
    assert budget.plan((BTC,), account_count=5)["candidate_connections"] == 3
    with pytest.raises(ValueError, match="CONNECTION_BUDGET"):
        SubscriptionBudget(reserved_connections=8).plan((BTC,), account_count=5)
    with pytest.raises(ValueError, match="USER_BUDGET"):
        SubscriptionBudget(reserved_users=6).plan((BTC,), account_count=5)
    with pytest.raises(ValueError, match="DUPLICATE"):
        budget.plan((BTC, BTC), account_count=1)
    hedge = Instrument("hyperliquid", "mainnet:perp:xyz", "CL")
    plan = SubscriptionBudget().plan((hedge, BTC), account_count=5)
    assert plan["required_markets"] == sorted([BTC.key, hedge.key])
    assert plan["subscription_count"] == 11
    assert plan["account_orderability"] == "UNKNOWN"


def test_preflight_manifest_binds_registry_and_old_evidence(tmp_path, monkeypatch):
    import copytrade_pm.pm_forward_continuous as module

    registry = tmp_path / "registry.sqlite"
    with closing(sqlite3.connect(registry)) as db:
        db.execute("CREATE TABLE marker(x)")
    registry.chmod(0o600)
    monkeypatch.setattr(
        module,
        "db_authority_health",
        lambda _: {
            "database_integrity": "VERIFIED",
            "inventory_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(module, "db_status", lambda _: {})
    monkeypatch.setattr(
        module,
        "registry_watched_addresses",
        lambda *_a, **_k: {
            "0x" + "1" * 40: "wallet:1",
        },
    )
    monkeypatch.setattr(
        module,
        "_portfolio_seals",
        lambda *_a, **_k: {
            "P1": {"version": 2, "definition_sha256": "c" * 64},
        },
    )
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
        expected_inventory_sha="b" * 64,
    )
    assert report["status"] == "PREFLIGHT_VERIFIED_OBSERVER_ONLY"
    assert report["unique_wallet_count"] == 1
    assert report["order_route"] == "NONE"
    assert report["financial_admission"] == "BLOCKED_NO_TRADE"
    assert report["portfolio_seals"]["P1"]["definition_sha256"] == "c" * 64
    assert len(report["manifest_sha"]) == 64
    assert "0x" + "1" * 40 not in json.dumps(report)
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
            expected_inventory_sha="d" * 64,
        )
