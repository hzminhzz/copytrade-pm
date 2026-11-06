"""Actual-shape, synthetic provenance/ID tests for read-only vendor reconciliation."""

from __future__ import annotations

import gzip
from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

import pytest

from copytrade_pm.pm_vike_reconcile import (
    _ms,
    archive_vike_chunks,
    load_hyperx,
    load_vike,
    reconcile,
    wallet_from_registry,
)

WALLET = "0x" + "1" * 40
BIG_ID = 9_007_199_254_740_993  # Must survive > JS 2**53
T0 = "2026-10-01T00:00:00Z"


def vike_fill(tid: int, ts: str, quantity: float = 2.0, coin: str = "BTC") -> dict:
    return {
        "trade_id": tid,
        "ts": ts,
        "symbol": coin,
        "side": "buy",
        "price": 100.0,
        "size_token": quantity,
        "size_usd": quantity * 100,
        "dex_name": "HL",
    }


def hyperx_fill(tid: int, ts: str, quantity: str = "2.0", coin: str = "BTC") -> dict:
    return {
        "tid": tid,
        "time": _ms(ts),
        "coin": coin,
        "side": "B",
        "px": "100.0",
        "sz": quantity,
        "user": WALLET,
    }


def write_vike(tmp: Path, fills: list[dict], *, total: int = 2, known=None):
    for part in range(total):
        items = fills[part::total]
        payload = {
            "schema": "vike_mcp_unmodified_fill_items_chunk_v1",
            "wallet": WALLET,
            "query": {
                "start": "2026-09-01T00:00:00Z",
                "end": "2026-11-01T00:00:00Z",
            },
            "part": part,
            "total_parts": total,
            "items": items,
            "retrospective_first_known_at": known,
        }
        (tmp / f"vike_w028_part_{part:03d}.json").write_text(json.dumps(payload))


def write_hyperx(tmp: Path, fills: list[dict]):
    page_dir = tmp / "hx/pages/W028/BTC"
    page_dir.mkdir(parents=True)
    payload = json.dumps({"page": 1, "page_size": 2000, "fills": fills}).encode()
    marker = {
        "alias": "W028",
        "coin": "BTC",
        "page": 1,
        "page_size": 2000,
        "sha256": sha256(payload).hexdigest(),
    }
    (page_dir / "page-00001.json.gz").write_bytes(gzip.compress(payload, mtime=0))
    (page_dir / "page-00001.meta.json").write_text(json.dumps(marker))
    (tmp / "hx/append_only_page_journal.jsonl").write_text(json.dumps(marker) + "\n")


def test_same_second_partial_fills_with_64bit_trade_ids(tmp_path):
    # This must preserve two native trades with the same timestamp/quantity.
    a, b = BIG_ID, BIG_ID + 1
    rows = [vike_fill(a, T0), vike_fill(b, T0)]
    write_vike(tmp_path, rows)
    write_hyperx(tmp_path, [hyperx_fill(a, T0), hyperx_fill(b, T0)])
    vk, vm = load_vike(tmp_path)
    hx, hm = load_hyperx(tmp_path / "hx", alias="W028", wallet=WALLET)
    hm["wallet_address"] = WALLET
    report = reconcile(vk, hx, vm, hm)
    assert report["counts"]["matched_trade_ids"] == 2
    assert report["counts"]["matched_conflicts"] == {}
    assert report["counts"]["vike_only"] == 0
    assert report["missing_data_auto_inserted"] == 0
    assert report["prospective_known_at_reconstructed"] is False


def test_vike_only_interior_window_is_unresolved_not_auto_repaired(tmp_path):
    times = ["2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z", "2026-10-01T00:00:02Z"]
    write_vike(tmp_path, [vike_fill(101 + i, ts) for i, ts in enumerate(times)])
    write_hyperx(tmp_path, [hyperx_fill(101, times[0]), hyperx_fill(103, times[2])])
    vk, vm = load_vike(tmp_path)
    hx, hm = load_hyperx(tmp_path / "hx", alias="W028", wallet=WALLET)
    hm["wallet_address"] = WALLET
    report = reconcile(vk, hx, vm, hm)
    assert report["counts"]["vike_only_classes"] == {
        "WITHIN_HYPERX_OBSERVED_SYMBOL_RANGE_UNRESOLVED": 1
    }
    assert report["interior_gap_candidates"][0]["trade_id"] == "102"


def test_price_conflict_flagged_not_resolved_with_float_matching(tmp_path):
    write_vike(tmp_path, [vike_fill(101, T0)])
    rows = [hyperx_fill(101, T0)]
    rows[0]["px"] = "100.001"
    write_hyperx(tmp_path, rows)
    vk, vm = load_vike(tmp_path)
    hx, hm = load_hyperx(tmp_path / "hx", alias="W028", wallet=WALLET)
    hm["wallet_address"] = WALLET
    report = reconcile(vk, hx, vm, hm)
    assert report["status"] == "BLOCKED_FILL_CONFLICT"
    assert report["counts"]["matched_conflicts"] == {"price": 1}


def test_duplicate_native_trade_id_rejected_even_between_chunks(tmp_path):
    write_vike(tmp_path, [vike_fill(BIG_ID, T0), vike_fill(BIG_ID, T0)])
    with pytest.raises(ValueError, match="VIKE_NATIVE_TRADE_ID_DUPLICATED"):
        load_vike(tmp_path)


def test_missing_chunk_fails_closed(tmp_path):
    write_vike(tmp_path, [vike_fill(1, T0)])
    (tmp_path / "vike_w028_part_001.json").unlink()
    with pytest.raises(ValueError, match="VIKE_CHUNK_SEQUENCE_GAP"):
        load_vike(tmp_path)


def test_retrospective_cannot_be_stamped_as_first_known(tmp_path):
    write_vike(tmp_path, [vike_fill(1, T0)], known=T0)
    with pytest.raises(ValueError, match="VIKE_RETROSPECTIVE_KNOWN_AT_FORGED"):
        load_vike(tmp_path)


def test_hyperx_byte_tamper_cannot_pass_original_sha(tmp_path):
    write_hyperx(tmp_path, [hyperx_fill(1, T0)])
    raw = tmp_path / "hx/pages/W028/BTC/page-00001.json.gz"
    data = json.loads(gzip.decompress(raw.read_bytes()))
    data["fills"][0]["px"] = "999.0"
    raw.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    with pytest.raises(ValueError, match="HYPERX_RAW_SHA_MISMATCH"):
        load_hyperx(tmp_path / "hx", alias="W028", wallet=WALLET)


def test_utc_offset_and_exact_integer_millisecond_clock():
    assert _ms("2026-11-06T00:00:00.605000Z") == _ms("2026-11-06T07:00:00.605000+07:00")
    assert _ms("2026-11-06T00:00:00.605000Z") % 1000 == 605


def test_private_vike_archive_preserves_raw_bytes_and_refuses_overwrite(tmp_path):
    write_vike(tmp_path, [vike_fill(1, T0), vike_fill(2, T0)])
    source, meta = load_vike(tmp_path)
    assert len(source) == 2
    result = archive_vike_chunks(tmp_path, tmp_path / "archive", alias="W028")
    assert result["source_sha256"] == meta["source_sha256"]
    destination = Path(result["directory"])
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["first_known_at"] is None
    assert manifest["fill_count"] == 2
    for part in (0, 1):
        name = f"vike_w028_part_{part:03d}.json"
        assert (destination / name).read_bytes() == (tmp_path / name).read_bytes()
        assert (destination / name).stat().st_mode & 0o777 == 0o600
    assert (destination / "manifest.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        archive_vike_chunks(tmp_path, tmp_path / "archive", alias="W028")


def test_registry_alias_resolution_read_only_and_collision_refusal(tmp_path):
    db = tmp_path / "wallet.sqlite"
    with closing(sqlite3.connect(db)) as con:
        con.executescript(
            "CREATE TABLE wallets(wallet_id INTEGER PRIMARY KEY, address TEXT NOT NULL);"
            "CREATE TABLE wallet_aliases(namespace TEXT, alias TEXT, wallet_id INTEGER);"
        )
        con.execute("INSERT INTO wallets VALUES (1, ?)", (WALLET,))
        con.execute("INSERT INTO wallet_aliases VALUES ('frozen_pm01','W028',1)")
        con.commit()
    assert wallet_from_registry(db, namespace="frozen_pm01", alias="W028") == WALLET
    with closing(sqlite3.connect(db)) as con:
        con.execute("INSERT INTO wallets VALUES (2, ?)", ("0x" + "2" * 40,))
        con.execute("INSERT INTO wallet_aliases VALUES ('frozen_pm01','W028',2)")
        con.commit()
    with pytest.raises(ValueError, match="REGISTRY_WALLET_IDENTITY_UNRESOLVED"):
        wallet_from_registry(db, namespace="frozen_pm01", alias="W028")
    with pytest.raises(ValueError, match="REGISTRY_FILE_NOT_FOUND"):
        wallet_from_registry(tmp_path / "missing.sqlite", namespace="frozen_pm01", alias="W028")


def test_hyperx_wallet_identity_is_scoped(tmp_path):
    write_hyperx(tmp_path, [hyperx_fill(1, T0)])
    with pytest.raises(ValueError, match="HYPERX_WALLET_IDENTITY_DRIFT"):
        load_hyperx(tmp_path / "hx", alias="W028", wallet="0x" + "2" * 40)
