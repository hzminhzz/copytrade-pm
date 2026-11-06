"""Missing selection signatures must remain blocked even if SQLite is sound."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from copytrade_pm.wallet_registry_catalog import V2_SHA256
from copytrade_pm.wallet_registry_provenance_diagnostics import inspect_provenance


def db_with_selections(path: Path, *, include_unverified: bool = True) -> Path:
    with closing(sqlite3.connect(path)) as con:
        con.executescript(
            "CREATE TABLE research_selections("
            "source_sha256 TEXT, portfolio_id TEXT);"
            "CREATE TABLE research_selection_proofs("
            "source_sha256 TEXT PRIMARY KEY, source_json TEXT,"
            "signature_hex TEXT, public_key_hex TEXT,"
            "trusted_key_sha256 TEXT, first_known_at TEXT);"
        )
        con.execute(
            "INSERT INTO research_selections VALUES(?,?)",
            (V2_SHA256, "gemini.phase4/E6"),
        )
        if include_unverified:
            con.execute(
                "INSERT INTO research_selections VALUES(?,?)",
                ("a" * 64, "regime.macro/TriadA"),
            )
            con.execute(
                "INSERT INTO research_selections VALUES(?,?)",
                ("a" * 64, "regime.macro/TriadChop"),
            )
        con.commit()
    return path


def test_missing_independent_proof_is_diagnostic_not_registry_repair(tmp_path):
    db = db_with_selections(tmp_path / "registry.sqlite")
    before = db.read_bytes()
    result = inspect_provenance(db)
    assert result["sqlite_physical_integrity"] == "VERIFIED"
    assert result["selection_provenance"] == "BLOCKED"
    assert result["signed_proof_count"] == 0
    assert result["doctor_ready"] is False
    assert result["safe_to_write"] is False
    assert result["trading_authorized"] is False
    assert result["blockers"] == [
        {
            "source_sha256": "a" * 64,
            "selection_count": 2,
            "portfolio_ids": ["regime.macro/TriadA", "regime.macro/TriadChop"],
            "state": "MISSING_SIGNED_PROOF",
        },
    ]
    assert db.read_bytes() == before


def test_untrusted_invalid_signed_proof_stays_blocked(tmp_path):
    db = db_with_selections(tmp_path / "registry.sqlite")
    with closing(sqlite3.connect(db)) as con:
        con.execute(
            "INSERT INTO research_selection_proofs VALUES (?,?,?,?,?,?)",
            ("a" * 64, "{}", "b" * 128, "c" * 64, "d" * 64, "2026-11-05T00:00:00+00:00"),
        )
        con.commit()
    result = inspect_provenance(db)
    assert result["blockers"][0]["state"] == "INVALID_SIGNED_PROOF"
    assert result["doctor_ready"] is False


def test_legacy_v2_is_not_falsely_required_to_have_signature(tmp_path):
    db = db_with_selections(tmp_path / "registry.sqlite", include_unverified=False)
    result = inspect_provenance(db)
    assert result["selection_provenance"] == "VERIFIED_OR_LEGACY_PINNED"
    assert result["selection_provenance_ready"] is True
    assert result["doctor_ready"] is False
    assert result["trading_authorized"] is False


def test_missing_database_is_refused_without_creation(tmp_path):
    db = tmp_path / "missing.sqlite"
    assert inspect_provenance(db)["failure_code"] == "REGISTRY_DB_MISSING_OR_SYMLINK"
    assert not db.exists()
