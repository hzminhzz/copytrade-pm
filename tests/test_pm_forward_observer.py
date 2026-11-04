"""FP shared read-only observer cycles: no market capacity or paper-fills invented."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_observer import (
    capture_shared_observer_cycle,
    exclusive_observer_lease,
    run_readonly_observer_epochs,
    source_native_inventory,
)
from copytrade_pm.pm_forward_source_campaign import _ALIAS
from copytrade_pm.pm_forward_registry_identity import audit_frozen_member_resolution
from copytrade_pm.pm_forward_source_observation import (
    append_public_scope,
    read_public_all_dex_scope,
)
from test_pm_e4_prospective import sample_state
from test_pm_forward_registry_identity import P14, prepare
from test_pm_forward_source_stream import FakeSocket

T = datetime.fromtimestamp(1793294400, UTC)


def seeded(tmp_path):
    registry, primary, secondary = prepare(tmp_path)
    journal = PaperJournal(tmp_path / "private")
    first = json.loads(next(primary.glob("S035-ENA_0x*.json")).read_text())["address"]
    book = deepcopy(sample_state())
    book["user"] = first
    parent = read_public_all_dex_scope(
        alias="S035",
        address=first,
        frame={"channel": "allDexsClearinghouseState", "data": book},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(T + timedelta(seconds=2)).isoformat(),
    )
    append_public_scope(journal, alias="S035", seq=1, receipt=parent)
    return registry, primary, secondary, journal


def parent_hashes(registry, primary, secondary):
    identity = audit_frozen_member_resolution(
        registry_db=registry,
        primary_dir=primary,
        secondary_dir=secondary,
        portfolio_id="P14",
    )
    return {_ALIAS[row["alias"]]: row["address_sha256"] for row in identity["members"]}


def test_observer_process_lease_exclusive_and_reversible(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    with exclusive_observer_lease(journal):
        with pytest.raises(ValueError, match="PAPER_OBSERVER_ALREADY_RUNNING_FOR_JOURNAL"):
            with exclusive_observer_lease(journal):
                pytest.fail("unexpected second lease")
    with exclusive_observer_lease(journal):
        assert (journal.root / "paper-observer.lock").stat().st_mode & 0o077 == 0
    assert not journal.source_status("S035")["paper_admitted"]


def test_observer_refuses_symlinked_lock_file(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    external = tmp_path / "external"
    external.write_text("do not overwrite")
    (journal.root / "paper-observer.lock").symlink_to(external)
    with pytest.raises(ValueError, match="PAPER_OBSERVER_LEASE_UNAVAILABLE"):
        with exclusive_observer_lease(journal):
            pytest.fail("unexpected symlink lease")
    assert external.read_text() == "do not overwrite"


def test_native_inventory_includes_child_hedges_and_missing_aliases(tmp_path):
    registry, primary, secondary, journal = seeded(tmp_path)
    child_address = "0x" + "f" * 40
    child = deepcopy(sample_state())
    child["user"] = child_address
    child["clearinghouseStates"][1][1]["assetPositions"][0]["position"]["coin"] = "xyz:MU"
    observed = read_public_all_dex_scope(
        alias="S035",
        address=child_address,
        frame={"channel": "allDexsClearinghouseState", "data": child},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(T + timedelta(seconds=3)).isoformat(),
    )
    append_public_scope(journal, alias="S035", seq=2, receipt=observed)
    inventory = source_native_inventory(
        journal, expected_parent_hashes=parent_hashes(registry, primary, secondary)
    )
    assert inventory["observed_account_count"] == 2
    assert inventory["observed_native_market_count"] == 3
    assert {item.key for item in inventory["instruments"]} == {
        "hyperliquid/mainnet:perp:default/BTC",
        "hyperliquid/mainnet:perp:xyz/CL",
        "hyperliquid/mainnet:perp:xyz/MU",
    }
    assert inventory["missing_parent_aliases"] == list(P14[1:])
    assert inventory["source_scope_complete"] is False
    assert inventory["whole_wallet_nav_attested"] is False


def test_child_only_scope_does_not_masquerade_as_observed_parent(tmp_path):
    registry, primary, secondary, _ = seeded(tmp_path)
    journal = PaperJournal(tmp_path / "child_only")
    child_address = "0x" + "f" * 40
    child_state = deepcopy(sample_state())
    child_state["user"] = child_address
    child = read_public_all_dex_scope(
        alias="S035",
        address=child_address,
        frame={"channel": "allDexsClearinghouseState", "data": child_state},
        dex_catalog=[None, {"name": "xyz"}],
        discovered_subaccounts=None,
        first_known_at=(T + timedelta(seconds=3)).isoformat(),
    )
    append_public_scope(journal, alias="S035", seq=1, receipt=child)
    identity = parent_hashes(registry, primary, secondary)
    inventory = source_native_inventory(journal, expected_parent_hashes=identity)
    assert inventory["observed_account_count"] == 1
    assert inventory["missing_parent_aliases"] == list(P14)
    assert not inventory["source_scope_complete"]
    with pytest.raises(ValueError, match="PAPER_OBSERVER_PARENT_IDENTITY_CENSUS_INVALID"):
        source_native_inventory(journal, expected_parent_hashes={})


def test_one_shared_cycle_captures_five_parents_and_all_native_positions(tmp_path):
    async def run():
        registry, primary, secondary = prepare(tmp_path)
        journal = PaperJournal(tmp_path / "private")
        before_registry = registry.read_bytes()
        addresses = []
        for member in P14:
            root = secondary if member == "Whale_0x5f94" else primary
            pattern = (
                "HL Perps Whale_0x5f94*.json" if member == "Whale_0x5f94" else member + "_0x*.json"
            )
            addresses.append(json.loads(next(root.glob(pattern)).read_text())["address"])
        sockets = []
        for address in addresses:
            book = deepcopy(sample_state())
            book["user"] = address
            sockets.append(FakeSocket([{"channel": "allDexsClearinghouseState", "data": book}]))
        subscription_count = 0

        def info(request):
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "a" * 64
            return None, b"subs", "b" * 64

        def connect(*args, **kwargs):
            nonlocal subscription_count
            subscription_count += 1
            return sockets.pop(0)

        from copytrade_pm.pm_forward_source_campaign import observe_shared_frozen_sources_readonly

        async def source_capture(**kwargs):
            return await observe_shared_frozen_sources_readonly(
                **kwargs, info=info, connect=connect
            )

        market_requests = []

        class MarketSpy:
            def __init__(self, requested, *, journal, hip3_dexes, now):
                market_requests.append((tuple(x.key for x in requested), hip3_dexes))
                assert len(requested) <= 8
                assert journal is not None
                assert now() == (T + timedelta(seconds=4)).isoformat()

            async def run(self, *, duration_seconds, max_updates_per_channel):
                assert duration_seconds == 0.5
                assert max_updates_per_channel == 1
                return {
                    "missing_native_markets": [],
                    "stream_failures": {},
                    "receipt_counts": {},
                }

        report = await capture_shared_observer_cycle(
            registry_db=registry,
            primary_dir=primary,
            secondary_dir=secondary,
            journal=journal,
            seconds_per_account=2,
            max_source_frames=1,
            market_duration_seconds=0.5,
            max_market_updates=1,
            now=lambda: (T + timedelta(seconds=4)).isoformat(),
            source_capture=source_capture,
            market_factory=MarketSpy,
        )
        assert subscription_count == 5
        assert not sockets
        assert len(market_requests) == 1
        requested, dexes = market_requests[0]
        assert requested == (
            "hyperliquid/mainnet:perp:default/BTC",
            "hyperliquid/mainnet:perp:xyz/CL",
        )
        assert dexes == ("xyz",)
        assert report["shared_source"]["unique_source_wallet_count"] == 5
        assert report["native_inventory"]["observed_account_count"] == 5
        assert report["native_inventory"]["observed_native_market_count"] == 2
        assert report["readiness"]["P1"]["status"] == "BLOCKED_NO_TRADE"
        assert report["readiness"]["P14"]["status"] == "BLOCKED_NO_TRADE"
        assert report["trade_volume_complete"] is False
        assert report["executable_volume_base"] is None
        assert report["financial_events_committed"] == 0
        assert not report["paper_observed"] and not report["real_worker_attested"]
        assert all(journal.source_status(_ALIAS[member])["cursor"] == 1 for member in P14)
        assert registry.read_bytes() == before_registry

    asyncio.run(run())


def test_failed_market_shard_isolated_and_missing_capacity_not_promoted(tmp_path):
    async def run():
        registry, primary, secondary, journal = seeded(tmp_path)

        async def source_capture(**kwargs):
            return {
                "status": "BLOCKED_OBSERVATION_ONLY_NO_TRADE",
                "order_route": "NONE",
                "unique_source_wallet_count": 5,
                "source_subscription_deduplication": "P14_UNION_CAPTURED_ONCE",
                "portfolios": {
                    key: {
                        "unresolved_members": [],
                        "partial_account_observations": [],
                    }
                    for key in ("P1", "P14")
                },
            }

        requested = []

        class FailFirst:
            def __init__(self, native, **kwargs):
                requested.append(tuple(x.key for x in native))

            async def run(self, **kwargs):
                if len(requested) == 1:
                    raise TimeoutError("simulated disconnect")
                return {
                    "missing_native_markets": [],
                    "stream_failures": {},
                    "receipt_counts": {},
                }

        report = await capture_shared_observer_cycle(
            registry_db=registry,
            primary_dir=primary,
            secondary_dir=secondary,
            journal=journal,
            seconds_per_account=2,
            max_source_frames=1,
            market_duration_seconds=0.5,
            max_market_updates=1,
            market_shard_size=1,
            source_capture=source_capture,
            market_factory=FailFirst,
            now=lambda: (T + timedelta(seconds=4)).isoformat(),
        )
        assert len(requested) == 2
        assert len(report["market_failures"]) == 1
        assert report["market_failures"][0]["reason"].startswith("TimeoutError:")
        assert len(report["market_shards"]) == 1
        assert report["native_inventory"]["observed_native_market_count"] == 2
        assert report["status"] == "BLOCKED_NO_TRADE"
        assert not report["paper_admitted"] and report["broker_orders"] == 0

    asyncio.run(run())


def test_observer_restart_epochs_explicit_gap_fault_recovery_and_no_financial_state():
    async def run():
        calls = 0
        sleeps = []

        async def capture():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("network unavailable")
            return {
                "status": "BLOCKED_NO_TRADE",
                "order_route": "NONE",
                "native_inventory": {"observed_native_market_count": 22},
                "market_shards": [{}, {}, {}],
            }

        async def pause(seconds):
            sleeps.append(seconds)

        result = await run_readonly_observer_epochs(
            run_cycle=capture, epochs=2, pause_seconds=0.01, pause=pause
        )
        assert result["completed_epochs"] == 2
        assert result["epochs"][0]["status"] == "DEGRADED_OBSERVER_FAILURE"
        assert result["epochs"][1]["status"] == "BLOCKED_NO_TRADE"
        assert result["epochs"][1]["gap_before_epoch"] is True
        assert result["reconnect_gap_count"] == 1
        assert sleeps == [0.01]
        assert result["uninterrupted_prospective_observation_verified"] is False
        assert not result["protected_worker_attested"] and not result["paper_observed"]
        assert result["financial_events_committed"] == 0

    asyncio.run(run())


def test_supervisor_marks_partial_channels_degraded_but_stays_no_trade():
    async def run():
        async def capture():
            return {
                "status": "BLOCKED_NO_TRADE",
                "order_route": "NONE",
                "native_inventory": {"observed_native_market_count": 2},
                "market_shards": [
                    {"stream_failures": {"default/BTC": ["timeout"]}},
                    {"stream_failures": {}, "missing_native_markets": []},
                ],
                "market_failures": [],
                "source_capture_gaps": [
                    {"member": "S035-ENA", "reason": "NO_ACCOUNT_BOOK_RECEIPT_THIS_EPOCH"}
                ],
            }

        result = await run_readonly_observer_epochs(run_cycle=capture, epochs=1)
        assert result["epochs"][0]["status"] == "DEGRADED_OBSERVER_EVIDENCE"
        assert result["epochs"][0]["current_epoch_capture_gap_count"] == 2
        assert result["epochs"][0]["gap_before_epoch"] is False
        assert result["status"] == "BLOCKED_NO_TRADE"
        assert result["paper_observed"] is False

    asyncio.run(run())


def test_observer_refuses_positive_source_status_before_market(tmp_path):
    registry, primary, secondary, journal = seeded(tmp_path)

    async def source_capture(**kwargs):
        return {"status": "PAPER_RUNNING", "order_route": "NONE"}

    async def run():
        with pytest.raises(ValueError, match="PAPER_OBSERVER_SOURCE_POSITIVE_ATTESTATION"):
            await capture_shared_observer_cycle(
                registry_db=registry,
                primary_dir=primary,
                secondary_dir=secondary,
                journal=journal,
                source_capture=source_capture,
            )

    asyncio.run(run())
