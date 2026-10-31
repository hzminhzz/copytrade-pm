"""Synthetic adversarial verification of independent Q3 source fill accounting.

No private vendor pages are committed. All prices, wallet IDs, fills and
expected source PnL are synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import gzip
from hashlib import sha256
import json

import pytest

from copytrade_pm.pm_quarter_fill_audit import (
    START,
    END,
    _original_records,
    _record,
    describe_wallet,
    wallet_fills,
    save_private_artifact,
)
from copytrade_pm.pm_sources import CohortEntry


ADDRESS = "0x" + "1" * 40


def _entry(alias="W001"):
    return CohortEntry(
        alias,
        "original",
        ADDRESS,
        sha256(ADDRESS.encode()).hexdigest(),
        "HISTORICAL_ONLY",
        1,
        0,
    )


def _raw(when, tid, start, side, size, price="100", pnl="0", fee="0.10", coin="BTC"):
    return {
        "user": ADDRESS,
        "coin": coin,
        "tid": tid,
        "time": int(when.timestamp() * 1000),
        "start_position": str(start),
        "side": side,
        "sz": str(size),
        "px": str(price),
        "closed_pnl": str(pnl),
        "fee": str(fee),
        "fee_token": "USDC",
        "dir": "Close Long" if side == "A" else "Open Long",
    }


def _page(root, alias, coin, rows):
    path = root / "slow_pod_data_v1/hyperx_fills_cache_v1/pages" / alias / coin
    path.mkdir(parents=True)
    doc = {
        "page": 1,
        "page_size": 2000,
        "has_more": False,
        "fills": sorted(rows, key=lambda f: f["time"], reverse=True),
    }
    raw = json.dumps(doc).encode()
    (path / "page-00001.json.gz").write_bytes(gzip.compress(raw))
    (path / "page-00001.meta.json").write_text(
        json.dumps({"alias": alias, "coin": coin, "page": 1, "sha256": sha256(raw).hexdigest()})
    )
    return path


def test_precise_92_day_boundary_and_independent_monthly_cashflows():
    fills = [
        _record(
            _raw(START - timedelta(milliseconds=1), 1, 0, "B", 1, pnl="100"), "W001", "BTC", ADDRESS
        ),
        _record(_raw(START, 2, 1, "A", 1, pnl="11", fee="1"), "W001", "BTC", ADDRESS),
        _record(
            _raw(datetime(2026, 8, 25, tzinfo=UTC), 3, 0, "B", 1, pnl="0", fee="0.5"),
            "W001",
            "BTC",
            ADDRESS,
        ),
        _record(
            _raw(END - timedelta(milliseconds=1), 4, 1, "A", 1, pnl="-2", fee="0.5"),
            "W001",
            "BTC",
            ADDRESS,
        ),
        _record(_raw(END, 5, 0, "B", 1, pnl="999"), "W001", "BTC", ADDRESS),
    ]
    row = describe_wallet("W001", fills, ["BTC:POSITION_DISCONTINUITY"])
    assert row["window_calendar_days"] == 92
    assert row["fills"] == 3
    assert row["days_with_fills"] == 3
    assert D(row["gross_closed_pnl_usdc"]) == 9
    assert D(row["reported_fees_usdc"]) == 2
    assert D(row["realized_after_reported_fees_usdc"]) == 7
    assert row["monthly"]["2026-07"]["fills"] == 1
    assert row["monthly"]["2026-08"]["fills"] == 1
    assert row["monthly"]["2026-09"]["fills"] == 1
    assert row["source_total_return"] is None
    assert row["source_unrealized_pnl"] is None
    assert row["follower_realized_net_pnl"] is None
    assert row["post_anchor_position_chain_gaps_all_history"] == 1


def test_fee_rebate_signed_closed_pnl_and_opaque_settlement():
    f = _record(_raw(START, 1, "0", "B", 1, pnl="4", fee="-0.5"), "W001", "BTC", ADDRESS)
    assert f.net_reported == D("4.5")
    assert f.turnover == 100
    raw = _raw(START, 2, "15", "A", 15, coin="#ID", price="0", pnl="5", fee="0.1")
    opaque = _record(raw, "W001", "#ID", ADDRESS)
    assert opaque.turnover == 0
    assert opaque.net_reported == D("4.9")


def test_reject_missing_unknown_fee_currency_and_bad_record():
    valid = _raw(START, 1, 0, "B", 1)
    for edited in [
        {**valid, "closed_pnl": "NaN"},
        {**valid, "fee": "Infinity"},
        {**valid, "fee_token": "HYPE"},
        {k: v for k, v in valid.items() if k != "closed_pnl"},
        {**valid, "user": "0x" + "2" * 40},
    ]:
        with pytest.raises(ValueError):
            _record(edited, "W001", "BTC", ADDRESS)


def test_original_sha_and_economic_normalized_tids(tmp_path):
    row1 = _raw(START + timedelta(hours=1), 99, 0, "B", 1, pnl="0")
    row2 = _raw(START + timedelta(hours=1), 1, 1, "B", 1, pnl="0")
    row3 = _raw(START + timedelta(hours=2), 55, 2, "A", 2, pnl="15")
    folder = _page(tmp_path, "W001", "BTC", [row1, row2, row3])
    normalized, issues = wallet_fills(tmp_path, _entry())
    assert not issues
    assert [row.trade_id for row in normalized] == [99, 1, 55]
    assert sum((row.net_reported for row in normalized), D(0)) == D("14.7")
    meta = folder / "page-00001.meta.json"
    payload = json.loads(meta.read_text())
    payload["sha256"] = "0" * 64
    meta.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="PROVENANCE_DRIFT"):
        _original_records(tmp_path, _entry(), "BTC")


def test_private_artifact_is_content_addressed_and_never_overwritten(tmp_path):
    data = {"schema": "test", "authorized": False}
    target, sha = save_private_artifact(tmp_path / "private", data, "fills")
    assert target.name == f"pm36-2026q3-fills-{sha[:20]}.json"
    assert target.stat().st_mode & 0o077 == 0
    assert save_private_artifact(tmp_path / "private", data, "fills") == (target, sha)
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="HASH_CONFLICT"):
        save_private_artifact(tmp_path / "private", data, "fills")
    with pytest.raises(ValueError, match="INVALID_RESEARCH_ARTIFACT_KIND"):
        save_private_artifact(tmp_path / "private", data, "unknown")


def test_expost_propr_scope_is_explicitly_not_a_pit_trading_universe():
    snapshot = {
        "market_symbols": {
            "crypto": ["BTC"],
            "equities": ["GOOGL"],
            "indices": [],
            "commodities": [],
        }
    }
    rows = [
        _record(_raw(START, 1, 0, "B", 1, pnl="10"), "W001", "BTC", ADDRESS),
        _record(
            _raw(START, 2, 0, "B", 1, pnl="20", coin="xyz:GOOGL"), "W001", "xyz:GOOGL", ADDRESS
        ),
        _record(_raw(START, 3, 0, "B", 1, pnl="30", coin="UNKNOWN"), "W001", "UNKNOWN", ADDRESS),
    ]
    result = describe_wallet("W001", rows, [], snapshot)
    scoped = result["expost_propr_display_classification_not_historical_tradability"]
    assert scoped["DISPLAY_NATIVE_CRYPTO_MATCH"]["fills"] == 1
    assert scoped["TENTATIVE_XYZ_HIP3_DISPLAY_MATCH"]["fills"] == 1
    assert scoped["OUTSIDE_PROPR_DISPLAY_UNIVERSE"]["fills"] == 1
    assert sum(row["fills"] for row in scoped.values()) == 3


def test_duplicate_tid_or_source_position_gap_does_not_become_zero(tmp_path):
    a = _raw(START + timedelta(minutes=1), 1, 0, "B", 1)
    b = _raw(START + timedelta(minutes=2), 1, 1, "A", 1)
    _page(tmp_path, "W001", "BTC", [a, b])
    with pytest.raises(ValueError, match="UNVERIFIED_OR_INCOMPLETE"):
        wallet_fills(tmp_path, _entry())
