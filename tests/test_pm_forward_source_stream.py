"""Bounded public Hyperliquid account stream must remain NOT WHOLE WALLET."""

import asyncio
from datetime import UTC, datetime, timedelta
import json

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_source_stream import bounded_source_scope_capture
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
