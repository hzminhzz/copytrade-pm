"""SQLite remains the authority when legacy sources and importer clocks become stale.

Use disposable, owner-private sqlite databases. Never touch production.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_native as native
from copytrade_pm import pm_operations
from test_wallet_registry import fixture, address


INITIAL = "2026-11-04T00:00:00+00:00"
NOW = "2026-11-05T04:00:00+00:00"


def seed(tmp_path: Path) -> tuple[Path, dict, str]:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "private" / "wallet_registry.sqlite"
    registry.apply(db, snapshot, INITIAL)
    baseline = registry.db_authority_health(db)["inventory_sha256"]
    return db, snapshot, baseline


def manifest(tmp_path: Path, *, alias: str = "NATIVE006") -> Path:
    private = tmp_path / "input_private"
    private.mkdir(mode=0o700)
    file = private / "cohort.json"
    file.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "native-wave",
                "wallets": [
                    {"address": address(6), "aliases": [alias]},
                    {"address": address(2), "aliases": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    file.chmod(0o600)
    return file


def test_lock_blocks_legacy_reimport_even_from_old_binary(tmp_path: Path) -> None:
    db, snapshot, before = seed(tmp_path)
    preview = native.lock_legacy_import(db, expected=before)
    assert preview["applied"] is False
    assert preview["inventory_sha256"] == before
    with pytest.raises(ValueError, match="SQLITE_INVENTORY_SHA_CHANGED"):
        native.lock_legacy_import(db, expected="0" * 64, apply=True, now=NOW)
    applied = native.lock_legacy_import(db, expected=before, apply=True, now=NOW)
    assert applied["legacy_import"] == "DISABLED"
    assert applied["backup_verified"] is True
    assert applied["inventory_sha256"] != before
    with closing(registry.connect(Path(applied["backup"]), False)) as old:
        assert not native.locked(old)
        assert old.execute("PRAGMA foreign_key_check").fetchall() == []
    with closing(registry.connect(db, False)) as con:
        assert native.locked(con)
        assert con.execute("SELECT COUNT(*) FROM monitoring").fetchone()[0] >= 1
    # Both current importer and a historical binary bypassing the Python
    # guard must be unable to rewrite monitoring or import manifests.
    with pytest.raises(ValueError, match="LEGACY_SOURCE_IMPORT_DISABLED"):
        registry.apply(db, snapshot, NOW)
    with closing(registry.connect(db, True)) as old_writer:
        with pytest.raises(sqlite3.IntegrityError, match="TRACKER_SNAPSHOT_READ_ONLY"):
            old_writer.execute("UPDATE monitoring SET configured=0")
        with pytest.raises(sqlite3.IntegrityError, match="LEGACY_SOURCE_IMPORT_DISABLED"):
            old_writer.execute(
                "INSERT INTO import_runs VALUES(?,?,?,?)",
                ("obsolete", NOW, "obsolete", 0),
            )
    assert (
        native.lock_legacy_import(db, expected=applied["inventory_sha256"], apply=True)["unchanged"]
        is True
    )


def test_native_cohort_registration_versions_and_preserves_history(tmp_path: Path) -> None:
    db, _, before = seed(tmp_path)
    activated = native.lock_legacy_import(db, expected=before, apply=True, now=NOW)
    file = manifest(tmp_path)
    expected = activated["inventory_sha256"]
    preflight = native.register_cohort(db, file, expected=expected, apply=False, now=NOW)
    assert preflight["next_version"] == 1
    assert preflight["wallets_in_manifest"] == 2
    assert preflight["applied"] is False
    with pytest.raises(ValueError, match="SQLITE_INVENTORY_SHA_CHANGED"):
        native.register_cohort(db, file, expected=before, apply=True, now=NOW)
    first = native.register_cohort(db, file, expected=expected, apply=True, now=NOW)
    assert first["version"] == 1
    assert first["backup_verified"] is True
    assert first["inventory_sha256"] != expected
    with closing(registry.connect(db, False)) as con:
        path, digest = con.execute(
            "SELECT source_path,sha256 FROM evidence_artifacts "
            "WHERE source_key='sqlite_primary:native-wave'"
        ).fetchone()
    immutable = db.parent / path
    assert immutable.is_file()
    assert sha256(immutable.read_bytes()).hexdigest() == digest
    assert immutable.stat().st_mode & 0o777 == 0o600
    assert (
        native.register_cohort(db, file, expected=first["inventory_sha256"], apply=True)[
            "unchanged"
        ]
        is True
    )
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM cohort_memberships WHERE cohort_id='native-wave'"
            ).fetchone()[0]
            == 2
        )
        assert con.execute("SELECT COUNT(*) FROM monitoring WHERE configured=1").fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM portfolio_versions").fetchone()[0] == 7
        assert (
            con.execute("SELECT COUNT(*) FROM wallet_aliases WHERE alias='NATIVE006'").fetchone()[0]
            == 1
        )
        assert con.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1
    file.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "native-wave",
                "wallets": [{"address": address(7), "aliases": ["NATIVE007"]}],
            }
        )
    )
    second = native.register_cohort(
        db, file, expected=first["inventory_sha256"], apply=True, now=NOW
    )
    assert second["version"] == 2
    assert second["cohort_total"] == 3
    assert immutable.is_file()
    assert sha256(immutable.read_bytes()).hexdigest() == digest
    with closing(registry.connect(db, False)) as con:
        versions = con.execute(
            "SELECT version,COUNT(*) FROM cohort_memberships "
            "WHERE cohort_id='native-wave' GROUP BY version ORDER BY version"
        ).fetchall()
        assert versions == [(1, 2), (2, 3)]
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    health = registry.db_authority_health(db)
    assert health["database_integrity"] == "VERIFIED"
    assert health["research_cohorts"]["native-wave"] == 3


def test_invalid_manifest_identity_and_permissions_fail_closed(tmp_path: Path) -> None:
    db, _, before = seed(tmp_path)
    locked = native.lock_legacy_import(db, expected=before, apply=True, now=NOW)
    source = manifest(tmp_path)
    source.chmod(0o644)
    with pytest.raises(PermissionError, match="PRIVATE_WALLET_MANIFEST_REQUIRED"):
        native.register_cohort(db, source, expected=locked["inventory_sha256"], apply=True)
    source.chmod(0o600)
    source.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "native-wave",
                "wallets": [
                    {"address": address(7), "aliases": ["DUPLICATE"]},
                    {"address": address(8), "aliases": ["DUPLICATE"]},
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="NATIVE_MANIFEST_DUPLICATE_IDENTITY"):
        native.register_cohort(db, source, expected=locked["inventory_sha256"], apply=True)
    assert registry.db_authority_health(db)["inventory_sha256"] == locked["inventory_sha256"]


def test_sqlite_native_doctor_and_operations_not_stale_on_old_csv_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db, _, baseline = seed(tmp_path)
    native.lock_legacy_import(db, expected=baseline, apply=True, now=NOW)
    # Independent source importer may disappear entirely after cutover.
    monkeypatch.setattr(
        registry,
        "collect",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy importer read")),
    )
    assert registry.cli(["--db", str(db), "doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["authority"] == "SQLITE"
    generation = pm_operations._generation(db)
    assert generation["status"] == "VERIFIED"
    assert generation["sha"] == registry.db_authority_health(db)["inventory_sha256"]
    assert pm_operations._doctor(db)["status"] == "VERIFIED"
    with closing(registry.connect(db, False)) as con:
        assert native.locked(con)


def test_cli_native_lock_and_status_preserve_non_sensitive_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db, _, baseline = seed(tmp_path)
    assert registry.cli(["--db", str(db), "native", "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["legacy_import"] == "UNLOCKED_LEGACY_WRITER"
    assert status["inventory_sha256"] == baseline
    assert (
        registry.cli(["--db", str(db), "native", "lock", "--expected-inventory-sha", baseline]) == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["applied"] is False
    assert address(1) not in json.dumps(preview)


def test_lock_marker_without_all_sqlite_triggers_fails_closed(tmp_path: Path) -> None:
    db, _, baseline = seed(tmp_path)
    locked = native.lock_legacy_import(db, expected=baseline, apply=True, now=NOW)
    with closing(registry.connect(db, True)) as con:
        con.execute("DROP TRIGGER native_registry_no_legacy_import")
    with pytest.raises(ValueError, match="LEGACY_LOCK_TRIGGER_INTEGRITY_FAILED"):
        registry.db_authority_health(db)
    with pytest.raises(ValueError, match="LEGACY_LOCK_TRIGGER_INTEGRITY_FAILED"):
        native.lock_legacy_import(db, expected=locked["inventory_sha256"], apply=True)


def test_native_cohort_archive_deleted_or_corrupt_fails_doctor_and_idempotency(
    tmp_path: Path,
) -> None:
    db, _, baseline = seed(tmp_path)
    lock = native.lock_legacy_import(db, expected=baseline, apply=True, now=NOW)
    source = manifest(tmp_path)
    result = native.register_cohort(
        db, source, expected=lock["inventory_sha256"], apply=True, now=NOW
    )
    archive = (
        db.parent
        / "evidence"
        / "native-cohorts"
        / f"{sha256(source.read_bytes()).hexdigest()}.json"
    )
    archive.unlink()
    with pytest.raises(ValueError, match="NATIVE_COHORT_EVIDENCE_INVALID"):
        registry.db_authority_health(db)
    with pytest.raises(ValueError, match="NATIVE_COHORT_EVIDENCE_INVALID"):
        native.register_cohort(db, source, expected=result["inventory_sha256"], apply=True, now=NOW)


def test_native_cohort_evidence_root_symlink_is_rejected(tmp_path: Path) -> None:
    db, _, baseline = seed(tmp_path)
    locked = native.lock_legacy_import(db, expected=baseline, apply=True, now=NOW)
    source = manifest(tmp_path)
    external = tmp_path / "elsewhere"
    external.mkdir(mode=0o700)
    (db.parent / "evidence").symlink_to(external, target_is_directory=True)
    with pytest.raises(PermissionError, match="PRIVATE_EVIDENCE_DIRECTORY_REQUIRED"):
        native.register_cohort(db, source, expected=locked["inventory_sha256"], apply=True, now=NOW)
    assert registry.db_authority_health(db)["inventory_sha256"] == locked["inventory_sha256"]


def test_unlocked_legacy_import_keeps_existing_fixture_behavior(tmp_path: Path) -> None:
    db, snapshot, baseline = seed(tmp_path)
    with closing(registry.connect(db, False)) as con:
        assert not native.locked(con)
    updated = {**snapshot, "sources": {**snapshot["sources"], "research-108": "f" * 64}}
    registry.apply(db, updated, NOW)
    assert registry.db_authority_health(db)["inventory_sha256"] != baseline
    assert datetime.fromisoformat(NOW).tzinfo == timezone.utc
