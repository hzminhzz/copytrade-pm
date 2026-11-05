"""SQLite-first cutover: source files are legacy after activation.

All tests use a disposable owner-private database and never mutate live services.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from copytrade_pm import pm_operations
from copytrade_pm import wallet_registry as registry
from copytrade_pm import wallet_registry_authority as primary
from test_wallet_registry import address, fixture


INITIAL = "2026-11-05T00:00:00+00:00"
CUTOVER = "2026-11-05T01:00:00+00:00"
IMPORT = "2026-11-05T02:00:00+00:00"


def _seed(tmp_path: Path) -> tuple[Path, dict, str]:
    _, snapshot = fixture(tmp_path)
    db = tmp_path / "registry" / "wallet_registry.sqlite"
    registry.apply(db, snapshot, INITIAL)
    generation = registry.db_status(db)["generation"]["manifest_sha256"]
    return db, snapshot, generation


def _manifest(tmp_path: Path, *, alias: str = "new-primary-4") -> Path:
    private = tmp_path / "source-private"
    private.mkdir(mode=0o700)
    path = private / "new-wallets.json"
    path.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "native-2026",
                "wallets": [
                    {"address": address(4), "aliases": [alias]},
                    {"address": address(2), "aliases": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_sqlite_primary_activation_is_backed_up_and_non_destructive(tmp_path: Path) -> None:
    db, snapshot, generation = _seed(tmp_path)
    before = registry.db_status(db)
    proposed = primary.activate(db, expected=generation, apply=False, now=CUTOVER)
    assert proposed["applied"] is False
    assert registry.db_status(db) == before
    with pytest.raises(ValueError, match="SQLITE_GENERATION_CHANGED"):
        primary.activate(db, expected="f" * 64, apply=True, now=CUTOVER)
    selected = primary.activate(db, expected=generation, apply=True, now=CUTOVER)
    assert selected["authority_mode"] == primary.MODE
    assert selected["generation"] != generation
    with closing(registry.connect(Path(selected["backup"]), False)) as backup:
        assert primary._integrity(backup)
        assert primary.mode(backup) == "LEGACY_IMPORTED_V1"
    with closing(registry.connect(db, False)) as con:
        assert primary._integrity(con)
        assert primary.mode(con) == primary.MODE
        assert con.execute("SELECT COUNT(*) FROM portfolio_versions").fetchone()[0] == 7
        assert (
            con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'guard_primary_%'"
            ).fetchone()[0]
            == 4
        )
    # A historical release that bypasses the new Python guard still cannot
    # reset current monitoring or import dated source generations.
    with closing(registry.connect(db, True)) as stale_writer:
        with pytest.raises(sqlite3.IntegrityError, match="TRACKER_MONITORING_READ_ONLY"):
            stale_writer.execute("UPDATE monitoring SET configured=0")
        with pytest.raises(sqlite3.IntegrityError, match="LEGACY_IMPORT_DISABLED"):
            stale_writer.execute(
                "INSERT INTO import_runs VALUES(?,?,?,?)",
                ("obsolete", IMPORT, "obsolete", 0),
            )
    assert registry.db_status(db)["counts"]["research_unique"] == 3
    assert registry.db_status(db)["authority_mode"] == primary.MODE
    assert registry.db_status(db)["freshness"] == "CURRENT"
    assert primary.activate(db, expected=selected["generation"], apply=True)["unchanged"]
    with pytest.raises(ValueError, match="LEGACY_IMPORT_DISABLED_SQLITE_PRIMARY"):
        registry.apply(db, snapshot, IMPORT)
    assert registry.db_status(db)["generation"]["manifest_sha256"] == selected["generation"]


def test_primary_doctor_no_longer_requires_legacy_files(tmp_path: Path, monkeypatch) -> None:
    db, _, generation = _seed(tmp_path)
    primary.activate(db, expected=generation, apply=True, now=CUTOVER)

    def forbidden(*args):
        raise AssertionError("legacy collect is not an authority read")

    monkeypatch.setattr(registry, "collect", forbidden)
    assert registry.cli(["--db", str(db), "doctor"]) == 0
    state = pm_operations._doctor(db)
    assert state["status"] == "VERIFIED"
    assert state["data"]["authority_mode"] == primary.MODE
    assert state["data"]["counts_match"] is None


def test_native_import_versions_cohort_without_overwriting_monitoring(
    tmp_path: Path,
) -> None:
    db, _, generation = _seed(tmp_path)
    activated = primary.activate(db, expected=generation, apply=True, now=CUTOVER)
    manifest = _manifest(tmp_path)
    planned = primary.register(
        db, manifest, expected=activated["generation"], apply=False, now=IMPORT
    )
    assert planned["wallets_in_manifest"] == 2
    assert planned["applied"] is False
    with pytest.raises(ValueError, match="SQLITE_GENERATION_CHANGED"):
        primary.register(db, manifest, expected=generation, apply=True, now=IMPORT)
    saved = primary.register(db, manifest, expected=activated["generation"], apply=True, now=IMPORT)
    assert saved["cohort_total"] == 2
    assert saved["version"] == 1
    assert saved["backup_verified"] is True
    after = registry.db_status(db)
    assert after["counts"]["research_unique"] == 4
    assert after["counts"]["desired"] == 2
    assert after["counts"]["subscribed"] == 1
    assert after["authority_mode"] == primary.MODE
    assert after["generation"]["authority_updated_at"] == IMPORT
    with closing(registry.connect(db, False)) as con:
        assert primary._integrity(con)
        row = con.execute(
            "SELECT wallet_id FROM wallet_aliases "
            "WHERE namespace='sqlite_primary' AND alias='new-primary-4'"
        ).fetchone()
        assert row is not None
        assert con.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM portfolio_seals").fetchone()[0] >= 0
    assert (
        primary.register(db, manifest, expected=saved["generation"], apply=True, now=IMPORT)[
            "unchanged"
        ]
        is True
    )


def test_conflict_and_insecure_manifest_fail_before_backup(tmp_path: Path) -> None:
    db, _, generation = _seed(tmp_path)
    activated = primary.activate(db, expected=generation, apply=True, now=CUTOVER)
    manifest = _manifest(tmp_path)
    manifest.chmod(0o644)
    with pytest.raises(PermissionError, match="PRIVATE_WALLET_MANIFEST_REQUIRED"):
        primary.register(db, manifest, expected=activated["generation"], apply=True, now=IMPORT)
    manifest.chmod(0o600)
    path = manifest.parent / "collision.json"
    path.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "conflicting",
                "wallets": [
                    {"address": address(4), "aliases": ["shared"]},
                    {"address": address(5), "aliases": ["shared"]},
                ],
            }
        )
    )
    path.chmod(0o600)
    with pytest.raises(ValueError, match="ALIAS_COLLISION_IN_MANIFEST"):
        primary.register(db, path, expected=activated["generation"], apply=True, now=IMPORT)
    assert registry.db_status(db)["generation"]["manifest_sha256"] == activated["generation"]


def test_import_adds_new_cohort_version_instead_of_replacing_members(
    tmp_path: Path,
) -> None:
    db, _, generation = _seed(tmp_path)
    activated = primary.activate(db, expected=generation, apply=True, now=CUTOVER)
    manifest = _manifest(tmp_path)
    first = primary.register(db, manifest, expected=activated["generation"], apply=True, now=IMPORT)
    manifest.write_text(
        json.dumps(
            {
                "schema": "sqlite_wallet_import_v1",
                "cohort": "native-2026",
                "wallets": [{"address": address(6), "aliases": ["new-primary-6"]}],
            }
        )
    )
    second = primary.register(db, manifest, expected=first["generation"], apply=True, now=IMPORT)
    assert second["version"] == 2
    assert second["cohort_total"] == 3
    with closing(registry.connect(db, False)) as con:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM cohort_memberships "
                "WHERE cohort_id='native-2026' AND version=1"
            ).fetchone()[0]
            == 2
        )
        assert (
            con.execute(
                "SELECT COUNT(*) FROM cohort_memberships "
                "WHERE cohort_id='native-2026' AND version=2"
            ).fetchone()[0]
            == 3
        )


def test_legacy_mode_stays_compatible(tmp_path: Path) -> None:
    db, _, _ = _seed(tmp_path)
    assert registry.db_status(db)["authority_mode"] == "LEGACY_IMPORTED_V1"
    with closing(registry.connect(db, False)) as con:
        assert primary.mode(con) == "LEGACY_IMPORTED_V1"
    assert datetime.fromisoformat(CUTOVER).tzinfo == timezone.utc
