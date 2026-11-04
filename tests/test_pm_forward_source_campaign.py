"""Single bounded source-scope campaign for frozen P1, no trading."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_campaign import observe_frozen_portfolio_readonly
from test_pm_e4_prospective import sample_state
from test_pm_forward_registry_identity import prepare
from test_pm_forward_source_stream import FakeSocket


def test_p1_opt_in_family_capture_preserves_missing_child_scope(tmp_path):
    async def run():
        registry, primary, secondary = prepare(tmp_path)
        journal = PaperJournal(tmp_path / "paper")
        import json

        addresses = [
            json.loads(next(primary.glob(alias + "_0x*.json")).read_text())["address"]
            for alias in ("S035-ENA", "S051-BTC", "S053-HYPE")
        ]
        child = "0x" + "f" * 40
        sockets = []
        for addr in (addresses[0], child, addresses[1], addresses[2]):
            book = deepcopy(sample_state())
            book["user"] = addr
            sockets.append(FakeSocket([{"channel": "allDexsClearinghouseState", "data": book}]))

        def info(payload):
            if payload["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"cat", "a" * 64
            if payload["type"] == "spotClearinghouseState":
                return {"balances": []}, b"spot", sha256(b"spot").hexdigest()
            if payload["type"] == "userVaultEquities":
                return [], b"vault", sha256(b"vault").hexdigest()
            if payload["user"].lower() == addresses[0].lower():
                return [{"master": addresses[0], "subAccountUser": child}], b"subs", "b" * 64
            return None, b"none", "c" * 64

        report = await observe_frozen_portfolio_readonly(
            portfolio_id="P1",
            registry_db=registry,
            primary_dir=primary,
            secondary_dir=secondary,
            journal=journal,
            seconds_per_wallet=2,
            max_frames=1,
            include_subaccounts=True,
            include_collateral=True,
            info=info,
            connect=lambda *_args, **_kwargs: sockets.pop(0),
            now=lambda: (
                datetime.fromtimestamp(1793294400, UTC) + timedelta(seconds=2)
            ).isoformat(),
        )
        assert report["status"] == "BLOCKED_OBSERVATION_ONLY_NO_TRADE"
        assert report["all_parent_books_complete"] is False
        assert report["whole_wallet_equity_attested"] is False
        assert report["partial_account_observations"][0]["expected_account_count"] == 2
        assert report["partial_account_observations"][0]["observed_account_count"] == 2
        assert report["partial_account_observations"][0]["partial_receipts"] == 2
        first_collateral = report["partial_account_observations"][0]["collateral_diagnostics"]
        assert len(first_collateral) == 2
        assert all(item["receipt"]["cursor"] == 1 for item in first_collateral)
        assert all(item["source_equity"] is None for item in first_collateral)
        assert all(
            item["status"] == "BLOCKED_COLLATERAL_AND_VAULT_RECONCILIATION"
            for item in first_collateral
        )
        assert journal.source_status("S035")["cursor"] == 2
        assert journal.source_status("S035")["paper_admitted"] is False
        assert not sockets

    asyncio.run(run())


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
