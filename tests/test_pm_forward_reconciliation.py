from hashlib import sha256
import json

from copytrade_pm.pm_forward_journal import PaperJournal
from copytrade_pm.pm_forward_public_trades import (
    PersistentPublicMarket,
    reconcile_public_wallet_fills,
)
from copytrade_pm.pm_forward_stream_journal import verify_streams
from test_pm_forward_public_trades import BUYER, trade, known, BTC


def official(tid, seconds):
    raw = trade(tid, seconds)
    return {
        "coin": raw["coin"],
        "tid": raw["tid"],
        "time": raw["time"],
        "px": raw["px"],
        "sz": raw["sz"],
        "side": "B",
        "hash": raw["hash"],
    }


def test_independent_match_and_later_recovery_never_become_forward_candidates(tmp_path):
    journal = PaperJournal(tmp_path / "private")
    feed = PersistentPublicMarket(journal, BTC, {BUYER: "wallet:17"}, scope_sha="c" * 64)
    feed.begin(known(0))
    feed.observe([trade(1, 1)], known(2))
    feed.observe([trade(2, 3)], known(4))
    original = journal.audit_public_wallet_trade_tape("wallet:17", BTC.key)
    calls = []

    def info(request):
        calls.append(request)
        rows = [official(2, 3), official(3, 7), official(3, 7)]
        raw = json.dumps(rows).encode()
        return rows, raw, sha256(raw).hexdigest()

    result = reconcile_public_wallet_fills(
        journal=journal,
        watched={BUYER: "wallet:17"},
        start_at=known(0),
        end_at=known(8),
        required_markets=(BTC,),
        info=info,
        now=lambda: known(10),
    )
    assert calls[0]["type"] == "userFillsByTime"
    assert result["independent_matches"] == 1
    assert result["recovered_later"] == 1
    assert result["live_match_status"] == "INDEPENDENT_WATCHED_MATCH_OBSERVED"
    assert result["comparison_complete"] is False
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key) == original
    again = reconcile_public_wallet_fills(
        journal=PaperJournal(journal.root),
        watched={BUYER: "wallet:17"},
        start_at=known(0),
        end_at=known(8),
        required_markets=(BTC,),
        info=info,
        now=lambda: known(11),
    )
    assert again["recovered_later"] == 1
    assert journal.audit_public_wallet_trade_tape("wallet:17", BTC.key) == original
    stream = verify_streams(journal.path)["streams"]["reconcile:wallet:17"]
    assert stream["cursor"] == 2
    assert stream["event"]["details"]["rows"][1]["signal_eligible"] is False


def test_no_match_and_incomplete_or_wrong_shape_remain_unknown(tmp_path):
    journal = PaperJournal(tmp_path / "private")

    def info(request):
        raw = b"[]"
        return [], raw, sha256(raw).hexdigest()

    result = reconcile_public_wallet_fills(
        journal=journal,
        watched={BUYER: "wallet:17"},
        start_at=known(0),
        end_at=known(8),
        required_markets=(BTC,),
        info=info,
        now=lambda: known(10),
    )
    assert result["live_match_status"] == "LIVE_MATCH_UNKNOWN"
    assert result["independent_matches"] == 0
    assert result["comparison_complete"] is False
    assert result["financial_events_committed"] == 0
