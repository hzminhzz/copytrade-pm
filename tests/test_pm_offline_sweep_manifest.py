"""Public manifest contract: source SHA and clock provenance fail closed."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from copytrade_pm.pm_offline_manifest import (
    SCHEMA,
    ManifestBlocked,
    ManifestInvalid,
    Study,
    inspect_manifest,
)


def fixture(tmp_path: Path):
    def file(name, contents):
        path = tmp_path / name
        path.write_bytes(contents)
        return {"path": name, "sha256": sha256(contents).hexdigest()}

    book = file("book.json", b'{"complete":true}')
    equity = file("equity.json", b'{"nav":"1000"}')
    market = file("data.parquet", b"synthetic-marker-only")
    market_meta = file("source.json", b'{"exchange":"hyperliquid_futures"}')
    rule = file("rule.json", b"frozen synthetic")
    cost = file("cost.json", b"frozen synthetic")
    risk = file("risk.json", b"frozen risk assumptions")
    source = dict(
        account="W001",
        dex="default",
        instrument="BTC",
        book_path=book["path"],
        book_sha256=book["sha256"],
        equity_path=equity["path"],
        equity_sha256=equity["sha256"],
        first_known_basis="HISTORICAL_ORACLE",
    )
    return {
        "schema": SCHEMA,
        "study_id": "case-1",
        "start": "2026-10-20T00:00:00+00:00",
        "end": "2026-10-21T00:00:00+00:00",
        "selection_cutoff": "2026-10-19T00:00:00+00:00",
        "clock_basis": "HISTORICAL_ORACLE",
        "policy": "PER_FILL_ELIGIBILITY",
        "delays_minutes": [10, 5, 2, 1, 0],
        "mode": "CERTIFIED",
        "sources": [source],
        "market_days": [
            dict(
                dex="default",
                instrument="BTC",
                date="2026-10-20",
                **market,
                metadata_path=market_meta["path"],
                metadata_sha256=market_meta["sha256"],
            )
        ],
        "rulebook": rule,
        "cost_model": cost,
        "risk_policy": risk,
        "follower_initial_equity": "10000",
        "source_equity_max_age_minutes": 1440,
        "synthetic_funding_evidence_complete": True,
    }


def test_valid_study_is_stable_and_does_not_certify(tmp_path):
    data = fixture(tmp_path)
    a = Study.validate(data, input_root=tmp_path)
    b = Study.validate(json.loads(json.dumps(data)), input_root=tmp_path)
    assert a.manifest_sha256 == b.manifest_sha256
    assert a.delay_minutes == (0, 1, 2, 5, 10)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data))
    inspected = inspect_manifest(manifest, input_root=tmp_path)
    assert inspected["status"] == "VALIDATED_INPUT_ONLY"
    assert inspected["financial_certified"] is False
    assert inspected["scientifically_qualified"] is False


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("mode", "PASS", "UNKNOWN_RESULT_MODE"),
        ("clock_basis", "LIVE", "UNKNOWN_CLOCK_BASIS"),
        ("delays_minutes", [5, 5], "INVALID_DELAY_SET"),
        ("delays_minutes", [3], "INVALID_DELAY_SET"),
        ("follower_initial_equity", "0", "INVALID_FOLLOWER_EQUITY"),
        ("selection_cutoff", "2026-10-20T01:00:00+00:00", "INVALID_STUDY_WINDOW_OR_CUTOFF"),
    ],
)
def test_invalid_modes_clocks_and_cutoff(tmp_path, field, value, expected):
    data = fixture(tmp_path)
    data[field] = value
    with pytest.raises(ManifestInvalid, match=expected):
        Study.validate(data, input_root=tmp_path)


def test_missing_book_equity_and_tamper_fail_closed(tmp_path):
    data = fixture(tmp_path)
    (tmp_path / "equity.json").unlink()
    with pytest.raises(ManifestBlocked, match="MISSING_INPUT_FILE"):
        Study.validate(data, input_root=tmp_path)
    (tmp_path / "equity.json").write_bytes(b"forged")
    with pytest.raises(ManifestBlocked, match="EQUITY_SHA_MISMATCH"):
        Study.validate(data, input_root=tmp_path)


def test_no_prospective_upgrade_from_vendor_clock(tmp_path):
    data = fixture(tmp_path)
    data["clock_basis"] = "PROSPECTIVE_FIRST_KNOWN"
    data["sources"][0]["first_known_basis"] = "PROSPECTIVE_FIRST_KNOWN"
    with pytest.raises(ManifestBlocked, match="MISSING_INDEPENDENT_FIRST_KNOWN_RECEIPT"):
        Study.validate(data, input_root=tmp_path)


def test_duplicate_and_unverified_exchange(tmp_path):
    data = fixture(tmp_path)
    data["sources"].append(deepcopy(data["sources"][0]))
    with pytest.raises(ManifestInvalid, match="DUPLICATE_SOURCE_IDENTITY"):
        Study.validate(data, input_root=tmp_path)
    data["sources"].pop()
    data["sources"][0]["dex"] = "unverified"
    with pytest.raises(ManifestInvalid, match="UNSUPPORTED_DEX"):
        Study.validate(data, input_root=tmp_path)


def test_escape_and_symlinked_inputs_rejected(tmp_path):
    data = fixture(tmp_path)
    data["sources"][0]["book_path"] = "../book.json"
    with pytest.raises(ManifestInvalid, match="UNSAFE_PATH"):
        Study.validate(data, input_root=tmp_path)
    data = fixture(tmp_path)
    (tmp_path / "alias.json").symlink_to(tmp_path / "book.json")
    data["sources"][0]["book_path"] = "alias.json"
    with pytest.raises(ManifestInvalid, match="SYMLINK_PATH"):
        Study.validate(data, input_root=tmp_path)


def test_sparse_oversized_source_rejected_before_hashing(tmp_path):
    data = fixture(tmp_path)
    book = tmp_path / "book.json"
    with book.open("wb") as stream:
        stream.truncate(256 * 1024 * 1024 + 1)
    with pytest.raises(ManifestBlocked, match="OVERSIZED_BOOK_INPUT"):
        Study.validate(data, input_root=tmp_path)


def test_market_sha_rejected(tmp_path):
    data = fixture(tmp_path)
    data["market_days"][0]["sha256"] = "0" * 64
    with pytest.raises(ManifestBlocked, match="MARKET_DAY_SHA_MISMATCH"):
        Study.validate(data, input_root=tmp_path)
