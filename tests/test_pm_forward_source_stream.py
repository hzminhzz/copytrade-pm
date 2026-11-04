"""Bounded public Hyperliquid account stream must remain NOT WHOLE WALLET."""

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import (
    bounded_source_family_capture,
    bounded_source_scope_capture,
    read_public_collateral_scope,
)
from test_pm_e4_prospective import SUB, WALLET, sample_state


T = datetime.fromtimestamp(1793294400, UTC)


class FakeSocket:
    def __init__(self, frames):
        self.frames = frames
        self.sent = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        if not self.frames:
            raise TimeoutError("simulated no new event")
        return json.dumps(self.frames.pop(0))


def frame(*, snapshot=False, missing_clock=False):
    book = sample_state()
    if snapshot:
        book["isSnapshot"] = True
    if missing_clock:
        book["clearinghouseStates"][0][1].pop("time")
    return {"channel": "allDexsClearinghouseState", "data": book}


def test_public_scope_stream_records_only_unadmitted_account_frames(tmp_path):
    async def run():
        j = PaperJournal(tmp_path / "paper")
        sock = FakeSocket(
            [
                {"channel": "subscriptionResponse", "data": {}},
                frame(snapshot=True),
                frame(),
            ]
        )
        calls = []

        def info(request):
            calls.append(request["type"])
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "c" * 64
            return [{"master": WALLET, "subAccountUser": SUB}], b"subs", "d" * 64

        result = await bounded_source_scope_capture(
            alias="S035",
            address=WALLET,
            journal=j,
            seconds=2,
            max_frames=3,
            info=info,
            connect=lambda *_args, **_kwargs: sock,
            now=lambda: (T + timedelta(seconds=2)).isoformat(),
        )
        assert calls == ["perpDexs", "subAccounts"]
        assert result["frames_received"] == 3
        assert result["per_account_receipts"] == 1
        assert result["snapshot_backfill_excluded"] == 1
        assert result["source_cursor"] == 1
        assert result["errors"] == []
        assert not result["paper_admitted"]
        assert not result["whole_wallet_equity_attested"]
        assert "0x" not in json.dumps(result)
        assert sock.sent == [
            {
                "method": "subscribe",
                "subscription": {"type": "allDexsClearinghouseState", "user": WALLET},
            }
        ]
        assert sock.closed
        assert j.source_status("S035")["status"] == "CAPTURED_ONLY"

    asyncio.run(run())


def test_public_spot_and_vault_receipts_have_distinct_known_clocks_no_equity():
    calls = []

    def info(request):
        calls.append(request["type"])
        if request["type"] == "spotClearinghouseState":
            return (
                {"balances": [{"coin": "USDC", "total": "11"}]},
                b"spot",
                sha256(b"spot").hexdigest(),
            )
        return [{"vaultAddress": "redacted", "equity": "4"}], b"vault", sha256(b"vault").hexdigest()

    async def run():
        result = await read_public_collateral_scope(
            address=WALLET, info=info, now=lambda: T.isoformat()
        )
        assert calls == ["spotClearinghouseState", "userVaultEquities"]
        assert [r["row_count"] for r in result["observations"]] == [1, 1]
        assert all(r["source_event_at"] is None for r in result["observations"])
        assert all(r["first_known_at"] == T.isoformat() for r in result["observations"])
        assert result["source_equity"] is None
        assert result["collateral_reconciled"] is False
        assert result["status"] == "BLOCKED_COLLATERAL_AND_VAULT_RECONCILIATION"
        assert "0x" not in json.dumps(result)

    asyncio.run(run())


def test_invalid_spot_does_not_promote_vault_or_assume_zero():
    def info(request):
        if request["type"] == "spotClearinghouseState":
            return None, b"null", sha256(b"null").hexdigest()
        return [], b"[]", sha256(b"[]").hexdigest()

    async def run():
        result = await read_public_collateral_scope(address=WALLET, info=info)
        assert result["observations"][0]["status"] == "BLOCKED_SCOPE_ACQUISITION"
        assert result["observations"][0]["row_count"] is None
        assert result["observations"][1]["row_count"] == 0
        assert result["source_equity"] is None
        assert not result["provider_atomic_nav_available"]

    asyncio.run(run())


def test_family_capture_observes_parent_and_subaccount_without_merged_nav(tmp_path):
    async def run():
        journal = PaperJournal(tmp_path / "paper")
        parent = FakeSocket([frame()])
        sub_book = sample_state()
        sub_book["user"] = SUB
        sub = FakeSocket([{"channel": "allDexsClearinghouseState", "data": sub_book}])
        sockets = [parent, sub]
        calls = []

        def info(request):
            calls.append(request)
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "c" * 64
            if request["user"].lower() == WALLET.lower():
                return [{"master": WALLET, "subAccountUser": SUB}], b"subs", "d" * 64
            return None, b"none", "e" * 64

        result = await bounded_source_family_capture(
            alias="S035",
            parent_address=WALLET,
            journal=journal,
            seconds_per_account=2,
            max_frames=1,
            info=info,
            connect=lambda *_args, **_kwargs: sockets.pop(0),
            now=lambda: (T + timedelta(seconds=2)).isoformat(),
        )
        assert result["expected_account_count"] == 2
        assert result["observed_account_count"] == 2
        assert result["source_cursor"] == 2
        assert [a["subject"] for a in result["accounts"]] == ["PARENT", "SUBACCOUNT"]
        assert all(a["partial_receipts"] == 1 for a in result["accounts"])
        assert result["parent_subaccount_census_atomic"] is False
        assert result["whole_wallet_equity_attested"] is False
        assert result["spot_vault_collateral_reconciled"] is False
        assert result["status"] == "BLOCKED_INCOMPLETE_WHOLE_WALLET"
        assert "0x" not in json.dumps(result)
        assert journal.source_status("S035")["paper_admitted"] is False
        assert parent.closed and sub.closed
        assert len(calls) == 5

    asyncio.run(run())


def test_family_capture_retains_failed_subaccount_not_flattened(tmp_path):
    async def run():
        journal = PaperJournal(tmp_path / "paper")
        parent = FakeSocket([frame()])
        child = FakeSocket([frame(missing_clock=True)])
        sockets = [parent, child]

        def info(request):
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "c" * 64
            if request["user"].lower() == WALLET.lower():
                return [{"master": WALLET, "subAccountUser": SUB}], b"subs", "d" * 64
            return None, b"none", "e" * 64

        report = await bounded_source_family_capture(
            alias="S035",
            parent_address=WALLET,
            journal=journal,
            seconds_per_account=2,
            max_frames=1,
            info=info,
            connect=lambda *_args, **_kwargs: sockets.pop(0),
            now=lambda: (T + timedelta(seconds=2)).isoformat(),
        )
        assert report["observed_account_count"] == 1
        assert report["accounts"][1]["partial_receipts"] == 0
        assert report["accounts"][1]["transport_status"] == "BLOCKED_SCOPE_OR_SOURCE"
        assert report["source_cursor"] == 1
        assert report["status"] == "BLOCKED_INCOMPLETE_WHOLE_WALLET"
        assert not journal.source_status("S035")["paper_admitted"]

    asyncio.run(run())


def test_broken_source_clock_is_reported_and_does_not_advance_cursor(tmp_path):
    async def run():
        j = PaperJournal(tmp_path / "paper")
        sock = FakeSocket([frame(missing_clock=True)])

        def info(request):
            if request["type"] == "perpDexs":
                return [None, {"name": "xyz"}], b"catalog", "c" * 64
            return None, b"sub", "d" * 64

        observed = await bounded_source_scope_capture(
            alias="S035",
            address=WALLET,
            journal=j,
            seconds=2,
            max_frames=1,
            info=info,
            connect=lambda *_args, **_kwargs: sock,
            now=lambda: (T + timedelta(seconds=2)).isoformat(),
        )
        assert observed["per_account_receipts"] == 0
        assert observed["source_cursor"] == 0
        assert observed["transport_status"] == "BLOCKED_SCOPE_OR_SOURCE"
        assert "SOURCE_PER_DEX_EVENT_CLOCK_UNKNOWN" in observed["errors"][0]
        assert sock.closed

    asyncio.run(run())
