"""One shared CCXT WebSocket quote writer, no broker, no invented clock."""

import asyncio

import pytest

from copytrade_pm.pm03_account import Instrument
from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_live_quotes import (
    MAX_MARKETS, _single_writer, live_quote_health, native_scope, serve,
)
from copytrade_pm.pm_forward_observer import capture_shared_observer_cycle
from test_pm_forward_observed_paper import BTC, add_quote, at


def test_quote_writer_lease_is_single_writer_and_reusable(tmp_path):
    journal = PaperJournal(tmp_path / "shared")
    with _single_writer(journal.root):
        with pytest.raises(ValueError, match="CCXT_QUOTE_WRITER_ALREADY_RUNNING"):
            with _single_writer(journal.root):
                pytest.fail("duplicate writer admitted")
    with _single_writer(journal.root):
        pass


def test_quote_health_is_read_only_and_stale_is_fail_closed(tmp_path):
    journal = PaperJournal(tmp_path / "shared")
    add_quote(journal, 10)
    before = journal.market_quote_status(BTC.key)
    age_fresh = live_quote_health(journal.path, (BTC,), at(20))
    assert age_fresh["status"] == "FRESH_MARKET_COVERAGE"
    assert age_fresh["fresh"] == 1
    stale = live_quote_health(journal.path, (BTC,), at(43))
    assert stale["status"] == "DEGRADED_MARKET_COVERAGE"
    assert stale["fresh"] == 0 and stale["stale"] == 1
    missing = Instrument("hyperliquid", "mainnet:perp:default", "ETH")
    uncovered = live_quote_health(journal.path, (BTC, missing), at(20))
    assert uncovered["missing"] == 1
    assert before == journal.market_quote_status(BTC.key)


def test_native_scope_blocks_missing_or_unverified_source(tmp_path, monkeypatch):
    from copytrade_pm import pm_forward_live_quotes as module

    db = PaperJournal(tmp_path / "public").path
    monkeypatch.setattr(module, "audit_frozen_member_resolution", lambda **kw: {
        "members": [
            {"alias": alias, "address_sha256": "ab" * 32}
            for alias in ("S035-ENA", "S051-BTC", "S053-HYPE",
                          "S064-xyz:BRENTOIL", "Whale_0x5f94")
        ],
    })
    monkeypatch.setattr(module, "source_native_inventory", lambda *_a, **_k: {
        "missing_parent_aliases": ["S035-ENA"], "instruments": (BTC,),
    })
    args = {
        "registry_db": tmp_path / "registry.sqlite",
        "primary_dir": tmp_path / "primary",
        "secondary_dir": tmp_path / "secondary",
    }
    with pytest.raises(ValueError, match="QUOTE_SOURCE_PARENT_OBSERVATION_MISSING"):
        native_scope(db, **args)
    monkeypatch.setattr(module, "source_native_inventory", lambda *_a, **_k: {
        "missing_parent_aliases": [], "instruments": tuple([BTC] * 65),
    })
    with pytest.raises(ValueError, match="QUOTE_NATIVE_SCOPE_BUDGET_EXCEEDED"):
        native_scope(db, **args)
    monkeypatch.setattr(module, "source_native_inventory", lambda *_a, **_k: {
        "missing_parent_aliases": [], "instruments": (BTC,),
    })
    assert native_scope(db, **args) == (BTC,)
    with pytest.raises(ValueError, match="QUOTE_SCOPE_BUDGET_INVALID"):
        native_scope(db, max_markets=MAX_MARKETS + 1, **args)


def test_ccxt_quote_only_runner_never_subscribes_trade_channel(monkeypatch, tmp_path):
    import copytrade_pm.pm_forward_live_quotes as module

    journal = PaperJournal(tmp_path / "shared")
    stop = asyncio.Event()
    received = []

    async def fake_runner(instruments, **kwargs):
        received.append((instruments, kwargs["channels"], kwargs["min_quote_interval_seconds"]))
        assert kwargs["channels"] == ("quote",)
        stop.set()
        kwargs["stop"].set()

    monkeypatch.setattr(module, "run_ccxt_markets", fake_runner)
    asyncio.run(serve(
        journal, scope=lambda: (BTC,), stop=stop,
        min_interval_seconds=5,
    ))
    assert received == [((BTC,), ("quote",), 5)]


def test_source_only_observer_does_not_create_old_bounded_quote_subscriptions(
    monkeypatch, tmp_path,
):
    from copytrade_pm import pm_forward_observer as observer

    journal = PaperJournal(tmp_path / "shared")

    async def stub_source(**kwargs):
        return {
            "status": "BLOCKED_OBSERVATION_ONLY_NO_TRADE",
            "order_route": "NONE",
            "unique_source_wallet_count": 5,
            "source_subscription_deduplication": True,
            "portfolios": {
                "P14": {
                    "partial_account_observations": [
                        {"member": str(i), "partial_receipts": 1, "errors": []}
                        for i in range(5)
                    ],
                    "unresolved_members": [],
                },
                "P1": {"partial_account_observations": [], "unresolved_members": []},
            },
        }

    monkeypatch.setattr(observer, "audit_frozen_member_resolution", lambda **kw: {
        "members": [{"alias": "S035-ENA", "address_sha256": "ab" * 32}],
    })
    monkeypatch.setattr(observer, "source_native_inventory", lambda *a, **kw: {
        "observed_native_market_count": 1,
        "observed_native_instruments": [BTC.key],
        "instruments": (BTC,),
        "missing_parent_aliases": [],
    })
    monkeypatch.setattr(observer, "audit_live_paper_readiness", lambda **kw: {
        "status": "BLOCKED_NO_TRADE", "reason_codes": ["SOURCE_UNKNOWN"],
        "needed_native_market_count": 1,
    })

    class ForbiddenMarketCapture:
        def __init__(self, *_a, **_k):
            pytest.fail("bounded source observer created an unwanted market session")

    # If the existing supervisor expects additional keys, the test should
    # identify them rather than treating missing evidence as a green status.
    result = asyncio.run(capture_shared_observer_cycle(
        registry_db=tmp_path / "registry.sqlite",
        primary_dir=tmp_path, secondary_dir=tmp_path,
        journal=journal, source_capture=stub_source,
        market_factory=ForbiddenMarketCapture,
        market_capture_enabled=False,
    ))
    assert result["market_shards"] == []
    assert result["status"] == "BLOCKED_NO_TRADE"
    assert result["order_route"] == "NONE"
