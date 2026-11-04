"""Shared read-only P1/P14 Hyperliquid source observation; no duplicate wallet feeds."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from contextlib import closing

import pytest

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_campaign import observe_shared_frozen_sources_readonly
from test_pm_e4_prospective import sample_state
from test_pm_forward_registry_identity import P1, P14, prepare
from test_pm_forward_source_stream import FakeSocket


def test_shared_p1_p14_uses_five_source_subscriptions_not_eight(tmp_path):
    async def run():
        registry, primary, secondary = prepare(tmp_path)
        journal = PaperJournal(tmp_path / "paper")
        before = registry.read_bytes()
        addresses = {}
        for alias in P14:
            root = secondary if alias == "Whale_0x5f94" else primary
            filename = (
                next(root.glob("HL Perps Whale_0x5f94*.json"))
                if alias == "Whale_0x5f94"
                else next(root.glob(alias + "_0x*.json"))
            )
            addresses[alias] = json.loads(filename.read_text())["address"]
        sockets = []
        for address in addresses.values():
            state = deepcopy(sample_state())
            state["user"] = address
            sockets.append(FakeSocket([{"channel": "allDexsClearinghouseState", "data": state}]))
        calls = []

        def info(request):
            calls.append(request)
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "a" * 64
            return None, b"subaccounts", "b" * 64

        result = await observe_shared_frozen_sources_readonly(
            registry_db=registry,
            primary_dir=primary,
            secondary_dir=secondary,
            journal=journal,
            seconds_per_wallet=2,
            max_frames=1,
            include_collateral=False,
            info=info,
            connect=lambda *_args, **_kwargs: sockets.pop(0),
            now=lambda: (
                datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)
            ).isoformat(),
        )
        assert result["unique_source_wallet_count"] == 5
        assert len(result["portfolios"]["P1"]["partial_account_observations"]) == 3
        assert len(result["portfolios"]["P14"]["partial_account_observations"]) == 5
        assert [
            row["member"] for row in result["portfolios"]["P1"]["partial_account_observations"]
        ] == list(P1)
        assert not sockets
        assert len([x for x in calls if x["type"] == "perpDexs"]) == 5
        assert all(
            journal.source_status(alias)["cursor"] == 1
            for alias in ("S035", "S051", "S053", "S064", "Whale_0x5f94")
        )
        assert registry.read_bytes() == before
        assert result["status"] == "BLOCKED_OBSERVATION_ONLY_NO_TRADE"
        assert result["paper_admitted"] is False
        assert result["order_route"] == "NONE"
        assert all(row["status"] == "BLOCKED_NO_TRADE" for row in result["portfolios"].values())

    asyncio.run(run())


def test_shared_sources_refuse_drifted_frozen_versions_before_any_transport(tmp_path):
    registry, primary, secondary = prepare(tmp_path)
    with closing(sqlite3.connect(registry)) as db:
        with db:
            db.execute(
                "INSERT INTO portfolio_seals VALUES (?,?,?,?,?)",
                ("P1", 3, "a" * 64, "b" * 64, "2026-11-04T04:00:00+00:00"),
            )
            db.execute(
                "INSERT INTO portfolio_memberships SELECT portfolio_id,3,member_alias,wallet_id "
                "FROM portfolio_memberships WHERE portfolio_id='P1' AND version=2"
            )

    async def run():
        with pytest.raises(ValueError, match="P1_P14_SHARED_SOURCE_REGISTRY_IDENTITY_DRIFT"):
            await observe_shared_frozen_sources_readonly(
                registry_db=registry,
                primary_dir=primary,
                secondary_dir=secondary,
                journal=PaperJournal(tmp_path / "paper"),
                info=lambda *_: pytest.fail("unexpected network request"),
            )

    asyncio.run(run())
