"""Single bounded source-scope campaign for frozen P1, no trading."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_campaign import observe_frozen_portfolio_readonly
from test_pm_e4_prospective import sample_state
from test_pm_forward_registry_identity import prepare
from test_pm_forward_source_stream import FakeSocket


def test_p1_observes_three_parent_accounts_without_membership_or_pnl_mutation(tmp_path):
    async def run():
        registry, primary, secondary = prepare(tmp_path)
        journal = PaperJournal(tmp_path / "paper")
        addresses = []
        for alias in ("S035-ENA", "S051-BTC", "S053-HYPE"):
            import json

            name = next(primary.glob(alias + "_0x*.json"))
            addresses.append(json.loads(name.read_text())["address"])
        sockets = []
        for address in addresses:
            state = deepcopy(sample_state())
            state["user"] = address
            sockets.append(FakeSocket([{"channel": "allDexsClearinghouseState", "data": state}]))
        before = registry.read_bytes()

        def info(payload):
            if payload["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"cat", "a" * 64
            return None, b"subs", "b" * 64

        def connect(*_args, **_kwargs):
            return sockets.pop(0)

        result = await observe_frozen_portfolio_readonly(
            portfolio_id="P1",
            registry_db=registry,
            primary_dir=primary,
            secondary_dir=secondary,
            journal=journal,
            seconds_per_wallet=2,
            max_frames=1,
            info=info,
            connect=connect,
            now=lambda: (
                datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)
            ).isoformat(),
        )
        assert result["status"] == "BLOCKED_OBSERVATION_ONLY_NO_TRADE"
        assert result["frozen_member_count"] == 3
        assert result["frozen_wallet_id_resolved"] is False
        assert len(result["unresolved_members"]) == 3
        assert all(x["partial_receipts"] == 1 for x in result["partial_account_observations"])
        assert all(
            x["whole_wallet_equity_attested"] is False
            for x in result["partial_account_observations"]
        )
        assert result["broker_orders"] == 0
        assert not result["paper_observed"] and not result["registry_mutated"]
        assert registry.read_bytes() == before
        for alias in ("S035", "S051", "S053"):
            assert journal.source_status(alias)["cursor"] == 1
        assert not journal.path.is_symlink()

    asyncio.run(run())
