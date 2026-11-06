"""Bounded, independent native evidence and immutable overlay guards."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os

import pytest

from copytrade_pm.pm_vike_native_verify import validate_candidates, write_verified_overlay


ADDR = "0x" + "a" * 40
WHEN = "2026-10-15T16:05:20.596000Z"
TID = 9_007_199_254_740_993


def vike():
    return {
        ("HYPE", TID): {
            "symbol": "HYPE",
            "trade_id": TID,
            "ts": WHEN,
            "side": "sell",
            "price": 81.37,
            "size_token": 20.85,
            "size_usd": 1696.5645,
        }
    }


def candidates():
    return [
        {
            "coin": "HYPE",
            "trade_id": str(TID),
            "ts": WHEN,
            "class": "WITHIN_HYPERX_OBSERVED_SYMBOL_RANGE_UNRESOLVED",
        }
    ]


def native(wallet, day):
    assert wallet == ADDR and day == "2026-10-15"
    epoch_ms = int(datetime.fromisoformat(WHEN.replace("Z", "+00:00")).timestamp() * 1000)
    return (
        [{"coin": "HYPE", "tid": TID, "time": epoch_ms, "side": "A", "px": "81.37", "sz": "20.85"}],
        "1" * 64,
    )


def test_confirm_exact_native_id_timestamp_and_economics():
    res = validate_candidates(candidates(), vike(), ADDR, fetch=native)
    assert res["status"] == "NATIVE_CONFIRMED_ALL"
    assert res["native_status_counts"] == {"NATIVE_CONFIRMED_EXACT": 1}
    assert res["historical_known_at"] is None
    assert res["candidates"][0]["native_raw_record"]["tid"] == TID


def test_native_not_found_is_unknown_not_false_positive():
    res = validate_candidates(candidates(), vike(), ADDR, fetch=lambda *_: ([], "1" * 64))
    assert res["status"] == "PARTIAL_OR_CONFLICT"
    assert res["native_status_counts"] == {"NOT_FOUND_IN_BOUNDED_NATIVE_DAY": 1}


def test_native_economic_disagreement_blocks_promotion():
    def bad(wallet, day):
        rows, sha = native(wallet, day)
        rows[0]["sz"] = "20.84"
        return rows, sha

    res = validate_candidates(candidates(), vike(), ADDR, fetch=bad)
    assert res["native_status_counts"] == {"NATIVE_FIELD_CONFLICT": 1}


def test_many_days_refused_before_any_requests():
    selections = [
        {"coin": "HYPE", "trade_id": str(TID), "ts": f"2026-10-{n:02d}T00:00:00Z", "class": "GAP"}
        for n in range(1, 13)
    ]
    with pytest.raises(ValueError, match="NATIVE_DAY_BUDGET_EXCEEDED"):
        validate_candidates(selections, vike(), ADDR, fetch=native)


def test_overlay_is_immutable_hashed_private_and_never_first_known(tmp_path):
    native_report = validate_candidates(candidates(), vike(), ADDR, fetch=native)
    native_report["research_sources_sha256"] = {
        "vike": "a" * 64,
        "hyperx": "b" * 64,
    }
    out = write_verified_overlay(tmp_path / "priv", "W028", native_report, vike())
    root = tmp_path / "priv"
    manifest_path = next(root.glob("*/manifest.json"))
    rows_path = manifest_path.parent / "native_confirmed_missing_fills.jsonl"
    manifest = json.loads(manifest_path.read_text())
    assert out["rows"] == 1
    assert manifest["native_confirmed_fills"] == 1
    assert manifest["schema"] == "copytrade_vike_w028_research_recovery_v2"
    assert manifest["independent_native_raw_records_preserved"] is True
    assert json.loads(rows_path.read_text().splitlines()[0])["raw_native"]["tid"] == TID
    assert manifest["first_known_at"] is None
    assert manifest["sqlite_registry_mutated"] is False
    assert manifest["frozen_hyperx_overwritten"] is False
    assert sha256(rows_path.read_bytes()).hexdigest() == manifest["derived_rows_sha256"]
    assert os.stat(rows_path).st_mode & 0o777 == 0o600
    assert os.stat(manifest_path).st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_verified_overlay(root, "W028", native_report, vike())


def test_unverified_or_unhashed_overlay_fails_closed(tmp_path):
    result = validate_candidates(candidates(), vike(), ADDR, fetch=native)
    with pytest.raises(ValueError, match="OVERLAY_SOURCE_HASHES_MISSING"):
        write_verified_overlay(tmp_path, "W028", result, vike())
    result["research_sources_sha256"] = {"vike": "a" * 64, "hyperx": "b" * 64}
    result["status"] = "PARTIAL_OR_CONFLICT"
    with pytest.raises(ValueError, match="OVERLAY_REQUIRES_ALL_NATIVE_CONFIRMED"):
        write_verified_overlay(tmp_path, "W028", result, vike())
